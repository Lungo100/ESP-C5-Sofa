# Diagnose: Roht- und Normalwerte des Joysticks, Achse fuer Achse.
# Ablauf: Mitte lernen, dann je Achse die Endanschlaege lernen, dann anzeigt
# was beim Ausschlagen passiert.
import time
from machine import Pin, ADC

DEADZONE = 30


def adc_init(pin):
    try:
        a = ADC(Pin(pin), atten=ADC.ATTN_11DB)
    except (TypeError, ValueError):
        a = ADC(Pin(pin))
        a.atten(ADC.ATTN_11DB)
    try:
        a.width(ADC.WIDTH_12BIT)
    except Exception:
        pass
    a.read_u16()
    return a


def avg(a):
    return sum(a.read_u16() for _ in range(4)) // 4


def norm(raw, center, lo, hi):
    span = max(1, hi - center) if raw >= center else max(1, center - lo)
    p = (raw - center) * 100 / span
    p = max(-100.0, min(100.0, p))
    a = abs(p)
    if a <= DEADZONE:
        return 0.0
    a = (a - DEADZONE) * 100.0 / (100 - DEADZONE)
    return a if p > 0 else -a


def learn(name, a):
    idle = sum(avg(a) for _ in range(20)) // 20
    lo = hi = idle
    t0 = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), t0) < 6000:
        r = avg(a)
        lo = min(lo, r)
        hi = max(hi, r)
        time.sleep_ms(5)
    print("%s: idle=%d  min=%d  max=%d  (Mitte=%d)" % (name, idle, lo, hi, idle))
    return idle, lo, hi


x = adc_init(3)   # X = IO3
y = adc_init(1)   # Y = IO1

cx, lo_x, hi_x = learn("X", x)
cy, lo_y, hi_y = learn("Y", y)
print()
print("Phase: Hebel VOR -> zurueck -> links -> rechts. Ausgabe beobachten:")
t1 = time.ticks_ms()
while time.ticks_diff(time.ticks_ms(), t1) < 16000:
    print("X %+5.0f  Y %+5.0f   roh X=%d Y=%d"
          % (norm(avg(x), cx, lo_x, hi_x), norm(avg(y), cy, lo_y, hi_y),
             avg(x), avg(y)))
    time.sleep_ms(80)
print("Ende.")
