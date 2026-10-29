# =====================================================================
#  Fahrzeug-Steuerung  -  ESP32-C5 mit MicroPython
#
#  Motoren der Vorderseite:
#
#    Position         PWM (Geschwindigkeit)   DIR (Richtung)
#    ---------------- ----------------------- --------------
#    vorne rechts     IO10                    IO9
#    vorne links      IO5                     IO4
#
#  Beide Motoren laufen immer gleich schnell und in dieselbe Richtung.
#  Links ist spiegelbildlich montiert, deshalb wird dort der DIR-Pegel
#  umgedreht (Motor(..., invert=True)).
#
#  Gesamtdrosselung ueber THROTTLE (aktuell 20 % der vollen Leistung).
#
#  Ablauf: langsam -> schnell -> langsam -> Richtungswechsel, endlos.
# =====================================================================

import time
from machine import Pin, PWM

# ------------------------------------------------------------- PWM-Basis
PWM_FREQ = 1000      # PWM-Frequenz in Hz (1 kHz)
PWM_MAX = 1023       # 10-Bit-Aufloesung -> Tastgrad 0 ... 1023

# ----------------------------------------------------------- Fahrprofil
THROTTLE = 20        # % Gesamtdrosselung: 20 = nur 20 % der vollen Leistung
MIN_SPEED = 10       # % kleinste Drehzahl (Anfang/Ende jeder Rampe, vor Drosselung)
MAX_SPEED = 100      # % groesste Drehzahl (vor Drosselung)
RAMP_STEPS = 45      # Zwischenstufen pro Rampe (hoch und runter gleich)
RAMP_TIME = 1.4      # s Dauer einer kompletten Rampe
RAMP_DELAY = RAMP_TIME / RAMP_STEPS
HOLD_TIME = 1.0      # s Haltezeit auf MAX bzw. MIN


def percent_to_duty(percent):
    """Prozent (0 ... 100) -> Tastgrad 0 ... PWM_MAX, inklusive Drosselung."""
    percent = percent * THROTTLE / 100
    return int(percent * PWM_MAX / 100 + 0.5)


class Motor:
    """Ein DC-Motor an einem PWM-Pin (Drehzahl) und einem DIR-Pin (Richtung)."""

    def __init__(self, name, pwm_pin, dir_pin, invert=False):
        self.name = name
        # LEDC-Kanal fuer die Geschwindigkeit
        self.pwm = PWM(Pin(pwm_pin))
        self.pwm.freq(PWM_FREQ)
        self.pwm.duty(0)                    # startet stehend
        # einfacher Digitalausgang fuer die Richtung (kein PWM!)
        self.dir = Pin(dir_pin, Pin.OUT)
        self.duty = 0                       # aktueller Tastgrad 0 ... PWM_MAX
        # Spiegelbildlich montierte Motoren drehen sonst entgegengesetzt
        self.invert = invert

    def set_duty(self, duty):
        """Tastgrad direkt setzen und auf 0 ... PWM_MAX begrenzen."""
        if duty < 0:
            duty = 0
        if duty > PWM_MAX:
            duty = PWM_MAX
        self.duty = duty
        self.pwm.duty(duty)

    def set_direction(self, forward):
        """Richtung setzen: DIR = 0 -> vorwaerts, DIR = 1 -> rueckwaerts.

        Bei invert=True wird der Pegel umgedreht, damit ein spiegelbildlich
        eingebauter Motor physisch in dieselbe Richtung laeuft.
        """
        level = 0 if forward else 1
        if self.invert:
            level = 1 - level
        self.dir.value(level)


# -------------------------------------------------------------- Motoren
# Vorderseite. Jeder Motor hat seinen eigenen DIR-Pin.
MOTOR_FR = Motor("vorne rechts", pwm_pin=10, dir_pin=9)
# Links ist spiegelbildlich montiert -> DIR-Pegel umdrehen, damit beide
# Motoren physisch in dieselbe Richtung laufen.
MOTOR_FL = Motor("vorne links", pwm_pin=5, dir_pin=4, invert=True)

# Liste aller Motoren - hier spaeter "hinten rechts"/"hinten links" ergaenzen
MOTORS = (MOTOR_FR, MOTOR_FL)

direction = True     # True = vorwaerts
speed = 0            # aktueller Tastgrad, gilt fuer alle Motoren


def set_all_duty(duty):
    """Tastgrad auf alle Motoren legen."""
    global speed
    if duty < 0:
        duty = 0
    if duty > PWM_MAX:
        duty = PWM_MAX
    speed = duty
    for m in MOTORS:
        m.set_duty(duty)


def set_speed(percent):
    """Drehzahl in Prozent (0 ... 100) auf alle Motoren legen."""
    set_all_duty(percent_to_duty(percent))


def set_direction(forward=True):
    """Richtung auf alle Motoren legen."""
    global direction
    direction = forward
    for m in MOTORS:
        m.set_direction(forward)


def stop_all():
    """Alle Motoren sofort auf 0 %."""
    set_all_duty(0)


def ramp_to(percent):
    """Rampe in RAMP_STEPS gleich grossen Schritten zum Zielwert.

    Wird fuer Beschleunigen und Entschleunigen benutzt, deshalb sind
    Schrittzahl, Schrittweite und Dauer in beide Richtungen identisch.
    """
    target = percent_to_duty(percent)
    start = speed
    for i in range(1, RAMP_STEPS + 1):
        set_all_duty(start + (target - start) * i // RAMP_STEPS)
        time.sleep(RAMP_DELAY)


# ------------------------------------------------------------- Startlauf
set_direction(True)
set_speed(MIN_SPEED)
print('--- Dauerlauf: langsam -> schnell -> langsam -> Richtungswechsel ---')

try:
    while True:
        # beschleunigen
        ramp_to(MAX_SPEED)
        time.sleep(HOLD_TIME)

        # abbremsen
        ramp_to(MIN_SPEED)
        time.sleep(HOLD_TIME)

        # Richtung wechseln (beide Motoren gleichzeitig)
        set_direction(not direction)
        print('Richtung: %s' % ('vorwaerts' if direction else 'rueckwaerts'))
except KeyboardInterrupt:
    # Ctrl-C in der REPL: kein Weiterlaufen auf dem letzten Tastgrad
    print('Abbruch erkannt')
finally:
    # laeuft auch bei jedem anderen Fehler: Motoren sicher stoppen
    stop_all()
    print('Motoren gestoppt')
