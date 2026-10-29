# Diagnose: zeigt Roht + normalisierte Achswerte.
# Hebel in dieser Zeit langsam ganz nach links und ganz nach rechts bewegen.
import time
from machine import Pin, ADC

a_x = ADC(Pin(3))
a_y = ADC(Pin(1))
try:
    a_x.atten(ADC.ATTN_11DB)
    a_y.atten(ADC.ATTN_11DB)
except Exception:
    pass


def avg(a):
    return sum(a.read_u16() for _ in range(4)) // 4


for _ in range(20):
    avg(a_x)
    avg(a_y)
    time.sleep_ms(10)

cx = sum(avg(a_x) for _ in range(20)) // 20
cy = sum(avg(a_y) for _ in range(20)) // 20
print("Mitte X=%d Y=%d" % (cx, cy))
lo_x = hi_x = cx
lo_y = hi_y = cy
t0 = time.ticks_ms()
while time.ticks_diff(time.ticks_ms(), t0) < 8000:
    rx = avg(a_x)
    ry = avg(a_y)
    lo_x = min(lo_x, rx)
    hi_x = max(hi_x, rx)
    lo_y = min(lo_y, ry)
    hi_y = max(hi_y, ry)
    time.sleep_ms(150)
print("X-Bereich: lo=%d hi=%d  (Mitte lo-bis-hi = %d)" % (lo_x, hi_x, (lo_x + hi_x) // 2))
print("Y-Bereich: lo=%d hi=%d" % (lo_y, hi_y))
print("X-Ausschlag links = %d, rechts = %d (sollte aehnlich sein)"
      % (cx - lo_x, hi_x - cx))
