#!/bin/bash
# Double-click to start PhonePad. The first run sets up a private Python environment.
cd "$(dirname "$0")/desktop" || exit 1

fail() {
  echo
  echo "PhonePad stopped with an error."
  read -n 1 -s -r -p "Press any key to close."
  exit 1
}

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is not installed. Get it from https://www.python.org/downloads/"
  fail
fi

if [ ! -x .venv/bin/python ]; then
  echo "Setting up PhonePad for the first time, this takes a minute..."
  python3 -m venv .venv || fail
fi

# Install dependencies on the first run and again whenever requirements.txt changes.
# Ignore personal pip config, so a broken extra index elsewhere can't stall the install.
export PIP_CONFIG_FILE=/dev/null
if ! cmp -s requirements.txt .venv/requirements.installed; then
  .venv/bin/python -m pip install --disable-pip-version-check -q -r requirements.txt || fail
  cp requirements.txt .venv/requirements.installed
fi

.venv/bin/python main.py "$@" || fail
