# =====================================================================
#  controller.py  -  nur Controller auslesen (KEINE Motoren!)
#
#  Start:  .venv/bin/mpremote connect /dev/ttyACM0 run controller.py
#  (wird NICHT automatisch gestartet, ist nicht main.py)
#
#  Anschluesse wie gewuenscht:
#     X-Achse (links/rechts)  ->  IO3
#     Y-Achse (vor/zurueck)   ->  IO0
#
#  WICHTIG zu IO0:
#  Der ESP32-C5 hat ADC-Eingaenge nur auf GPIO1 ... GPIO6.
#  GPIO0 ist XTAL_32K_P und besitzt KEINEN ADC-Kanal -> ADC(Pin(0))
#  schlaegt fehl. Deshalb versucht dieses Skript IO0 und weicht bei
#  Fehler automatisch auf IO1 aus (ADC1_CH0). Dann einfach die
#  Y-Leitung von IO0 auf IO1 umstecken.
#
#  Ausgabe: Rohwert, Prozent (-100 ... +100) und ein Balken.
#  Die Mittelstellung wird automatisch kalibriert (min/max je Achse).
# =====================================================================

import time
from machine import ADC, Pin

# ------------------------------------------------------------ Anschluesse
X_PIN = 3            # X-Achse
Y_PIN = 0            # Y-Achse (laut Vorgabe)
Y_FALLBACK = 1       # Ersatz, falls IO0 keinen ADC hat

# ------------------------------------------------------------- Einstellung
ATTEN = ADC.ATTN_11DB     # Messbereich ca. 0 ... 3,3 V
WIDTH = ADC.WIDTH_12BIT   # 12 Bit Aufloesung
SAMPLES = 8               # Mittelwert ueber 8 Messungen (gegen Zittern)
DEADZONE = 6              # % um die Mitte, die als 0 gilt
PRINT_MS = 200            # Ausgabeintervall


def make_adc(pin, name):
    """ADC an einem Pin anlegen; bei Fehler None zurueckgeben."""
    try:
        a = ADC(Pin(pin))
        # atten/width sind in dieser MicroPython-Version Methoden,
        # keine Konstruktor-Argumente
        a.atten(ATTEN)
        a.width(WIDTH)
        a.read_u16()                     # Testmessung
        print("%-2s: IO%-2d  ok" % (name, pin))
        return a
    except Exception as e:
        print("%-2s: IO%-2d  FEHLER (%s: %s)" % (name, pin, type(e).__name__, e))
        return None


print("--- Controller-Test (nur lesen, keine Motoren) ---")
adc_x = make_adc(X_PIN, "X")

adc_y = make_adc(Y_PIN, "Y")
if adc_y is None:
    print("     IO%d hat auf dem ESP32-C5 keinen ADC-Kanal." % Y_PIN)
    print("     Y-Leitung auf IO%d umstecken, dann laeuft es." % Y_FALLBACK)
    adc_y = make_adc(Y_FALLBACK, "Y*")

if adc_x is None or adc_y is None:
    print("Abbruch: mindestens eine Achse nicht lesbar.")
else:
    # ------------------------------------------------- Kalibrierung
    # min/max werden waehrend des Laufs mitverfolgt. Zu Beginn den
    # Hebel einmal in alle vier Ecken bewegen, danach stimmt die Mitte.
    x_min = y_min = 65535
    x_max = y_max = 0

    def read_avg(adc):
        return sum(adc.read_u16() for _ in range(SAMPLES)) // SAMPLES

    def axis_percent(value, lo, hi):
        """Rohwert -> -100 ... +100, Mitte = 0, mit Totzone."""
        center = (lo + hi) / 2
        span = (hi - lo) / 2
        if span < 1000:                  # noch nicht kalibriert
            return 0
        p = (value - center) / span * 100
        if -DEADZONE < p < DEADZONE:
            return 0
        return int(max(-100, min(100, p)))

    def bar(p):
        """Balken von -100 ... +100, Mitte ist |."""
        pos = int((p + 100) * 20 / 200)  # 0 ... 20
        s = ["-"] * 21
        s[10] = "|"
        s[pos] = "#"
        return "".join(s)

    print()
    print("Hebel einmal in alle Ecken bewegen -> Mitte wird kalibriert.")
    print("%-7s %-6s %-5s %-21s   %-7s %-6s %-5s %s"
          % ("X roh", "Volt", "%", "links<--->rechts", "Y roh", "Volt", "%", "hinten<->vorn"))
    print()

    try:
        while True:
            x = read_avg(adc_x)
            y = read_avg(adc_y)

            x_min = min(x_min, x)
            x_max = max(x_max, x)
            y_min = min(y_min, y)
            y_max = max(y_max, y)

            px = axis_percent(x, x_min, x_max)
            py = axis_percent(y, y_min, y_max)

            print("%-7d %-6.2f %-5s %-21s   %-7d %-6.2f %-5s %s"
                  % (x, x / 65535 * 3.3, "%+d" % px if px else "0", bar(px),
                     y, y / 65535 * 3.3, "%+d" % py if py else "0", bar(py)))
            time.sleep_ms(PRINT_MS)

    except KeyboardInterrupt:
        # nur eine saubere Meldung - es gibt keine Motoren zu stoppen
        print()
        print("beendet. Kalibrierbereich: X %d ... %d   Y %d ... %d"
              % (x_min, x_max, y_min, y_max))
