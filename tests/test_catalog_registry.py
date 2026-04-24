#!/usr/bin/env python3
"""Smoke test for CATALOG-REGISTRY in-memory form lookup."""
import socket, time, sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4590

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
except:
    pass


def send(cmd, wait=2.0):
    s.sendall((cmd + '\r').encode())
    time.sleep(wait)
    s.settimeout(3)
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


PASS = FAIL = 0


def check(name, ok, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {name}')
    else:
        FAIL += 1
        print(f'  FAIL: {name} -- {detail}')


def extract_number(text):
    words = text.replace('\r', ' ').replace('\n', ' ').split()
    for i in range(len(words) - 1, -1, -1):
        if words[i] in ('ok', 'OK') and i > 0:
            try:
                return int(words[i - 1])
            except ValueError:
                pass
    return None


# Set up search order for vocab words
send('ALSO CATALOG-RESOLVER', 1)
send('ALSO UI-PARSER', 1)
send('ALSO UI-CORE', 1)

# Test 1: CATALOG-FIND returns TRUE
print("\nTest 1: CATALOG-FIND registry hit")
r = send(': T1 S" NOTEPAD-FORM" CATALOG-FIND ;', 1)
r = send('T1 . . .', 3)
print(f"  response: {r.strip()!r}")
check('CATALOG-FIND returns TRUE',
      '-1 ' in r,
      f'expected -1 (TRUE)')

# Test 2: CATALOG-MEM flag is set
print("\nTest 2: CATALOG-MEM flag")
r = send('CATALOG-MEM @ .', 2)
print(f"  response: {r.strip()!r}")
check('CATALOG-MEM = 1',
      '1 ' in r or r.strip().endswith('1 ok'),
      f'expected 1')

# Test 3: FORM-LOAD produces widgets
print("\nTest 3: FORM-LOAD widget count")
r = send(': T3 S" NOTEPAD-FORM" CATALOG-FIND IF FORM-LOAD THEN ;', 1)
r = send('T3', 3)
r = send('WT-COUNT @ .', 2)
print(f"  WT-COUNT: {r.strip()!r}")
count = extract_number(r)
check('Widget count >= 10',
      count is not None and count >= 10,
      f'got {count}')

# Test 4: Stack clean
print("\nTest 4: Stack clean")
r = send('.S', 2)
print(f"  stack: {r.strip()!r}")
check('Stack clean', '<>' in r, f'stack not empty')

print(f'\nPassed: {PASS}/{PASS + FAIL}')
s.close()
sys.exit(0 if FAIL == 0 else 1)
