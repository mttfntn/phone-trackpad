#!/bin/bash
# Double-click to start Phone Trackpad. The first run sets up a private Python environment.
cd "$(dirname "$0")/desktop" || exit 1

fail() {
  echo
  echo "Phone Trackpad stopped with an error."
  read -n 1 -s -r -p "Press any key to close."
  exit 1
}

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is not installed. Get it from https://www.python.org/downloads/"
  fail
fi

if [ ! -x .venv/bin/python ]; then
  # Same minimum as MIN_PYTHON in desktop/version.py.
  if ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
    echo "Phone Trackpad needs Python 3.10 or newer; python3 is $(python3 --version 2>&1)."
    echo "Get a newer one from https://www.python.org/downloads/"
    fail
  fi
  echo "Setting up Phone Trackpad for the first time, this takes a minute..."
  python3 -m venv .venv || fail
fi

# Install dependencies on the first run and again whenever requirements.txt changes.
# The marker lives in .venv/bin (Windows uses .venv\Scripts), so a folder that was also set up
# on Windows still gets the Mac packages installed.
# Ignore personal pip config, so a broken extra index elsewhere can't stall the install.
export PIP_CONFIG_FILE=/dev/null
if ! cmp -s requirements.txt .venv/bin/requirements.installed; then
  .venv/bin/python -m pip install --disable-pip-version-check -q -r requirements.txt || fail
  cp requirements.txt .venv/bin/requirements.installed
fi

.venv/bin/python main.py "$@" || fail
