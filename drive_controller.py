import time
from machine import Pin, PWM, ADC

PWM_FREQ = 1000
LOOP_MS = 20
ADC_SAMPLES = 6
DEADZONE = 20
CENTER_MS = 1200
CENTER_SETTLE_MS = 800
CENTER_STABLE = 2500
RANGE_MS = 4000
MIN_SPAN = 4000
DEFAULT_SPAN = 26000
CAL_FILE = "cal.txt"
SAVE_CAL = True
RECALIBRATE = True

MAX_POWER = 100
ACCEL = 140.0
DECEL = 240.0
STEER_EXPO = 1.8
STEER_GAIN = 1.0

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


class Motor:
    def __init__(self, pwm_pin, dir_pin, brake_pin, inverted=False):
        self.pwm, self.use_u16 = pwm_init(pwm_pin)
        self.dir = Pin(dir_pin, Pin.OUT)
        self.brake = Pin(brake_pin, Pin.OUT)
        self.inverted = inverted
        self.forward = None
        self.cur = 0.0
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

    def drive(self, target, dt):
        if self.cur < target:
            nxt = self.cur + ACCEL * dt
            if nxt > target:
                nxt = target
        else:
            nxt = self.cur - DECEL * dt
            if nxt < target:
                nxt = target

        if (self.cur > 0.0 and nxt < 0.0) or (self.cur < 0.0 and nxt > 0.0):
            nxt = 0.0
        self.cur = nxt

        if abs(self.cur) < 0.5:
            self._duty(0.0)
            if abs(target) < 0.5:
                if BRAKE_HOLD:
                    self.brake_on()
                else:
                    self.brake_off()
            return

        self.brake_off()
        forward = self.cur > 0.0
        if forward != self.forward:
            self._duty(0.0)
            self._set_dir(forward)
        self._duty(abs(self.cur))

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
        rx = adc_x.read_u16()
        ry = adc_y.read_u16()
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

cal = None if RECALIBRATE else load_cal()
if cal is None:
    print("Joystick loslassen - Mitte kalibrieren ...")
    time.sleep_ms(CENTER_SETTLE_MS)
    center_x, center_y = read_center_both(adc_x, adc_y, CENTER_MS)
    print("Joystick %d s lang in alle Richtungen bewegen ..." % (RANGE_MS // 1000))
    min_x, max_x, min_y, max_y = read_range_both(
        adc_x, adc_y, center_x, center_y, RANGE_MS
    )
    if SAVE_CAL:
        save_cal((center_x, center_y, min_x, max_x, min_y, max_y))
        print("Kalibrierung gespeichert")
else:
    center_x, center_y, min_x, max_x, min_y, max_y = cal
    print("Kalibrierung geladen")

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

        left = (throttle + steer) * MAX_POWER / 100.0
        right = (throttle - steer) * MAX_POWER / 100.0

        if left > MAX_POWER:
            left = MAX_POWER
        elif left < -MAX_POWER:
            left = -MAX_POWER
        if right > MAX_POWER:
            right = MAX_POWER
        elif right < -MAX_POWER:
            right = -MAX_POWER

        if BRAKE_AT_CENTER and x == 0 and y == 0:
            motor_l.stop()
            motor_r.stop()
        else:
            motor_l.drive(left, dt)
            motor_r.drive(right, dt)

        tick += 1
        if tick % 50 == 0:
            print("X %+4d  Y %+4d  L %+6.1f  R %+6.1f"
                  % (x, y, left, right))

        elapsed = time.ticks_diff(time.ticks_ms(), loop_start)
        if elapsed < LOOP_MS:
            time.sleep_ms(LOOP_MS - elapsed)

except KeyboardInterrupt:
    print("Abbruch")
finally:
    stop_all()
    print("Motoren gestoppt")
