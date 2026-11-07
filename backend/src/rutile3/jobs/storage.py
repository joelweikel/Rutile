"""Short JSON reads and atomic writes tolerant of Windows sharing locks."""
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import sleep


def retry_io(operation, attempts=9):
    for attempt in range(attempts):
        try:
            return operation()
        except PermissionError:
            if attempt == attempts-1:
                raise
            sleep(min(.01 * 2**attempt, .16))


def read_json(path):
    # Close the handle before returning, particularly before streaming HTTP data.
    return retry_io(lambda: json.loads(path.read_text(encoding="utf-8")))


def write_json(path, value):
    content = json.dumps(value, allow_nan=False)
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                            prefix=path.stem+"-", suffix=".tmp", delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(content)
    try:
        retry_io(lambda: temporary.replace(path))
    finally:
        if temporary.exists():
            retry_io(temporary.unlink)
