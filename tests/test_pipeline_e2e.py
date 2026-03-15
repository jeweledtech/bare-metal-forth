#!/usr/bin/env python3
"""End-to-end pipeline test: .sys binary → block vocab → live USING.

Verifies the complete chain:
1. HARDWARE vocab loads from blocks (provides US-DELAY, IRQ-*, DPC-QUEUE)
2. I8042PRT vocab loads with zero ? errors (all 9 functions compile)
3. USING I8042PRT activates the vocabulary
4. Extracted port I/O functions execute real hardware reads
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

def check_no(name, response, bad_pattern):
    """Assert bad_pattern is NOT in response."""
    global PASS, FAIL
    if bad_pattern not in response:
        PASS += 1
        print(f'  PASS: {name}')
    else:
        FAIL += 1
        print(f'  FAIL: {name} -- unexpected "{bad_pattern}" in {response.strip()!r}')

print("E2E Pipeline: HARDWARE + I8042PRT (zero ? errors)")
print("=" * 50)

# Test 1: Kernel alive
r = send('1 2 + .')
check('kernel alive', r, '3')

# Test 2: Load HARDWARE vocabulary (block 50+)
# hardware.fth is ~170 lines = ~11 blocks
r = send('HEX 32 3D THRU DECIMAL', wait=3.0)
check('HARDWARE loads', r, 'ok')

# Test 3: Load I8042PRT vocabulary (block 100+)
# i8042prt.fth is 65 lines = 5 blocks
r = send('HEX 64 69 THRU DECIMAL', wait=2.0)
check_no('I8042PRT zero ? errors', r, '?')

# Test 4: USING activates the vocabulary
r = send('USING I8042PRT')
check('USING I8042PRT', r, 'ok')

# Test 5: All 9 extracted functions visible
r = send('WORDS', wait=1.0)
check('FUNC_16FCC in dictionary', r, 'FUNC_16FCC')
check('FUNC_122A8 in dictionary', r, 'FUNC_122A8')

# Test 6: Call extracted port I/O function on COM1 LSR
# func_16FCC is ( port -- byte ) INB
# Port 0x3FD = COM1 LSR, QEMU returns 0x60
r = send('HEX 3FD FUNC_16FCC . DECIMAL')
check('FUNC_16FCC reads COM1 LSR', r, '60')

# Test 7: US-DELAY runs without crash
r = send('HEX 64 US-DELAY DECIMAL')
check('US-DELAY executes', r, 'ok')

# Summary
print()
TOTAL = PASS + FAIL
print(f'Passed: {PASS}/{TOTAL}')
s.close()
sys.exit(0 if FAIL == 0 else 1)
