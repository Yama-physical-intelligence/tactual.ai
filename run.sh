#!/bin/zsh
# Usage: ./run.sh [--dry-run] [--calibrate] [--hand Left] [--anchor tip] [--camera 1]
cd "${0:a:h}"
if [[ ! -d .venv ]]; then
  python3.11 -m venv .venv && .venv/bin/pip install -q -r requirements.txt
fi
exec .venv/bin/python -m fingering "$@" 2> >(grep --line-buffered -vE '^(I0000|W0000|INFO: Created)' >&2)
