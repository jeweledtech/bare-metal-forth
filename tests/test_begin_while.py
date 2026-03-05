#!/usr/bin/env python3
"""Test BEGIN/WHILE/REPEAT and BEGIN/UNTIL loops.

Verifies the backward branch offset fix.
"""
import socket
import time
import sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4482

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(10)
for attempt in range(20):
    try:
        s.connect(('127.0.0.1', PORT))
        break
    except (ConnectionRefusedError, OSError):
        time.sleep(0.5)
else:
    print("FAIL: connect")
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


def extract_number(text):
    words = text.replace('\r', ' ').replace('\n', ' ').split()
    for i in range(len(words) - 1, -1, -1):
        if words[i] in ('ok', 'OK'):
            if i > 0:
                try:
                    return int(words[i - 1])
                except ValueError:
                    pass
    return None


PASS = FAIL = 0


def check(name, ok, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {name}')
    else:
        FAIL += 1
        print(f'  FAIL: {name} -- {detail}' if detail else
              f'  FAIL: {name}')


# Test 1: BEGIN/WHILE/REPEAT countdown
print("\nTest 1: BEGIN/WHILE/REPEAT countdown")
send('VARIABLE CNT', 1)
r = send(': COUNT-DOWN 0 CNT ! 5 BEGIN DUP WHILE 1 CNT +! 1- REPEAT DROP CNT @ ;', 1)
print(f"  define: {r.strip()!r}")
r = send('COUNT-DOWN .', 2)
val = extract_number(r)
print(f"  result: {r.strip()!r} (parsed: {val})")
check('BEGIN/WHILE/REPEAT counts 5 iterations',
      val == 5, f'expected 5, got {val}')

# Test 2: BEGIN/UNTIL
print("\nTest 2: BEGIN/UNTIL countdown")
r = send(': COUNT-UP 0 BEGIN 1+ DUP 10 = UNTIL ;', 1)
print(f"  define: {r.strip()!r}")
r = send('COUNT-UP .', 2)
val = extract_number(r)
print(f"  result: {r.strip()!r} (parsed: {val})")
check('BEGIN/UNTIL counts to 10',
      val == 10, f'expected 10, got {val}')

# Test 3: BEGIN/AGAIN with EXIT
print("\nTest 3: BEGIN/AGAIN with EXIT")
r = send(': FIND-3 0 BEGIN 1+ DUP 3 = IF EXIT THEN AGAIN ;', 1)
print(f"  define: {r.strip()!r}")
r = send('FIND-3 .', 2)
val = extract_number(r)
print(f"  result: {r.strip()!r} (parsed: {val})")
check('BEGIN/AGAIN with EXIT at 3',
      val == 3, f'expected 3, got {val}')

# Test 4: Nested DO/LOOP + BEGIN/WHILE/REPEAT
print("\nTest 4: DO/LOOP then BEGIN/WHILE/REPEAT")
r = send(': MIXED 0 3 0 DO 1+ LOOP 5 BEGIN DUP WHILE 1- SWAP 1+ SWAP REPEAT DROP ;', 1)
print(f"  define: {r.strip()!r}")
r = send('MIXED .', 2)
val = extract_number(r)
print(f"  result: {r.strip()!r} (parsed: {val})")
check('DO/LOOP(+3) then WHILE(+5) = 8',
      val == 8, f'expected 8, got {val}')

# Test 5: Stack clean
print("\nTest 5: Stack clean")
r = send('.S', 1)
check('Stack clean', '<>' in r, f'stack: {r.strip()!r}')

print(f'\nPassed: {PASS}/{PASS + FAIL}')
s.close()
sys.exit(0 if FAIL == 0 else 1)
