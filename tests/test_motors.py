# =====================================================================
#  test_motors.py  -  Einzeltest der beiden Vorder-Motoren
#
#  Start:   .venv/bin/mpremote connect /dev/ttyACM0 run test_motors.py
#  (wird NICHT automatisch gestartet, ist nicht main.py)
#
#  Ablauf: 4 Phasen a 3 s. Beobachte, welcher Motor sich wann dreht.
#    1) nur vorne rechts  (PWM IO10, DIR IO9)
#    2) nur vorne links   (PWM IO5,  DIR IO4)
#    3) beide vorwaerts
#    4) beide rueckwaerts
# =====================================================================

import time
from machine import Pin, PWM

PWM_FREQ = 1000
PWM_MAX = 1023
TEST_PERCENT = 50
PHASE_MS = 3000

# Pin.OUT zuerst setzen -> Pegel bleibt ruecklesbar (INPUT_OUTPUT)
Pin(10, Pin.OUT, value=0)
Pin(5, Pin.OUT, value=0)
r10 = Pin(10)
r5 = Pin(5)

m_fr = PWM(Pin(10))
m_fr.freq(PWM_FREQ)
m_fr.duty(0)

m_fl = PWM(Pin(5))
m_fl.freq(PWM_FREQ)
m_fl.duty(0)

dir_fr = Pin(9, Pin.OUT)
dir_fl = Pin(4, Pin.OUT)


def messung(pin_reader, n=8000):
    """Anteil High-Pegel in Prozent (muss ~TEST_PERCENT sein)."""
    return sum(pin_reader.value() for _ in range(n)) / n * 100


def richtung(forward=True):
    # 0 = vorwaerts, 1 = rueckwaerts - gilt fuer beide Motoren
    for p in (dir_fr, dir_fl):
        p.value(0 if forward else 1)


def phase(text, fr, fl, forward=True, sec=PHASE_MS / 1000):
    richtung(forward)
    m_fr.duty(fr)
    m_fl.duty(fl)
    print("%s  (DIR rechts=%d, links=%d)" % (text, dir_fr.value(), dir_fl.value()))
    time.sleep(sec)


duty_test = int(TEST_PERCENT * PWM_MAX / 100 + 0.5)

print("--- PWM-Selbsttest bei %d %% ---" % TEST_PERCENT)
m_fr.duty(duty_test)
m_fl.duty(duty_test)
time.sleep_ms(300)
print("  IO10 (vorne rechts): %5.1f %% high" % messung(r10))
print("  IO5  (vorne links) : %5.1f %% high" % messung(r5))
m_fr.duty(0)
m_fl.duty(0)
time.sleep_ms(300)

print("--- Motoren ---")
phase("1) NUR vorne rechts", duty_test, 0)
phase("2) NUR vorne links", 0, duty_test)
phase("3) BEIDE vorwaerts", duty_test, duty_test)
phase("4) BEIDE rueckwaerts", duty_test, duty_test, forward=False)

m_fr.duty(0)
m_fl.duty(0)
richtung(True)
print("fertig - beide Motoren aus")
