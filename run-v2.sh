#!/usr/bin/env bash
set -e
source "$(dirname "$0")/.venv/bin/activate"
exec python ui_v2/app.py "$@"
