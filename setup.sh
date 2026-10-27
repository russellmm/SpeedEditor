#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$(readlink -f -- "$0")")"
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
printf 'Ready. Launch with ./run.sh or inspect with ./run.sh doctor\n'
