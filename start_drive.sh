#!/usr/bin/env bash
# =====================================================================
#  start_drive.sh  -  Joystick-Steuerung starten (drive_controller.py)
#
#  Aufruf:   ./start_drive.sh            (Port automatisch suchen)
#            ./start_drive.sh /dev/ttyACM1
#
#  Laedt drive_controller.py als main.py auf das Board und oeffnet die
#  Konsole. main.py startet auf dem Board automatisch.
#  Beenden:  Ctrl-]  (oder Ctrl-C)
# =====================================================================
set -e
cd "$(dirname "$0")"

PORT="${1:-}"
if [ -z "$PORT" ]; then
    PORT=$(ls /dev/ttyACM* 2>/dev/null | head -n 1 || true)
fi
if [ -z "$PORT" ]; then
    echo "Kein ESP32 gefunden (/dev/ttyACM* fehlt)."
    echo "Board einstecken und nochmal starten."
    exit 1
fi

echo "Port:   $PORT"
echo "Skript: drive_controller.py  (X = IO3, Y = IO1)"
echo

.venv/bin/mpremote connect "$PORT" cp drive_controller.py :main.py

echo "Konsole oeffnen (Beenden mit Ctrl-]) ..."
exec .venv/bin/mpremote connect "$PORT" repl
