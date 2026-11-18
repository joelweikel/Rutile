"""Project public host notifications into a bounded run transcript."""
from time import monotonic, time

from rutile3.data import local_settings


TOOLS = {
    "get_reference_request": "Read the research targets",
    "search_materials_project": "Queried Materials Project",
    "stage_phase_data_proposal": "Submitted a finding",
}
CODEX_ITEMS = {
    "webSearch": "Searching the web",
    "commandExecution": "Running a command",
    "fileChange": "Updating research files",
}
OUTPUT_LIMIT = 24_000


class ResearchActivity:
    def __init__(self, publish):
        self.publish = publish
        self.started = monotonic()
        self.last_publish = 0
        self.last_report = None
        self.secrets = [value for name in ("MP_API_KEY", "RUTILE_RESEARCH_TOKEN")
                        if (value := local_settings.value(name))]
        self.output = ""
        self.events = []
        self.item = None
        self.turn = None
        self.codex_baseline = None
        self.pi_text = False
        self.tokens = None
        self.phase = "starting"
        self.dirty = False

    def event(self, label):
        if self.events and self.events[-1]["label"] == label:
            return
        self.events = [*self.events[-19:], {"at": time(), "label": label}]
        self.dirty = True

    def append(self, content, *, new_message=False):
        if isinstance(content, str) and content:
            prefix = "\n\n" if new_message and self.output else ""
            self.output = (self.output + prefix + content)[-OUTPUT_LIMIT:]
            self.dirty = True

    def usage(self, tokens):
        if type(tokens) is int and tokens >= 0:
            self.tokens = tokens
            self.last_report = round(monotonic() - self.started, 2)
            self.dirty = True

    def codex(self, message):
        method = message.get("method")
        params = message.get("params") or {}
        item = params.get("item") or {}
        if method == "turn/started":
            self.phase = "running"
            self.turn = (params.get("turn") or {}).get("id")
            self.event("Codex started the research turn")
            return
        if self.phase != "running" or self.turn and params.get("turnId") not in {self.turn, None}:
            return
        if method == "item/agentMessage/delta":
            item_id = params.get("itemId")
            self.append(params.get("delta"), new_message=item_id != self.item)
            self.item = item_id
        elif method == "item/completed" and item.get("type") == "agentMessage" and item.get("id") != self.item:
            self.append(item.get("text"), new_message=True)
            self.item = item.get("id")
        elif method == "item/started":
            kind = item.get("type")
            label = CODEX_ITEMS.get(kind)
            if kind == "mcpToolCall":
                label = TOOLS.get(item.get("tool"), "Calling an MCP tool")
            if label:
                self.event(label)
        elif method == "thread/tokenUsage/updated":
            usage = params.get("tokenUsage") or {}
            last = (usage.get("last") or {}).get("outputTokens")
            total = (usage.get("total") or {}).get("outputTokens")
            if type(last) is int and type(total) is int:
                if self.codex_baseline is None:
                    self.codex_baseline = max(0, total - last)
                self.usage(max(0, total - self.codex_baseline))

    def pi(self, message):
        kind = message.get("type")
        if kind == "agent_start":
            self.phase = "running"
            self.event("Pi started the research turn")
        elif kind == "message_update":
            delta = message.get("assistantMessageEvent") or {}
            if delta.get("type") == "text_delta":
                self.append(delta.get("delta"), new_message=not self.pi_text)
                self.pi_text = True
        elif kind == "message_end":
            assistant = message.get("message") or {}
            if assistant.get("role") == "assistant":
                if not self.pi_text:
                    output = "\n".join(part.get("text", "") for part in assistant.get("content", [])
                                       if part.get("type") == "text")
                    self.append(output, new_message=True)
                self.pi_text = False
                tokens = (assistant.get("usage") or {}).get("output")
                if type(tokens) is int and tokens >= 0:
                    self.usage((self.tokens or 0) + tokens)
        elif kind == "tool_execution_start":
            self.event(TOOLS.get(message.get("toolName"), "Running an agent tool"))

    def flush(self, *, force=False):
        elapsed = monotonic() - self.started
        if not force and (not self.dirty or elapsed - self.last_publish < .35):
            return
        output = self.output
        for secret in self.secrets:
            output = output.replace(secret, "[redacted]")
            # Keep a credential split across successive deltas out of snapshots.
            for length in range(min(len(secret) - 1, len(output)), 3, -1):
                if output.endswith(secret[:length]):
                    output = output[:-length]
                    break
        self.publish({"phase": self.phase, "output": output, "events": self.events,
                      "output_tokens": self.tokens, "usage_elapsed_s": self.last_report,
                      "ended_elapsed_s": round(elapsed, 2) if force else None})
        self.dirty = False
        self.last_publish = elapsed
