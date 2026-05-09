#!/usr/bin/env python3
"""Test d-word widget attributes: visible/enabled bit
flags on the widget table. Validates Milestone 2 proof
criterion: a button can be hidden and re-shown without
rebuilding the form.
"""
import socket
import time
import sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4760

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(10)
for attempt in range(20):
    try:
        s.connect(('127.0.0.1', PORT))
        break
    except (ConnectionRefusedError, OSError):
        time.sleep(0.5)
else:
    print("FAIL: Could not connect")
    sys.exit(1)

time.sleep(2)
try:
    while True:
        s.recv(4096)
except Exception:
    pass


def send(cmd, wait=1.0):
    s.sendall((cmd + '\r').encode())
    time.sleep(wait)
    s.settimeout(2)
    resp = b''
    while True:
        try:
            d = s.recv(4096)
            if not d:
                break
            resp += d
        except Exception:
            break
    return resp.decode('ascii', errors='replace')


def parse_int(resp):
    """Extract integer from the result line (last
    line containing 'ok'), skipping the command echo."""
    for line in reversed(resp.splitlines()):
        line = line.strip()
        if 'ok' in line:
            for word in line.split():
                if word.lstrip('-').isdigit():
                    return int(word)
    return None


def alive():
    r = send('1 2 + .', 1)
    return '3' in r


PASS = FAIL = 0


def check(name, ok, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {name}')
    else:
        FAIL += 1
        print(f'  FAIL: {name}' +
              (f' -- {detail}' if detail else ''))


# UI-CORE is embedded, activate it
r = send('USING UI-CORE', 2)
ok = alive()
check('USING UI-CORE succeeds', ok,
      f'response: {r.strip()[:80]!r}')
if not ok:
    print("FAIL: Could not activate UI-CORE")
    s.close()
    sys.exit(1)

# --- D-word constants ---
print("\nD-word constant tests:")

r = send('DECIMAL DW-VISIBLE .', 1)
check('DW-VISIBLE = 1', parse_int(r) == 1,
      f'got: {r.strip()!r}')

r = send('DW-ENABLED .', 1)
check('DW-ENABLED = 2', parse_int(r) == 2,
      f'got: {r.strip()!r}')

r = send('DW-VIS-ENA .', 1)
check('DW-VIS-ENA = 3', parse_int(r) == 3,
      f'got: {r.strip()!r}')

r = send('WTO-DWORD .', 1)
check('WTO-DWORD = 16', parse_int(r) == 16,
      f'got: {r.strip()!r}')

# --- Widget creation with d-word init ---
print("\nD-word initialization tests:")

# Reset widget table
send('WT-RESET', 1)

# Add a label (widget 0) and check d-word
send('5 3 S" Test" ADD-LABEL', 2)
r = send('0 WIDGET-VIS? .', 1)
val = parse_int(r)
check('ADD-LABEL sets visible',
      val is not None and val != 0,
      f'got: {r.strip()!r}')

r = send('0 WIDGET-ENA? .', 1)
val = parse_int(r)
check('ADD-LABEL sets enabled',
      val is not None and val != 0,
      f'got: {r.strip()!r}')

# Add a button (widget 1) with XT=0 (safe no-op)
send("2 5 10 S\" Go\" 0 ADD-BUTTON", 2)
r = send('1 WIDGET-VIS? .', 1)
val = parse_int(r)
check('ADD-BUTTON sets visible',
      val is not None and val != 0,
      f'got: {r.strip()!r}')

r = send('1 WIDGET-ENA? .', 1)
val = parse_int(r)
check('ADD-BUTTON sets enabled',
      val is not None and val != 0,
      f'got: {r.strip()!r}')

# --- CLR-VISIBLE / SET-VISIBLE ---
print("\nVisibility toggle tests:")

send('1 CLR-VISIBLE', 1)
r = send('1 WIDGET-VIS? .', 1)
val = parse_int(r)
check('CLR-VISIBLE clears visible', val == 0,
      f'expected 0, got: {r.strip()!r}')

# Enabled should still be set
r = send('1 WIDGET-ENA? .', 1)
val = parse_int(r)
check('CLR-VISIBLE preserves enabled',
      val is not None and val != 0,
      f'got: {r.strip()!r}')

send('1 SET-VISIBLE', 1)
r = send('1 WIDGET-VIS? .', 1)
val = parse_int(r)
check('SET-VISIBLE restores visible',
      val is not None and val != 0,
      f'got: {r.strip()!r}')

# --- CLR-ENABLED / SET-ENABLED ---
print("\nEnabled toggle tests:")

send('1 CLR-ENABLED', 1)
r = send('1 WIDGET-ENA? .', 1)
val = parse_int(r)
check('CLR-ENABLED clears enabled', val == 0,
      f'expected 0, got: {r.strip()!r}')

# Visible should still be set
r = send('1 WIDGET-VIS? .', 1)
val = parse_int(r)
check('CLR-ENABLED preserves visible',
      val is not None and val != 0,
      f'got: {r.strip()!r}')

send('1 SET-ENABLED', 1)
r = send('1 WIDGET-ENA? .', 1)
val = parse_int(r)
check('SET-ENABLED restores enabled',
      val is not None and val != 0,
      f'got: {r.strip()!r}')

# --- Idempotency ---
print("\nIdempotency tests:")

send('1 CLR-VISIBLE', 1)
send('1 CLR-VISIBLE', 1)
r = send('1 WIDGET-VIS? .', 1)
val = parse_int(r)
check('CLR-VISIBLE idempotent', val == 0,
      f'got: {r.strip()!r}')

send('1 SET-VISIBLE', 1)
send('1 SET-VISIBLE', 1)
r = send('1 WIDGET-VIS? .', 1)
val = parse_int(r)
check('SET-VISIBLE idempotent',
      val is not None and val != 0,
      f'got: {r.strip()!r}')

# --- Final check ---
print("\nFinal check:")
ok = alive()
check('System alive after all tests', ok)
if ok:
    r = send('.S', 1)
    check('Stack clean', '<>' in r,
          f'stack: {r.strip()!r}')

print(f'\nPassed: {PASS}/{PASS + FAIL}')
s.close()
sys.exit(0 if FAIL == 0 else 1)
