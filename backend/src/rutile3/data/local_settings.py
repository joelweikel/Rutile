"""Private settings shared by the loopback app and its stdio connector."""
from io import StringIO
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import RLock

from dotenv import dotenv_values
from dotenv.parser import parse_stream

from rutile3.jobs.storage import retry_io


ENV_FILE = Path(__file__).resolve().parents[4] / ".env"
DYNAMIC_KEYS = {"MP_API_KEY", "RUTILE_RESEARCH_TOKEN", "RUTILE_RESEARCH_CODEX_COMMAND",
                "RUTILE_RESEARCH_PI_COMMAND", "RUTILE_RESEARCH_CODEX_EXE"}
LOCK = RLock()


def file_value(name, path=None):
    return dotenv_values(path or ENV_FILE, interpolate=False).get(name) or None


def value(name):
    return file_value(name) or os.environ.get(name)


def save(name, setting):
    with LOCK:
        path = ENV_FILE
        source = retry_io(lambda: path.read_text(encoding="utf-8")) if path.exists() else ""
        content = "".join(entry.original.string for entry in parse_stream(StringIO(source)) if entry.key != name)
        if setting is not None:
            escaped = setting.replace("\\", "\\\\").replace("'", "\\'")
            if content and not content.endswith("\n"):
                content += "\n"
            content += f"{name}='{escaped}'\n"
        if content == source:
            return
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                prefix=".env.tmp-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        try:
            retry_io(lambda: temporary.replace(path))
        finally:
            retry_io(lambda: temporary.unlink(missing_ok=True))
