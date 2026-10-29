# ESP-C5 Sofa

Joystick-gesteuertes Fahrzeug auf Basis eines **ESP32-C5** mit **MicroPython**.

Zwei angetriebene Vorderräder, hinten Schwenkrollen (Tank-Lenkung). Gesteuert
wird über einen analogen Joystick; die Logik läuft direkt auf dem Mikrocontroller
(`drive_controller.py` wird als `main.py` aufs Board kopiert).

## Verkabelung

| Funktion            | Pin  |
| ------------------- | ---- |
| Joystick X (lenken) | IO3  (ADC1_CH2) |
| Joystick Y (fahren) | IO1  (ADC1_CH0) |
| Motor rechts: PWM   | IO10 |
| Motor rechts: DIR   | IO9  |
| Motor rechts: Bremse| IO8  |
| Motor links: PWM    | IO5  |
| Motor links: DIR    | IO4  |
| Motor links: Bremse | IO23 |

> **Wichtig:** Der ESP32-C5 hat auf IO0 **keinen** ADC. Joystick-Y muss auf IO1
> liegen (IO1 … IO6 sind als ADC nutzbar). Der linke Motor ist spiegelbildlich
> montiert und wird daher im Code invertiert.

## Voraussetzungen (Host)

- Python 3.9 oder neuer (getestet mit 3.14)
- Ein per USB angeschlossener ESP32-C5 (erscheint als `/dev/ttyACM0`)

## Setup

```bash
# virtuelle Umgebung anlegen und Tooling installieren
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Damit werden `mpremote` und `pyserial` installiert – alles, was zum Flashen
und Steuern nötig ist.

## MicroPython flashen

Das passende Firmware-Image liegt unter `firmware/`:

```bash
.venv/bin/mpremote flash firmware/ESP32_GENERIC_C5-20260824-v1.29.0.bin
```

> Image-Quelle: MicroPython v1.29.0 für `ESP32_GENERIC_C5`.

## Nutzung

| Skript              | Zweck |
| ------------------- | ----- |
| `./start_drive.sh`  | Joystick-Steuerung starten (kopiert `drive_controller.py` als `main.py` aufs Board, öffnet dann die REPL) |
| `./start_controller.sh` | Nur Joystick auslesen, keine Motoren |
| `./repl.sh`         | MicroPython-REPL öffnen |
| `.venv/bin/python verify.py` | Prüft, ob MicroPython auf dem Board läuft |

Alle Skripte suchen den Port automatisch (`/dev/ttyACM*`). Alternativ lässt sich
der Port als erstes Argument übergeben, z. B. `./start_drive.sh /dev/ttyACM1`.

**Beenden:** `Ctrl-C` (bzw. `Ctrl-]` in der mpremote-REPL). Beim Beenden werden
die Motoren automatisch gestoppt und die Bremsen angezogen.

## Fahrwerks-Ausrichtung (`DRIVE_ORIENTATION`)

Die Antriebsbasis ist nicht fest mit dem Sofa verbunden – das Sofa lässt sich
um 180° auf der Basis drehen. Je nachdem, ob die angetriebenen Räder hinten
oder vorn liegen, fährt sich das Fahrzeug unterschiedlich:

| `DRIVE_ORIENTATION` | Räder       | Verhalten |
| ------------------- | ----------- | --------- |
| `"rear"` (Default)  | angetrieben hinten, Rollen vorn | stabil (Untersteuern) |
| `"front"`           | angetrieben vorn, Rollen hinten | driftig (Übersteuern) |

Die Einstellung steht in `drive_controller.py` und schaltet `DRIVE_SIGN` und
`STEER_SIGN` gemeinsam um (Fahrtrichtung + Lenkrichtung). Ein Laufzeit-Schalter
für den schnellen Wechsel ist vorgesehen, aber noch nicht umgesetzt.

## Ablauf von `drive_controller.py`

1. Beim Start: Joystick loslassen → Mitte wird kalibriert.
2. Dann einige Sekunden in alle Richtungen ausschlagen → Endanschläge werden
   gelernt (Ergebnis wird in `cal.txt` auf dem Board gespeichert).
3. Danach fährt das Fahrzeug: Y-Achse = vor/zurück, X-Achse = lenken
   (Tank-Lenkung mit Kurvenfahrt und Drehen auf der Stelle im Stand).

## Tests und Diagnose

Im Ordner `tests/` liegen Diagnose-Skripte, die per `mpremote run` auf dem Board
gestartet werden:

```bash
.venv/bin/mpremote connect /dev/ttyACM0 run tests/test_motors.py
```

| Skript             | Zweck |
| ------------------ | ----- |
| `tests/test_motors.py` | Einzeltest der beiden Motoren |
| `tests/dir_test.py`    | Richtungs-/ADC-Rohwerte der Achsen |
| `tests/debug_stick.py` | Joystick-Rohwerte und Normalisierung |

## Archiv

In `archive/` liegen ältere bzw. experimentelle Versionen (`drive.py`,
`drive_controller_new.py`, `main_rampe.py`). Sie sind nicht mehr der aktuelle
Stand, werden aber als Referenz aufbewahrt.
