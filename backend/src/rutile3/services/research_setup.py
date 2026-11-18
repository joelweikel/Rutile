"""Prepare the bundled connector and local research launchers."""
import json
import os
from pathlib import Path
from secrets import token_urlsafe
import shutil
import subprocess
import sys

from rutile3.data import local_settings
from rutile3.data.catalog import PROJECT_ROOT


TOKEN = "RUTILE_RESEARCH_TOKEN"
CODEX_EXE = "RUTILE_RESEARCH_CODEX_EXE"
HOSTS = ("codex", "pi")


def connector_token():
    token = local_settings.value(TOKEN) or ""
    return token if len(token) >= 32 and token.isascii() else None


def bridge_command(origin):
    return [sys.executable, "-m", "rutile3.mcp_research", "--env-file", str(local_settings.ENV_FILE), "--url", origin]


def prepare_connector(origin):
    with local_settings.LOCK:
        token = connector_token() or token_urlsafe(32)
        if local_settings.file_value(TOKEN) != token:
            local_settings.save(TOKEN, token)
    return bridge_command(origin)


def codex_executable():
    saved = local_settings.value(CODEX_EXE)
    if saved:
        try:
            return validate_command([saved])[0]
        except ValueError:
            return None
    candidates = [shutil.which("codex")]
    if os.name == "nt":
        app_data = os.environ.get("LOCALAPPDATA")
        if app_data:
            candidates.insert(0, Path(app_data) / "Programs/OpenAI/Codex/bin/codex.exe")
    return next((str(Path(path).resolve()) for path in candidates
                 if path and Path(path).is_file() and Path(path).suffix.lower() not in {".ps1", ".bat", ".cmd"}), None)


def command_key(host):
    return f"RUTILE_RESEARCH_{host.upper()}_COMMAND"


def validate_command(command):
    if (not isinstance(command, list) or not command or
            any(not isinstance(part, str) or "\x00" in part for part in command) or
            not Path(command[0]).is_absolute() or not Path(command[0]).is_file() or
            Path(command[0]).suffix.lower() in {".ps1", ".bat", ".cmd"}):
        raise ValueError("Enter an absolute executable path and pass arguments as a JSON array of strings.")
    return command


def custom_command(host):
    raw = local_settings.value(command_key(host))
    if not raw:
        return None
    try:
        return validate_command(json.loads(raw))
    except ValueError:
        raise ValueError(f"The custom {host} launcher is invalid. Check its executable and arguments in Settings.") from None


def managed_codex(origin, folder, scratch):
    executable = codex_executable()
    if not executable:
        raise ValueError("Install Codex or enter its executable path in Research agent settings.")
    bridge, *args = prepare_connector(origin)
    registration = f"{{command={json.dumps(bridge, ensure_ascii=False)},args={json.dumps(args, ensure_ascii=False)},required=true}}"
    filesystem = {
        ":root": "read", ":minimal": "read",
        str(folder): "read", str(scratch): "write", sys.base_prefix: "read",
        str(local_settings.ENV_FILE): "deny", str(local_settings.ENV_FILE.parent / ".env.tmp-*"): "deny",
        str(Path.home() / ".codex" / "auth.json"): "deny",
    }
    permissions = ",".join(f"{json.dumps(path, ensure_ascii=False)}={json.dumps(access)}"
                           for path, access in filesystem.items())
    command = [executable, "-c", f"mcp_servers.rutile={registration}",
               "-c", 'approval_policy="never"', "-c", 'web_search="live"',
               "-c", 'default_permissions="rutile-research"',
               "-c", f"permissions.rutile-research.filesystem={{{permissions}}}",
               "-c", "permissions.rutile-research.network.enabled=false"]
    return [*command, "app-server"]


def register_codex(origin, executable=None):
    if executable:
        validate_command([executable])
    executable = executable or codex_executable()
    if not executable:
        raise ValueError("Install Codex or enter its executable path first.")
    bridge = prepare_connector(origin)
    try:
        result = subprocess.run([executable, "mcp", "add", "rutile", "--", *bridge], cwd=PROJECT_ROOT,
                                capture_output=True, timeout=20,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError("Rutile could not run Codex MCP setup. Use the manual connection steps below.") from None
    if result.returncode:
        raise ValueError("Codex rejected the MCP setup. Use the manual connection steps below.")


def save_launcher(host, command):
    local_settings.save(command_key(host), json.dumps(validate_command(command)) if command else None)


def settings(origin):
    launchers = {}
    for host in HOSTS:
        try:
            launchers[host] = {"available": bool(custom_command(host)), "custom": bool(local_settings.value(command_key(host)))}
        except ValueError:
            launchers[host] = {"available": False, "custom": True}
    return {"codex_executable": codex_executable(), "launchers": launchers,
            "connector_configured": bool(connector_token()), "bridge": bridge_command(origin)}
