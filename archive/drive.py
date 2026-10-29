# =====================================================================
#  drive_controller.py - Motorsteuerung per Joystick (ESP32-C5, MicroPython)
#
#  Start:  mpremote connect /dev/ttyACM0 run drive_controller.py
#
#  Anschluesse:
#     Joystick X (links/rechts) -> IO3  (ADC1_CH2)
#     Joystick Y (vor/zurueck)  -> IO1  (ADC1_CH0)
#       WICHTIG: IO0 hat beim ESP32-C5 KEINEN ADC. Nur IO1..IO6 gehen.
#
#     Motor vorne rechts: PWM IO10, DIR IO9
#     Motor vorne links : PWM IO5,  DIR IO4  (spiegelbildlich -> invertiert)
#
#  Sicherheit:
#     - Harte Begrenzung auf MAX_POWER = 40 % der vollen Leistung
#     - Weicher Anlauf/Auslauf
#     - Richtungswechsel erst im Stillstand
#     - Ctrl-C oder Fehler -> Motoren sofort aus
# =====================================================================

import time
from machine import Pin, PWM, ADC

# ------------------------------------------------------------ Einstellungen
MAX_POWER = 90       # % der vollen Leistung (harte Obergrenze, vor UND zurueck)
PWM_FREQ = 1000       # Hz
DEADZONE = 10         # % Totzone um die Mittelstellung
RAMP_STEP = 1.5       # max. Aenderung pro Zyklus in % Volllast (Anlauf)
LOOP_MS = 50          # 20 Hz Regelzyklus
SAMPLES = 4           # ADC-Mittelung
CAL_MS = 1500         # Kalibrierzeit beim Start (Joystick loslassen!)
RANGE_MS = 5000       # ms zum Lernen der Endanschlaege

X_PIN = 3
Y_PIN = 1

# Falls Fahrtrichtung vertauscht ist, hier umdrehen:
FORWARD_LEVEL = 1     # DIR-Pegel fuer "vorwaerts" (rechter Motor)
SWAP_STEER = True     # True, falls links/rechts vertauscht ist
STEER_GAIN_LEFT = 0.5   # Lenkstaerke Joystick nach links (1.0 = voll)
STEER_GAIN_RIGHT = 0.3  # Lenkstaerke Joystick nach rechts (kleiner = sanfter)


# ---------------------------------------------------------------- Motor
class Motor:
    def __init__(self, name, pwm_pin, dir_pin, invert=False):
        self.name = name
        self.pwm = PWM(Pin(pwm_pin), freq=PWM_FREQ, duty_u16=0)
        self.dir = Pin(dir_pin, Pin.OUT)
        self.invert = invert
        self.fwd = None

    def set_direction(self, forward):
        level = FORWARD_LEVEL if forward else 1 - FORWARD_LEVEL
        if self.invert:
            level = 1 - level
        self.dir.value(level)
        self.fwd = forward

    def set_signed(self, percent):
        """percent: % der Volllast mit Vorzeichen (-: rueckwaerts), begrenzt auf MAX_POWER."""
        fwd = percent >= 0
        if fwd != self.fwd:
            self.pwm.duty_u16(0)          # erst aus, dann Richtung umschalten
            self.set_direction(fwd)
        self.set_power(abs(percent))

    def set_power(self, percent):
        """percent: 0..100 der vollen Leistung, hart auf MAX_POWER begrenzt."""
        percent = max(0, min(MAX_POWER, percent))
        self.pwm.duty_u16(int(percent * 65535 / 100))

    def stop(self):
        self.pwm.duty_u16(0)


motor_r = Motor("rechts", pwm_pin=10, dir_pin=9)
motor_l = Motor("links", pwm_pin=5, dir_pin=4, invert=True)


def stop_all():
    motor_r.stop()
    motor_l.stop()


# ------------------------------------------------------------------ ADC
def adc_init(pin):
    a = ADC(Pin(pin), atten=ADC.ATTN_11DB)   # 0 ... ~3,3 V
    a.read_u16()
    return a


def read_avg(adc):
    return sum(adc.read_u16() for _ in range(SAMPLES)) // SAMPLES


def axis_percent(raw, center, lo, hi):
    """Rohwert -> -100..+100 mit Totzone, skaliert auf die gelernten Anschlaege."""
    if raw >= center:
        span = max(1, hi - center)
    else:
        span = max(1, center - lo)
    p = (raw - center) * 100 / span
    if -DEADZONE < p < DEADZONE:
        return 0
    return max(-100, min(100, p))


def ramp(current, target):
    if current < target:
        return min(target, current + RAMP_STEP)
    return max(target, current - RAMP_STEP)


# ---------------------------------------------------------------- Start
print("--- Joystick-Steuerung, Limit %d %% ---" % MAX_POWER)
stop_all()

try:
    adc_x = adc_init(X_PIN)
    adc_y = adc_init(Y_PIN)
except Exception as e:
    print("ADC-Fehler:", e)
    print("X muss auf IO3, Y auf IO1 liegen (IO0 hat keinen ADC).")
    stop_all()
    raise SystemExit

print("Joystick loslassen - kalibriere ...")
sx = sy = n = 0
t_end = time.ticks_add(time.ticks_ms(), CAL_MS)
while time.ticks_diff(t_end, time.ticks_ms()) > 0:
    sx += adc_x.read_u16()
    sy += adc_y.read_u16()
    n += 1
    time.sleep_ms(10)
center_x = sx // n
center_y = sy // n
print("Mitte: X=%d (%.2f V)  Y=%d (%.2f V)"
      % (center_x, center_x / 65535 * 3.3, center_y, center_y / 65535 * 3.3))

# --- Endanschlaege lernen: Joystick in alle Richtungen voll ausschlagen ---
print("Jetzt Joystick %d s lang in ALLE Richtungen voll ausschlagen ..."
      % (RANGE_MS // 1000))
min_x = max_x = center_x
min_y = max_y = center_y
t_end = time.ticks_add(time.ticks_ms(), RANGE_MS)
while time.ticks_diff(t_end, time.ticks_ms()) > 0:
    rx = adc_x.read_u16()
    ry = adc_y.read_u16()
    min_x = min(min_x, rx)
    max_x = max(max_x, rx)
    min_y = min(min_y, ry)
    max_y = max(max_y, ry)
    time.sleep_ms(5)

# Zu kleiner Bereich (nicht bewegt) -> Standardwerte nehmen
MIN_SPAN = 4000
if center_x - min_x < MIN_SPAN:
    min_x = 0
if max_x - center_x < MIN_SPAN:
    max_x = 65535
if center_y - min_y < MIN_SPAN:
    min_y = 0
if max_y - center_y < MIN_SPAN:
    max_y = 65535
print("Bereich X: %d ... %d   Y: %d ... %d" % (min_x, max_x, min_y, max_y))
print("Joystick loslassen!")
time.sleep_ms(1000)
print("Los geht's. Ctrl-C beendet.")

motor_r.set_direction(True)
motor_l.set_direction(True)
cur_l = 0.0          # aktuelle Leistung, mit Vorzeichen (-: rueckwaerts)
cur_r = 0.0
tick = 0

try:
    while True:
        x = axis_percent(read_avg(adc_x), center_x, min_x, max_x)
        y = axis_percent(read_avg(adc_y), center_y, min_y, max_y)

        gain = STEER_GAIN_RIGHT if x > 0 else STEER_GAIN_LEFT
        steer = (-x if SWAP_STEER else x) * gain             # -100..100

        # Panzerlenkung: ein Motor schneller/vorwaerts, der andere
        # langsamer bzw. in die Gegenrichtung (Drehen auf der Stelle moeglich)
        t_l = max(-100, min(100, y + steer)) * MAX_POWER / 100
        t_r = max(-100, min(100, y - steer)) * MAX_POWER / 100

        # weicher Anlauf/Auslauf, laeuft linear durch 0 -> Richtungswechsel
        # passiert automatisch bei (fast) Stillstand
        cur_l = ramp(cur_l, t_l)
        cur_r = ramp(cur_r, t_r)
        motor_l.set_signed(cur_l)
        motor_r.set_signed(cur_r)

        tick += 1
        if tick % 10 == 0:
            print("X %+4d  Y %+4d  L %+5.1f%%  R %+5.1f%%" % (x, y, cur_l, cur_r))

        time.sleep_ms(LOOP_MS)

except KeyboardInterrupt:
    print("Abbruch")
finally:
    stop_all()
    print("Motoren gestoppt")