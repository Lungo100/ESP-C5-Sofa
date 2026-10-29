# =====================================================================
#  calibrate_motors.py  -  Motor-Kalibrierung per Tastatur (REPL)
#
#  Zweck:  den linken/rechten Geschwindigkeitsversatz messen, damit beide
#          Raeder optisch gleich schnell laufen. Ergebnis = LEFT_TRIM.
#
#  Ablauf:
#    1) mpremote cp tests/calibrate_motors.py :main.py
#    2) mpremote repl   ->  Skript startet automatisch
#    3) Tasten druecken (siehe Hilfetext unten), bis beide Raeder gleich
#       schnell laufen. Vorwaerts und rueckwaerts getrennt kalibrieren.
#    4) 'q'  ->  Ergebnis ausgeben, Motoren stoppen, Bremse an
#
#  Tasten:
#    f  -> vorwaerts
#    b  -> rueckwaerts
#    +  -> linkes Rad schneller  (Trim +1 %)
#    -  -> linkes Rad langsamer  (Trim -1 %)
#    s  -> Motoren stoppen (Bremse loesen, Tastgrad 0)
#    q  -> beenden (Ergebnis + Bremse an)
#
#  Vorsicht: laedt die Motoren, also Raeder frei / Fahrzeug aufgebockt.
# =====================================================================

import sys
import time
from machine import Pin, PWM

# ------------------------------------------------------------ Einstellungen
PWM_FREQ = 1000      # Hz (wie drive_controller.py)
BASE = 15            # % Grundgeschwindigkeit
STEP = 1             # % Schrittweite pro Tastendruck

# ---------------------------------------------------------------- Anschluesse
MOTOR_R_PWM = 10
MOTOR_R_DIR = 9
MOTOR_R_BRAKE = 8
MOTOR_L_PWM = 5
MOTOR_L_DIR = 4
MOTOR_L_BRAKE = 23
MOTOR_L_INVERTED = True

DIR_FORWARD_LEVEL = 1
BRAKE_ACTIVE_LEVEL = 1


# -------------------------------------------------------------------- Motor
def pwm_init(pin):
    try:
        return PWM(Pin(pin), freq=PWM_FREQ, duty_u16=0), True
    except (TypeError, ValueError):
        p = PWM(Pin(pin))
        try:
            p.freq(PWM_FREQ)
        except Exception:
            pass
        p.duty(0)
        return p, False


class Motor:
    def __init__(self, pwm_pin, dir_pin, brake_pin, inverted=False):
        self.pwm, self.use_u16 = pwm_init(pwm_pin)
        self.dir = Pin(dir_pin, Pin.OUT)
        self.brake = Pin(brake_pin, Pin.OUT)
        self.inverted = inverted
        self.forward = None
        self.brake_on()

    def _duty(self, percent):
        if percent <= 0:
            value = 0
        elif self.use_u16:
            value = int(percent * 655.35)
        else:
            value = int(percent * 10.23)
        if self.use_u16:
            self.pwm.duty_u16(value)
        else:
            self.pwm.duty(value)

    def _set_dir(self, forward):
        level = DIR_FORWARD_LEVEL if forward else 1 - DIR_FORWARD_LEVEL
        if self.inverted:
            level = 1 - level
        self.dir.value(level)
        self.forward = forward

    def brake_on(self):
        self.brake.value(BRAKE_ACTIVE_LEVEL)

    def brake_off(self):
        self.brake.value(1 - BRAKE_ACTIVE_LEVEL)

    def stop(self):
        self._duty(0)
        self.brake_on()


motor_r = Motor(MOTOR_R_PWM, MOTOR_R_DIR, MOTOR_R_BRAKE)
motor_l = Motor(MOTOR_L_PWM, MOTOR_L_DIR, MOTOR_L_BRAKE, MOTOR_L_INVERTED)


def stop_motors():
    motor_r._duty(0)
    motor_l._duty(0)


def stop_all():
    motor_r.stop()
    motor_l.stop()


def drive(direction, trim):
    """Beide Motoren laufen: rechts = BASE, links = BASE * (1 + trim/100)."""
    motor_r._set_dir(direction)
    motor_l._set_dir(direction)
    motor_r.brake_off()
    motor_l.brake_off()
    left = BASE * (1.0 + trim / 100.0)
    motor_r._duty(BASE)
    motor_l._duty(left)
    return left


# ------------------------------------------------------------------ Zustand
trim_fwd = 0
trim_rev = 0
direction = True


def current_trim():
    return trim_rev if not direction else trim_fwd


def print_status():
    left = BASE * (1.0 + current_trim() / 100.0)
    print("dir=%s  trim_fwd=%+d%%  trim_rev=%+d%%  L=%5.1f%%  R=%5.1f%%"
          % ("F" if direction else "B", trim_fwd, trim_rev, left, BASE))


print("--- Motor-Kalibrierung (Tastatur via REPL) ---")
print("  f vor  b zurueck  +/- Trim  s stop  q beenden")
print("  rechts = %d%%, links = %d%% * (1 + trim/100)" % (BASE, BASE))
print()

try:
    drive(direction, current_trim())
    print_status()

    while True:
        c = sys.stdin.read(1)
        if isinstance(c, bytes):
            c = c.decode()
        c = c.strip()
        if not c:
            continue

        if c == "f":
            stop_motors()
            direction = True
            drive(direction, trim_fwd)
        elif c == "b":
            stop_motors()
            direction = False
            drive(direction, trim_rev)
        elif c == "+":
            if direction:
                trim_fwd += STEP
            else:
                trim_rev += STEP
            drive(direction, current_trim())
        elif c == "-":
            if direction:
                trim_fwd -= STEP
            else:
                trim_rev -= STEP
            drive(direction, current_trim())
        elif c == "s":
            stop_motors()
        elif c == "q":
            break
        else:
            print("  (f/b, +/-, s, q)")

        print_status()

except KeyboardInterrupt:
    print("\nAbbruch")

finally:
    stop_all()
    print("--- Ergebnis ---")
    print("LEFT_TRIM_FWD = %d" % trim_fwd)
    print("LEFT_TRIM_REV = %d" % trim_rev)
    print("Motoren gestoppt, Bremse an")
