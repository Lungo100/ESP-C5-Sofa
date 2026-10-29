#!/usr/bin/env bash
# =====================================================================
#  start_controller.sh  -  nur Controller auslesen (keine Motoren)
#
#  Aufruf:   ./start_controller.sh            (Port automatisch suchen)
#            ./start_controller.sh /dev/ttyACM1
#
#  Laedt controller.py auf das Board und startet es.
#  Beenden:  Ctrl-C
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

echo "Port:  $PORT"
echo "Skript: controller.py  (nur lesen, X = IO3, Y = IO1)"
echo

exec .venv/bin/mpremote connect "$PORT" run controller.py
