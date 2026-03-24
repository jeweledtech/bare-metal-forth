#!/usr/bin/env python3
"""Test ECHOPORT vocabulary: live hardware port activity recorder.
Vocabs are embedded in kernel — no block storage needed.
"""
import socket
import time
import sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4800

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(15)
for attempt in range(20):
    try:
        s.connect(('127.0.0.1', PORT))
        break
    except (ConnectionRefusedError, OSError):
        time.sleep(0.5)
else:
    print("FAIL: Could not connect")
    sys.exit(1)

time.sleep(3)
try:
    while True:
        s.recv(4096)
except Exception:
    pass


def send(cmd, wait=1.5):
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
