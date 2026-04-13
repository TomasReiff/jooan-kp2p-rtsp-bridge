#!/usr/bin/env bash

set -euo pipefail

# Disable Python's stdout/stderr buffering so log messages from all bridge
# processes appear immediately in the Home Assistant add-on log viewer.
export PYTHONUNBUFFERED=1

exec python3 /app/addon_launcher.py
