#!/usr/bin/env python3
"""Prueft per REPL, ob MicroPython auf dem ESP32-C5 laeuft.

Aufruf:  .venv/bin/python verify.py [PORT]     (Default: /dev/ttyACM0)
"""
import sys
import time

import serial

port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyACM0"

CMDS = [
    "import sys, os, gc",
    "print(sys.implementation)",
    "print(sys.platform, sys.version)",
    "print(gc.mem_free(), gc.mem_alloc())",
    "s = os.statvfs('/'); print('flash free:', s[0] * s[3], 'of', s[0] * s[2])",
]


def read_until_prompt(ser, timeout=5.0):
    buf = b""
    end = time.time() + timeout
    while time.time() < end:
        chunk = ser.read(256)
        if chunk:
            buf += chunk
            if buf.rstrip().endswith(b">>>"):
                break
        else:
            time.sleep(0.05)
    return buf.decode(errors="replace")


with serial.Serial(port, 115200, timeout=0.2) as s:
    s.dtr = False
    s.rts = False
    time.sleep(0.3)
    s.reset_input_buffer()
    s.write(b"\r\x03")
    read_until_prompt(s)          # Banner/Prompt einsammeln
    s.reset_input_buffer()
    for cmd in CMDS:
        s.write(cmd.encode() + b"\r\n")
        out = read_until_prompt(s)
        print(f">>> {cmd}")
        print(out.replace(cmd, "").replace(">>>", "").strip())
        print("-" * 40)
