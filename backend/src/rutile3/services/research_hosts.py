"""Start research turns through an operator-configured local host."""
import json
import os
from pathlib import Path
from queue import Empty, Full, Queue
import signal
import subprocess
from threading import Event, RLock, Thread
from time import monotonic, time

from rutile3.data import local_settings
from rutile3.data.reference_research import digest
from rutile3.jobs.storage import read_json, write_json
from rutile3.services import research_setup
from rutile3.services.research_activity import ResearchActivity
from rutile3.services.reference_research import session_decision


HOST_ENV = {"SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT", "PATH", "TEMP", "TMP", "HOME", "USERPROFILE",
            "APPDATA", "LOCALAPPDATA", "LANG", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_RUNTIME_DIR"}


def research_task(request, staged=()):
    return (
        f"Research Rutile batch {request['request_id']} for project {request['project_id']}. "
        "Use get_reference_request to read the approved targets, saved evidence, and scratch directory. "
        "Follow the project research AGENTS.md. Use host-approved retrieval and the isolated offline Python runtime "
        "for extraction. Send a phase-data proposal or a specific unresolved finding for each target. "
        "Use the existing drafts if a target is already staged. "
        + (f"Already staged target IDs: {', '.join(staged)}." if staged else "")
    )


def host_command(host):
    config = research_setup.custom_command("codex" if host == "codex_custom" else host)
    if config is None:
        raise ValueError("Configure a scoped launcher for the selected research host.")
    return config


def stop_process(process):
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=8,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


class HostProcess:
    def __init__(self, command, folder, scratch, notify, flush):
        environment = {key: value for key, value in os.environ.items() if key.upper() in HOST_ENV}
        environment["RUTILE_RESEARCH_SCRATCH"] = str(scratch)
        self.process = subprocess.Popen(command, cwd=folder, env=environment, text=True, encoding="utf-8",
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                        start_new_session=os.name != "nt",
                                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        self.messages = Queue(maxsize=512)
        self.stop_reading = Event()
        self.next_id = 0
        self.notify = notify
        self.flush = flush
        self.reader = Thread(target=self.read, daemon=True)
        self.reader.start()

    def read(self):
        try:
            for line in self.process.stdout:
                try:
                    value = json.loads(line)
                except ValueError:
                    continue
                while not self.stop_reading.is_set():
                    try:
                        self.messages.put(value, timeout=.25)
                        break
                    except Full:
                        pass
                if self.stop_reading.is_set():
                    return
        except (OSError, UnicodeError):
            return

    def send(self, message):
        self.process.stdin.write(json.dumps(message) + "\n")
        self.process.stdin.flush()

    def receive(self, until, timeout):
        deadline = monotonic() + timeout
        while monotonic() < deadline:
            try:
                message = self.messages.get(timeout=.25)
            except Empty:
                self.flush()
                if self.process.poll() is not None:
                    break
                continue
            if isinstance(message, dict):
                self.notify(message)
                self.flush()
                if until(message):
                    return message
        raise ValueError("The research host exited or timed out.")

    def rpc(self, *, method=None, params=None, type=None, **fields):
        self.next_id += 1
        identifier = self.next_id
        message = {"id": str(identifier), "type": type, **fields} if type else {
            "id": identifier, "method": method, "params": params or {}}
        self.send(message)
        response = self.receive(lambda value: value.get("id") == message["id"] and
                                (value.get("type") == "response" if type else "method" not in value), 30)
        if response.get("error") or response.get("success") is False:
            raise ValueError("The research host rejected the operation.")
        return response.get("data" if type else "result") or {}

    def close(self):
        self.stop_reading.set()
        stop_process(self.process)
        self.reader.join(timeout=2)
        self.process.stdin.close()
        self.process.stdout.close()


def launch_codex(client, folder, previous, task, save_session, activity):
    client.rpc(method="initialize", params={"clientInfo": {"name": "rutile_research", "version": "1.0"}})
    client.send({"method": "initialized"})
    activity.event("Codex App Server connected")
    thread = None
    if previous:
        try:
            thread = client.rpc(method="thread/resume", params={"threadId": previous, "cwd": str(folder),
                                                               "excludeTurns": True})["thread"]["id"]
        except ValueError:
            pass
    if not thread:
        thread = client.rpc(method="thread/start", params={"cwd": str(folder), "ephemeral": False})["thread"]["id"]
    save_session(thread, bool(previous and previous == thread))
    activity.event("Sending the research task")
    turn = client.rpc(method="turn/start", params={"threadId": thread, "input": [{"type": "text", "text": task,
                                                                                 "text_elements": []}]})["turn"]["id"]
    result = client.receive(lambda m: m.get("method") == "turn/completed"
                            and m.get("params", {}).get("turn", {}).get("id") == turn, 3600)
    return result["params"]["turn"]["status"] == "completed"


def launch_pi(client, previous, task, save_session, activity):
    resumed = False
    if previous:
        try:
            resumed = not client.rpc(type="switch_session", sessionPath=previous).get("cancelled")
        except ValueError:
            pass
    if not resumed and client.rpc(type="new_session").get("cancelled"):
        raise ValueError("Pi canceled the research session.")
    activity.event("Pi session ready. Sending the research task")
    if client.rpc(type="prompt", message=task).get("disposition") == "queued":
        raise ValueError("Pi queued the prompt behind another run.")
    result = client.receive(lambda m: m.get("type") == "agent_end", 3600)
    final = next((item for item in reversed(result.get("messages", [])) if item.get("role") == "assistant"), {})
    current = client.rpc(type="get_state")
    if current.get("sessionFile"):
        save_session(current["sessionFile"], resumed)
    return final.get("stopReason") == "stop"


class ResearchHosts:
    def __init__(self):
        self.lock = RLock()
        self.active = {}

    def available(self):
        available = ["codex"] if research_setup.codex_executable() else []
        for host in ("codex_custom", "pi"):
            try:
                host_command(host)
            except ValueError:
                continue
            available.append(host)
        return available

    def running(self, request_id):
        with self.lock:
            return request_id in self.active

    def start(self, service, project_id, request_id, host, *, origin=None):
        folder = service.store.project(project_id)
        scratch = service.store.folder(project_id, request_id) / "scratch"
        if origin:
            if host == "codex":
                command = research_setup.managed_codex(origin, folder, scratch)
                # This permission entry changes with each batch. Conversation scope is per project.
                route_command = [command[0], origin]
            else:
                route_command = command = host_command(host)
                research_setup.prepare_connector(origin)
        else:
            route_command = command = host_command(host)
        # The configured launcher owns model credentials and the host permission profile.
        scope = local_settings.value(f"RUTILE_RESEARCH_{host.removesuffix('_custom').upper()}_SESSION_SCOPE") or ""
        route = digest([host, route_command, scope])
        key = (project_id, route)
        path = folder / "sessions" / f"{route}.json"
        with self.lock:
            if request_id in self.active or any(run["key"] == key for run in self.active.values()):
                raise ValueError("A research batch is already running for this project and host.")
            service.reopen(project_id, request_id)
            request = service.status(project_id, request_id, agent=True)
            saved = read_json(path) if path.is_file() else {}
            decision = session_decision(request["session"], saved.get("ended_at"), time())
            previous = saved.get("session_id") if decision["action"] == "resume" else None
            run = {"key": key, "stop": Event(), "client": None}
            service.activity(project_id, request_id, phase="starting", output="", events=[],
                             output_tokens=None, usage_elapsed_s=None, ended_elapsed_s=None, mcp=None, started_at=time())
            service.host_status(project_id, request_id, host, decision, running=True)
            self.active[request_id] = run
            thread = Thread(target=self.run, args=(service, request, host, command, folder, path, previous, decision, run),
                            daemon=True)
            run["thread"] = thread
            thread.start()
        return decision

    def run(self, service, request, host, command, folder, path, previous, decision, run):
        project_id, request_id = request["project_id"], request["request_id"]
        session_id = previous
        client = None
        state = "failed"
        error = None

        def save_session(identifier, resumed):
            nonlocal session_id
            session_id = identifier
            if previous and not resumed:
                service.host_status(project_id, request_id, host,
                                    {"action": "new", "reason": "Saved conversation could not be resumed"}, running=True)

        activity = ResearchActivity(lambda snapshot: service.activity(project_id, request_id, **snapshot))
        try:
            if not run["stop"].is_set():
                notify = activity.pi if host == "pi" else activity.codex
                client = HostProcess(command, folder, Path(request["scratch_directory"]), notify, activity.flush)
                with self.lock:
                    run["client"] = client
                if not run["stop"].is_set():
                    task = research_task(request, request["staged_targets"])
                    completed = (launch_pi(client, previous, task, save_session, activity) if host == "pi"
                                 else launch_codex(client, folder, previous, task, save_session, activity))
                    if not completed:
                        error = "The agent ended its turn with an error. Check its sign-in and research setup."
                    if completed:
                        # A completed conversation can still have gaps the user wishes to retry.
                        staged = service.status(project_id, request_id)["proposals"]
                        covered = {p["target_id"] for p in staged}
                        state = "completed" if request["targets"].keys() <= covered else "failed"
                        if state == "failed":
                            error = "The host ended before staging a finding for every target."
        except (OSError, ValueError, KeyError, TypeError):
            error = ("The agent could not start. Check that it is signed in and that the Rutile MCP tools load."
                     if activity.phase == "starting" else
                     "The agent disconnected or timed out. You can review any findings it staged.")
        finally:
            try:
                if client:
                    try:
                        client.close()
                    except OSError:
                        state, error = "failed", "The research host could not be closed cleanly."
                if session_id:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    write_json(path, {"session_id": session_id, "ended_at": time()})
                if run["stop"].is_set():
                    state, error = "canceled", None
                activity.flush(force=True)
                service.host_status(project_id, request_id, host, None, running=False, error=error)
                service.finish(project_id, request_id, state)
            finally:
                with self.lock:
                    self.active.pop(request_id, None)

    def stop(self, request_id):
        with self.lock:
            run = self.active.get(request_id)
            if not run:
                return
            run["stop"].set()
            client = run["client"]
        if client:
            stop_process(client.process)

    def close(self):
        with self.lock:
            runs = list(self.active.items())
        for request_id, run in runs:
            self.stop(request_id)
            run["thread"].join(timeout=10)
