# =====================================================================
#  drive_controller.py - Joystick-Steuerung (ESP32-C5, MicroPython)
#  Fahrzeug: 2 angetriebene Vorderraeder + hinten Schwenkrollen
#
#  Start:     mpremote connect /dev/ttyACM0 run drive_controller.py
#  Autostart: mpremote connect /dev/ttyACM0 cp drive_controller.py :main.py
#
#  Anschluesse:
#     Joystick X (links/rechts) -> IO3  (ADC1_CH2)
#     Joystick Y (vor/zurueck)  -> IO1  (ADC1_CH0)   (IO0 hat KEINEN ADC!)
#     Motor rechts: PWM IO10, DIR IO9,  BREMS IO8
#     Motor links : PWM IO5,  DIR IO4,  BREMS IO23  (spiegelbildlich)
#
#  Lenkung:
#     - Waehrend der Fahrt: Kurvenfahrt. Das kurvenaeussere Rad wird
#       schneller (bis +STEER_BOOST), das innere langsamer bis Stillstand.
#       Das Innenrad dreht NIE rueckwaerts.
#     - Im Stand / bei sehr kleinem Tempo: weich uebergehend in Drehen
#       auf der Stelle (ein Rad vor, das andere zurueck).
#     - Lenkkurve: kleine Ausschlaege lenken fein, grosse immer staerker.
#
#  Bremsen:
#     - Hebel loslassen  -> schneller Auslauf, dann Bremse an
#       (BRAKE_HOLD = True haelt das Fahrzeug im Stand).
#     - Richtungswechsel -> erst bremsen, dann DIR umschalten.
#
#  Sicherheit: weicher Anlauf, Ctrl-C/Fehler -> Motoren sofort aus + Bremse.
#
#  Angepasst an MicroPython v1.29.0 (ESP32-C5):
#     - ADC nimmt atten/width NICHT als Konstruktor-Argument, sondern
#       nur als Methode  -> adc_init() probiert beides.
#     - PWM: duty_u16 wird benutzt wenn vorhanden, sonst 10-Bit duty().
# =====================================================================

import time
from machine import Pin, PWM, ADC

# ------------------------------------------------------------ Einstellungen
PWM_FREQ = 1000       # Hz
DEADZONE = 10         # % Totzone um die Mittelstellung
RAMP_STEP = 8.0       # max. Aenderung pro Zyklus in % Volllast (Anlauf/Auslauf)
LOOP_MS = 50          # 20 Hz Regelzyklus
SAMPLES = 4           # ADC-Mittelung
CAL_MS = 1500         # Kalibrierzeit Mittelstellung (Joystick loslassen!)
RANGE_MS = 5000       # Zeit zum Lernen der Endanschlaege

# --- Lenkung ---
STEER_EXPO = 2.0      # Lenkkurve: 1.0 = linear, 2.0 = fein am Anfang, dann
                      # immer staerker (3.0 = noch feiner in der Mitte)
STEER_GAIN_LEFT = 1.0   # max. Lenkstaerke nach links  (1.0 = Innenrad bis 0)
STEER_GAIN_RIGHT = 1.0  # max. Lenkstaerke nach rechts
STEER_BOOST = 0.5     # Aussenrad wird bis zu 50 % schneller (0.0 = alt)
PIVOT_GAIN = 0.6      # Staerke beim Drehen auf der Stelle (0.0 ... 1.0)
PIVOT_BLEND = 25      # % Tempo, ab dem reine Kurvenfahrt gilt (darunter
                      # fliesst das Drehen auf der Stelle weich ein)

# --- Bremsen ---
BRAKE_ACTIVE_LEVEL = 1  # Pegel, der die Bremse anzieht (1 oder 0)
BRAKE_STEP = 25.0       # % pro Zyklus beim Bremsen (schneller als RAMP_STEP)
BRAKE_MS = 400          # Dauer der Bremsung beim Richtungswechsel
BRAKE_HOLD = True       # Bremse im Stand angezogen lassen (haelt am Hang)

# --- Richtungen anpassen, falls noetig ---
FORWARD_LEVEL = 1     # DIR-Pegel fuer "vorwaerts"
SWAP_STEER = True     # True, falls links/rechts vertauscht ist

X_PIN = 3
Y_PIN = 1
BRAKE_PIN_R = 8       # Bremse rechtes Rad
BRAKE_PIN_L = 23      # Bremse linkes Rad


# ---------------------------------------------------------------- Motor
class Motor:
    def __init__(self, name, pwm_pin, dir_pin, brake_pin=None, invert=False):
        self.name = name
        self.use_u16 = True
        try:
            # moderne Variante: 16-Bit-Tastgrad direkt im Konstruktor
            self.pwm = PWM(Pin(pwm_pin), freq=PWM_FREQ, duty_u16=0)
        except (TypeError, ValueError):
            self.use_u16 = False
            try:
                self.pwm = PWM(Pin(pwm_pin), freq=PWM_FREQ)
            except (TypeError, ValueError):
                self.pwm = PWM(Pin(pwm_pin))
                self.pwm.freq(PWM_FREQ)
            self.pwm.duty(0)
        self.dir = Pin(dir_pin, Pin.OUT)
        self.brake = None
        if brake_pin is not None:
            self.brake = Pin(brake_pin, Pin.OUT)
            self.set_brake(False)
        self.invert = invert
        self.fwd = None

    def set_brake(self, on):
        """Bremse anziehen / loesen (Pegel ueber BRAKE_ACTIVE_LEVEL)."""
        if self.brake is None:
            return
        level = BRAKE_ACTIVE_LEVEL if on else 1 - BRAKE_ACTIVE_LEVEL
        self.brake.value(level)
        self.braking = on

    def set_direction(self, forward):
        level = FORWARD_LEVEL if forward else 1 - FORWARD_LEVEL
        if self.invert:
            level = 1 - level
        self.dir.value(level)
        self.fwd = forward

    def _write(self, percent):
        if self.use_u16:
            self.pwm.duty_u16(int(percent * 65535 / 100))
        else:
            self.pwm.duty(int(percent * 1023 / 100))

    def set_power(self, percent):
        percent = max(0, min(100, percent))
        self._write(percent)

    def set_signed(self, percent):
        """percent: % Volllast mit Vorzeichen (-: rueckwaerts)."""
        fwd = percent >= 0
        if fwd != self.fwd:
            self._write(0)                # erst aus, dann Richtung umschalten
            self.set_direction(fwd)
        self.set_power(abs(percent))

    def stop(self):
        self._write(0)


motor_r = Motor("rechts", pwm_pin=10, dir_pin=9, brake_pin=BRAKE_PIN_R)
motor_l = Motor("links", pwm_pin=5, dir_pin=4, brake_pin=BRAKE_PIN_L, invert=True)


def stop_all():
    motor_r.stop()
    motor_l.stop()
    motor_r.set_brake(BRAKE_HOLD)
    motor_l.set_brake(BRAKE_HOLD)


# ------------------------------------------------------------------ ADC
def adc_init(pin):
    try:
        a = ADC(Pin(pin), atten=ADC.ATTN_11DB)   # 0 ... ~3,3 V
    except (TypeError, ValueError):
        a = ADC(Pin(pin))
        a.atten(ADC.ATTN_11DB)
    try:
        a.width(ADC.WIDTH_12BIT)
    except Exception:
        pass
    a.read_u16()
    return a


def read_avg(adc):
    return sum(adc.read_u16() for _ in range(SAMPLES)) // SAMPLES


def axis_percent(raw, center, lo, hi):
    """Rohwert -> -100..+100. Totzone wird herausgerechnet, d.h. direkt
    hinter der Totzone beginnt der Wert bei 0 (fein regelbar)."""
    if raw >= center:
        span = max(1, hi - center)
    else:
        span = max(1, center - lo)
    p = (raw - center) * 100 / span
    p = max(-100, min(100, p))
    a = abs(p)
    if a <= DEADZONE:
        return 0
    a = (a - DEADZONE) * 100 / (100 - DEADZONE)
    return a if p > 0 else -a


def steer_curve(x):
    """-100..100 -> -1.0..+1.0 mit Lenkkurve (fein in der Mitte)."""
    a = abs(x) / 100
    c = a ** STEER_EXPO
    return c if x >= 0 else -c


def ramp(current, target):
    if current < target:
        return min(target, current + RAMP_STEP)
    return max(target, current - RAMP_STEP)


def fast_ramp(current, target):
    """Schneller Auslauf beim Bremsen (BRAKE_STEP statt RAMP_STEP)."""
    if current < target:
        return min(target, current + BRAKE_STEP)
    return max(target, current - BRAKE_STEP)


# ---------------------------------------------------------------- Start
print("--- Joystick-Steuerung (volle Leistung) ---")
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
cur_l = 0.0          # aktuelle Leistung in % Volllast, mit Vorzeichen
cur_r = 0.0
direction = True     # aktuelle Fahrtrichtung
brake_since = 0      # Startzeit der Bremsung beim Richtungswechsel
tick = 0

try:
    while True:
        x = axis_percent(read_avg(adc_x), center_x, min_x, max_x)
        y = axis_percent(read_avg(adc_y), center_y, min_y, max_y)

        # ---- Lenkung: -1.0 ... +1.0 mit Lenkkurve ----
        gain = STEER_GAIN_RIGHT if x > 0 else STEER_GAIN_LEFT
        s = steer_curve(x) * gain
        if SWAP_STEER:
            s = -s

        speed = abs(y)                     # 0 ... 100
        sgn = 1 if y >= 0 else -1          # Fahrtrichtung
        se = s * sgn                       # Lenkung rueckwaerts gleichsinnig

        # ---- Kurvenfahrt: Aussenrad schneller, Innenrad langsamer ----
        # Das Aussenrad bekommt bis zu STEER_BOOST zusaetzlich Leistung,
        # das Innenrad geht bis auf 0 zurueck (dreht nie rueckwaerts).
        outer = min(100.0, speed * (1 + STEER_BOOST * abs(se)))
        inner = speed * (1 - abs(se))
        if se >= 0:
            c_l, c_r = outer * sgn, inner * sgn
        else:
            c_l, c_r = inner * sgn, outer * sgn

        # ---- Drehen auf der Stelle: ein Rad vor, das andere zurueck ----
        p_l = s * 100 * PIVOT_GAIN
        p_r = -p_l

        # ---- weicher Uebergang: Stand = Drehen, Fahrt = Kurve ----
        w = min(1.0, speed / PIVOT_BLEND)
        t_l = w * c_l + (1 - w) * p_l
        t_r = w * c_r + (1 - w) * p_r

        # ---- Fahrtrichtung wechseln? -> erst bremsen, dann umschalten ----
        want_forward = direction if speed == 0 else (y > 0)
        brake_on = False

        if want_forward != direction:
            # 1) Leistung schnell auf 0
            cur_l = fast_ramp(cur_l, 0)
            cur_r = fast_ramp(cur_r, 0)
            if cur_l == 0 and cur_r == 0:
                # 2) Bremse anziehen und kurz warten
                brake_on = True
                now = time.ticks_ms()
                if brake_since == 0:
                    brake_since = now
                elif time.ticks_diff(now, brake_since) >= BRAKE_MS:
                    # 3) Bremse loesen und Richtung umschalten
                    brake_on = False
                    direction = want_forward
                    motor_l.set_direction(direction)
                    motor_r.set_direction(direction)
                    brake_since = 0

        elif speed == 0:
            # Hebel losgelassen: auslaufen lassen und bremsen
            cur_l = fast_ramp(cur_l, 0)
            cur_r = fast_ramp(cur_r, 0)
            if cur_l == 0 and cur_r == 0:
                brake_on = BRAKE_HOLD
            brake_since = 0

        else:
            # normale Fahrt mit weichem Anlauf
            cur_l = ramp(cur_l, t_l)
            cur_r = ramp(cur_r, t_r)
            brake_since = 0

        motor_l.set_brake(brake_on)
        motor_r.set_brake(brake_on)
        motor_l.set_signed(cur_l)
        motor_r.set_signed(cur_r)

        tick += 1
        if tick % 10 == 0:
            print("X %+4d  Y %+4d  L %+6.1f%%  R %+6.1f%%  %s%s"
                  % (x, y, cur_l, cur_r,
                     "vor" if direction else "rueck",
                     "  BREMS" if brake_on else ""))

        time.sleep_ms(LOOP_MS)

except KeyboardInterrupt:
    print("Abbruch")
finally:
    stop_all()
    print("Motoren gestoppt")
