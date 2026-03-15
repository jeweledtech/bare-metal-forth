#!/usr/bin/env python3
"""End-to-end pipeline test: .sys binary → block vocab → live USING.

Verifies that translator output written to block storage can be loaded
into the running kernel via THRU, and that USING activates the vocabulary
with working port I/O words.
"""
import socket, time, sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4530

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

print("E2E Pipeline Test: i8042prt.sys -> USING I8042PRT")
print("=" * 50)

# Test 1: Kernel alive
r = send('1 2 + .')
check('kernel alive', r, '3')

# Test 2: Load translated vocabulary from blocks 2-6
r = send('2 6 THRU', wait=2.0)
check('THRU loads without crash', r, 'ok')

# Test 3: USING activates the vocabulary
r = send('USING I8042PRT')
check('USING I8042PRT', r, 'ok')

# Test 4: Extracted words visible in WORDS
r = send('WORDS', wait=1.0)
check('FUNC_16FCC in dictionary', r, 'FUNC_16FCC')

# Test 5: ORDER shows I8042PRT in search order
r = send('ORDER')
check('ORDER shows vocabulary', r, 'Search:')

# Test 6: Call extracted port I/O function on COM1 LSR
# func_16FCC is ( port -- byte ) INB — read a byte from a port
# Port 0x3FD = COM1 Line Status Register, QEMU returns 0x60
r = send('HEX 3FD FUNC_16FCC . DECIMAL')
check('FUNC_16FCC reads COM1 LSR', r, '60')

# Test 7: Call second port I/O function
r = send('HEX 3FD FUNC_17024 . DECIMAL')
check('FUNC_17024 reads COM1 LSR', r, '60')

# Summary
print()
TOTAL = PASS + FAIL
print(f'Passed: {PASS}/{TOTAL}')
s.close()
sys.exit(0 if FAIL == 0 else 1)
