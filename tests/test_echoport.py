#!/usr/bin/env python3
"""Test ECHOPORT vocabulary: live hardware port activity recorder.
Vocabs are embedded in kernel — no block storage needed.
"""
import socket
import time
import sys

import serial as ser  # tests/serial.py: bounded reads ending at the prompt (4b)

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4800

try:
    s = ser.connect_and_sync(PORT, budget=60)
except TimeoutError as e:
    print(f"FAIL: connect: {e}")
    sys.exit(1)


def send(cmd, wait=1.5):
    # Ends at the guest's prompt (tests/serial.py); `wait` no longer sleeps,
    # it widens the budget for commands that legitimately take long.
    reply, _how = ser.send_until_prompt(s, cmd, budget=max(15.0, 5 * wait))
    return reply


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


# Embedded vocabs already loaded at boot
print("ECHOPORT tests (embedded vocab):")

r = send('USING ECHOPORT', 2)
ok = alive()
check('USING ECHOPORT succeeds', ok,
      f'response: {r.strip()[:80]!r}')

if not ok:
    print("FAIL: Cannot continue")
    s.close()
    sys.exit(1)

# Test ECHOPORT-ON sets flag
r = send('ECHOPORT-ON', 2)
check('ECHOPORT-ON executes',
      'tracing on' in r.lower(),
      f'got: {r.strip()!r}')

r = send('TRACE-ENABLED C@ .', 1)
check('TRACE-ENABLED = 1 after ON',
      '1' in r, f'got: {r.strip()!r}')

# Test ECHOPORT-OFF clears flag
r = send('ECHOPORT-OFF', 2)
check('ECHOPORT-OFF executes',
      'off' in r.lower(),
      f'got: {r.strip()!r}')

r = send('TRACE-ENABLED C@ .', 1)
check('TRACE-ENABLED = 0 after OFF',
      '0' in r, f'got: {r.strip()!r}')

# Test: enable, do one INB, check count
r = send('ECHOPORT-ON', 2)
r = send('HEX 20 INB DROP', 1)
check('INB after ON executes',
      alive(), f'got: {r.strip()!r}')

r = send('ECHOPORT-COUNT .', 1)
nums = [w for w in r.split() if w.strip().isdigit()]
has_count = any(int(n) >= 1 for n in nums) if nums else False
check('ECHOPORT-COUNT >= 1 after INB',
      has_count, f'got: {r.strip()!r}')

# Test ECHOPORT-DUMP shows INB and 0020
r = send('ECHOPORT-OFF', 2)
r = send('ECHOPORT-DUMP', 3)
check('ECHOPORT-DUMP shows INB',
      'INB' in r, f'got: {r.strip()[:100]!r}')
check('ECHOPORT-DUMP shows port 0020',
      '0020' in r, f'got: {r.strip()[:100]!r}')

# Test ECHOPORT-SUMMARY
r = send('ECHOPORT-SUMMARY', 3)
check('ECHOPORT-SUMMARY shows unique ports',
      'unique' in r.lower() or 'port' in r.lower(),
      f'got: {r.strip()[:100]!r}')

# Test ECHOPORT-CLEAR
r = send('ECHOPORT-CLEAR', 1)
r = send('ECHOPORT-COUNT .', 1)
check('ECHOPORT-CLEAR resets count to 0',
      '0' in r, f'got: {r.strip()!r}')

# Test ECHOPORT-WATCH
r = send(
    "USING PORT-MAPPER",
    2)
r = send(
    "' PIC-STATUS ECHOPORT-WATCH",
    5)
check('ECHOPORT-WATCH traces PIC-STATUS',
      'unique' in r.lower() or 'port' in r.lower()
      or 'ECHOPORT' in r,
      f'got: {r.strip()[:120]!r}')

# Final checks
print("\nFinal check:")
r = send('DECIMAL', 1)
ok = alive()
check('System alive after all tests', ok)

print(f'\nPassed: {PASS}/{PASS + FAIL}')
s.close()
sys.exit(0 if FAIL == 0 else 1)
