import time
from machine import Pin, PWM, ADC

PWM_FREQ = 1000
LOOP_MS = 20
ADC_SAMPLES = 6
DEADZONE = 40
CENTER_MS = 1200
CENTER_SETTLE_MS = 800
CENTER_STABLE = 2500
RANGE_MS = 4000
MIN_SPAN = 4000
DEFAULT_SPAN = 26000
CAL_FILE = "cal.txt"
SAVE_CAL = True
RECALIBRATE = True

MAX_POWER_FWD = 75
MAX_POWER_REV = 50
LEFT_TRIM_FWD = 36
LEFT_TRIM_REV = 40
ACCEL = 60.0
DECEL = 80.0
SOFT_DECEL = 80.0   # sanftes Ausrollen beim Richtungswechsel
BRAKE_MS = 400      # Bremse während Richtungswechsel (ms)
STEER_EXPO = 1.8
STEER_GAIN = 0.35

# Anordnung der angetriebenen Räder relativ zur Sitzrichtung:
#   "rear"  = angetrieben hinten, Rollen vorn   (stabil, Default)
#   "front" = angetrieben vorn,  Rollen hinten  (Drift-Modus)
DRIVE_ORIENTATION = "rear"

if DRIVE_ORIENTATION == "rear":
    DRIVE_SIGN = 1
    STEER_SIGN = 1
else:
    DRIVE_SIGN = -1
    STEER_SIGN = -1

BRAKE_HOLD = True
BRAKE_AT_CENTER = True
BRAKE_ACTIVE_LEVEL = 1
DIR_FORWARD_LEVEL = 1

X_PIN = 3
Y_PIN = 1
MOTOR_R_PWM = 10
MOTOR_R_DIR = 9
MOTOR_R_BRAKE = 8
MOTOR_L_PWM = 5
MOTOR_L_DIR = 4
MOTOR_L_BRAKE = 23
MOTOR_L_INVERTED = True


def adc_init(pin):
    try:
        a = ADC(Pin(pin), atten=ADC.ATTN_11DB)
    except (TypeError, ValueError):
        a = ADC(Pin(pin))
        try:
            a.atten(ADC.ATTN_11DB)
        except Exception:
            pass
    try:
        a.width(ADC.WIDTH_12BIT)
    except Exception:
        pass
    a.read_u16()
    return a


def read_avg(adc):
    total = 0
    for _ in range(ADC_SAMPLES):
        total += adc.read_u16()
    return total // ADC_SAMPLES


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


def axis_percent(raw, center, lo, hi):
    if raw >= center:
        span = hi - center
    else:
        span = center - lo
    if span < 1:
        span = 1
    p = (raw - center) * 100 // span
    if p > 100:
        p = 100
    elif p < -100:
        p = -100
    a = abs(p)
    if a <= DEADZONE:
        return 0
    a = (a - DEADZONE) * 100 // (100 - DEADZONE)
    if a < 2:
        return 0
    return a if p > 0 else -a


def build_curve(expo, gain):
    table = []
    for i in range(-100, 101):
        a = abs(i) / 100.0
        v = int((a ** expo) * 100.0 * gain)
        if v > 100:
            v = 100
        table.append(v if i >= 0 else -v)
    return table


STEER_CURVE = build_curve(STEER_EXPO, STEER_GAIN)


def ramp_cur(cur, target, dt, decel=None):
    """Zeitbasierte Rampe: beschleunigt mit ACCEL, bremst mit decel (default DECEL)."""
    if decel is None:
        decel = DECEL
    if cur < target:
        nxt = cur + ACCEL * dt
        if nxt > target:
            nxt = target
    else:
        nxt = cur - decel * dt
        if nxt < target:
            nxt = target
    if (cur > 0.0 and nxt < 0.0) or (cur < 0.0 and nxt > 0.0):
        nxt = 0.0
    return nxt


class Motor:
    def __init__(self, pwm_pin, dir_pin, brake_pin, inverted=False):
        self.pwm, self.use_u16 = pwm_init(pwm_pin)
        self.dir = Pin(dir_pin, Pin.OUT)
        self.brake = Pin(brake_pin, Pin.OUT)
        self.inverted = inverted
        self.forward = None
        self.cur = 0.0
        self.direction = 1    # logische Fahrtrichtung: 1 vor, -1 rueck
        self.brake_since = 0  # Brems-Timer beim Richtungswechsel
        self.brake_on()

    def _duty(self, percent):
        if percent <= 0.0:
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

    def set_brake(self, on):
        self.brake.value(BRAKE_ACTIVE_LEVEL if on else 1 - BRAKE_ACTIVE_LEVEL)

    def _apply(self, percent):
        self._set_dir(self.direction > 0)
        self._duty(abs(percent))

    def drive_soft(self, target, dt):
        want = self.direction if target == 0.0 else (1 if target > 0.0 else -1)

        if want != self.direction:
            if abs(self.cur) < 0.5:
                # schon im Stand -> Richtung sofort uebernehmen (kein Warten)
                self.direction = want
                self.brake_since = 0
                self.cur = ramp_cur(self.cur, target, dt)
                self.set_brake(False)
                self._apply(self.cur)
            else:
                # abbremsen -> Bremse anziehen -> umschalten
                self.cur = ramp_cur(self.cur, 0.0, dt, decel=SOFT_DECEL)
                if self.cur == 0.0:
                    self.set_brake(True)
                    now = time.ticks_ms()
                    if self.brake_since == 0:
                        self.brake_since = now
                    elif time.ticks_diff(now, self.brake_since) >= BRAKE_MS:
                        self.set_brake(False)
                        self.direction = want
                        self.brake_since = 0
                self._apply(self.cur)
        elif target == 0.0:
            # Neutral: ausrollen + Bremse halten
            self.cur = ramp_cur(self.cur, 0.0, dt, decel=SOFT_DECEL)
            self.set_brake(BRAKE_HOLD if abs(self.cur) < 0.5 else False)
            self.brake_since = 0
            self._apply(self.cur)
        else:
            # normale Fahrt
            self.cur = ramp_cur(self.cur, target, dt)
            self.set_brake(False)
            self.brake_since = 0
            self._apply(self.cur)

    def stop(self):
        self.cur = 0.0
        self._duty(0.0)
        self.brake_on()


motor_r = Motor(MOTOR_R_PWM, MOTOR_R_DIR, MOTOR_R_BRAKE)
motor_l = Motor(MOTOR_L_PWM, MOTOR_L_DIR, MOTOR_L_BRAKE, MOTOR_L_INVERTED)


def stop_all():
    motor_r.stop()
    motor_l.stop()


def read_center_both(adc_x, adc_y, ms):
    while True:
        sx = sy = n = 0
        lo_x = hi_x = None
        lo_y = hi_y = None
        t0 = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), t0) < ms:
            rx = adc_x.read_u16()
            ry = adc_y.read_u16()
            sx += rx
            sy += ry
            if lo_x is None or rx < lo_x:
                lo_x = rx
            if hi_x is None or rx > hi_x:
                hi_x = rx
            if lo_y is None or ry < lo_y:
                lo_y = ry
            if hi_y is None or ry > hi_y:
                hi_y = ry
            n += 1
            time.sleep_ms(5)
        if hi_x - lo_x <= CENTER_STABLE and hi_y - lo_y <= CENTER_STABLE:
            return sx // n, sy // n
        print("Joystick bewegt - bitte loslassen, erneut kalibrieren ...")
        time.sleep_ms(500)


def read_range_both(adc_x, adc_y, cx, cy, ms):
    min_x = max_x = cx
    min_y = max_y = cy
    t0 = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), t0) < ms:
        rx = read_avg(adc_x)
        ry = read_avg(adc_y)
        if rx < min_x:
            min_x = rx
        elif rx > max_x:
            max_x = rx
        if ry < min_y:
            min_y = ry
        elif ry > max_y:
            max_y = ry
        time.sleep_ms(5)
    span_x = min(DEFAULT_SPAN, cx, 65535 - cx)
    span_y = min(DEFAULT_SPAN, cy, 65535 - cy)
    if cx - min_x < MIN_SPAN:
        min_x = cx - span_x
    if max_x - cx < MIN_SPAN:
        max_x = cx + span_x
    if cy - min_y < MIN_SPAN:
        min_y = cy - span_y
    if max_y - cy < MIN_SPAN:
        max_y = cy + span_y
    return min_x, max_x, min_y, max_y


def load_cal():
    try:
        with open(CAL_FILE, "r") as f:
            parts = f.read().split(",")
        if len(parts) != 6:
            return None
        v = [int(p) for p in parts]
        if v[0] < 0 or v[0] > 65535 or v[1] < 0 or v[1] > 65535:
            return None
        if v[2] >= v[0] or v[0] >= v[3] or v[4] >= v[1] or v[1] >= v[5]:
            return None
        return v
    except Exception:
        return None


def save_cal(values):
    try:
        with open(CAL_FILE, "w") as f:
            f.write(",".join(str(v) for v in values))
    except Exception:
        pass


print("--- Sofa-Steuerung ---")
stop_all()

try:
    adc_x = adc_init(X_PIN)
    adc_y = adc_init(Y_PIN)
except Exception as e:
    print("ADC-Fehler:", e)
    stop_all()
    raise SystemExit

# Kalibrierung übersprungen: feste (gemessene) Werte.
# Stick-Drift wird über die Totzone (DEADZONE) abgefangen.
center_x, center_y = 27121, 6911
min_x, max_x = 40, 54241
min_y, max_y = 2052, 17987

print("Mitte X=%d Y=%d  Bereich X=%d..%d Y=%d..%d"
      % (center_x, center_y, min_x, max_x, min_y, max_y))
print("Joystick zentrieren ...")
while True:
    x = axis_percent(read_avg(adc_x), center_x, min_x, max_x)
    y = axis_percent(read_avg(adc_y), center_y, min_y, max_y)
    if x == 0 and y == 0:
        break
    time.sleep_ms(50)
print("Bereit. Ctrl-C beendet.")

last = time.ticks_ms()
tick = 0

try:
    while True:
        loop_start = time.ticks_ms()
        dt = time.ticks_diff(loop_start, last) / 1000.0
        last = loop_start
        if dt <= 0.0:
            dt = 0.001
        elif dt > 0.1:
            dt = 0.1

        x = axis_percent(read_avg(adc_x), center_x, min_x, max_x)
        y = axis_percent(read_avg(adc_y), center_y, min_y, max_y)

        steer = STEER_CURVE[x + 100] * STEER_SIGN
        throttle = y * DRIVE_SIGN

        power = MAX_POWER_REV if throttle < 0 else MAX_POWER_FWD

        left = (throttle + steer) * power / 100.0
        right = (throttle - steer) * power / 100.0

        if left > power:
            left = power
        elif left < -power:
            left = -power
        if right > power:
            right = power
        elif right < -power:
            right = -power

        trim = LEFT_TRIM_REV if throttle < 0 else LEFT_TRIM_FWD
        left *= 1.0 + trim / 100.0
        if left > 100.0:
            left = 100.0
        elif left < -100.0:
            left = -100.0

        # Richtungswechsel je Rad: abbremsen -> Bremse kurz anziehen ->
        # Richtung umschalten (deckt Gas-Wechsel UND Lenk-/Pivot-Wechsel ab).
        motor_l.drive_soft(left, dt)
        motor_r.drive_soft(right, dt)

        tick += 1
        if tick % 50 == 0:
            print("X %+4d  Y %+4d  L %+6.1f  R %+6.1f"
                  % (x, y, motor_l.cur, motor_r.cur))

        elapsed = time.ticks_diff(time.ticks_ms(), loop_start)
        if elapsed < LOOP_MS:
            time.sleep_ms(LOOP_MS - elapsed)

except KeyboardInterrupt:
    print("Abbruch")
finally:
    stop_all()
    print("Motoren gestoppt")
