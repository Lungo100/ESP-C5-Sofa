#!/usr/bin/env bash
# Oeffnet die MicroPython-REPL auf dem ESP32-C5.
# Beenden:  Ctrl-]   (oder Ctrl-x bei mpremote)
set -e
PORT="${1:-/dev/ttyACM0}"
cd "$(dirname "$0")"
exec .venv/bin/mpremote connect "$PORT" repl
