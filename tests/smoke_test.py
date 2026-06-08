#!/usr/bin/env python3
"""Quick smoke test for kernel S"/." block-mode fix."""
import socket, time, sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4448

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(5)
s.connect(('127.0.0.1', PORT))

time.sleep(1.5)
try:
    while True:
        s.recv(4096)
except:
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
        except:
            break
    return resp.decode('ascii', errors='replace')

PASS = 0
FAIL = 0

def check(name, response, pattern):
    global PASS, FAIL
    if pattern in response:
        PASS += 1
        print(f'  PASS: {name}')
    else:
        FAIL += 1
        print(f'  FAIL: {name} -- expected "{pattern}" in {response.strip()!r}')

# Test 1: WORDS shows kernel words (must run BEFORE any colon defs —
# defining a word re-threads VAR_LATEST through FORTH, masking the bug)
r = send('WORDS', 2)
check('WORDS shows DROP', r, 'DROP')
check('WORDS shows DUMP', r, 'DUMP')

# Test 2: basic arithmetic
r = send('1 2 + .')
check('basic arithmetic', r, '3')

# Test 3: S" in interpret mode
r = send('S" hello" TYPE')
check('S" interpret mode', r, 'hello')

# Test 4: ." in compile mode
send(': GREET ." world" ;', 1.0)
r = send('GREET', 1.0)
check('." compile mode', r, 'world')

# Test 5: IF/ELSE/THEN
r = send('1 IF 42 ELSE 99 THEN .')
check('IF/ELSE/THEN', r, '42')

# Test 6: DO/LOOP
r = send(': COUNTUP 5 0 DO I . LOOP ;')
r = send('COUNTUP')
check('DO/LOOP', r, '0')

# Summary
print()
TOTAL = PASS + FAIL
print(f'Passed: {PASS}/{TOTAL}')
s.close()
sys.exit(0 if FAIL == 0 else 1)
