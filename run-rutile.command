#!/bin/bash
# Double-click in Finder after granting execute permission once (see README).
cd -- "$(dirname -- "$0")" || exit 1

fail() {
    printf '\n%s\n' "$1"
    read -r -p "Press Return to close... "
    exit 1
}

if [ ! -x .venv/bin/python ]; then
    command -v python3.12 >/dev/null 2>&1 || fail "Install Python 3.12, then launch Rutile again."
    printf "Creating Rutile's Python 3.12 environment...\n"
    python3.12 -m venv .venv || fail "Could not create Rutile's Python environment. Check the error above."
fi

.venv/bin/python -c 'import sys; sys.exit(sys.version_info[:2] != (3, 12))' || \
    fail "Rutile requires a Python 3.12 virtual environment in .venv. Check your existing environment."

if ! .venv/bin/python -c 'import rutile3, uvicorn' >/dev/null 2>&1; then
    printf "Installing Rutile's dependencies. This can take a few minutes...\n"
    .venv/bin/python -m pip install -e . || fail "Dependency installation failed. Check the error above."
fi

.venv/bin/python scripts/run_app.py --open "$@"
status=$?
if [ "$status" -ne 0 ] && [ "$status" -ne 130 ]; then
    fail "Rutile could not start. Check the error above."
fi
