#!/usr/bin/env python3
"""Tests for kernel DUMP word ( addr len -- )."""
import socket, time, sys, re

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4560

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(5)
s.connect(('127.0.0.1', PORT))

time.sleep(1.5)
try:
    while True:
        s.recv(4096)
except:
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

def check_re(name, response, regex):
    global PASS, FAIL
    if re.search(regex, response):
        PASS += 1
        print(f'  PASS: {name}')
    else:
        FAIL += 1
        print(f'  FAIL: {name} -- regex {regex!r} not found in {response.strip()!r}')

def check_not(name, response, forbidden):
    global PASS, FAIL
    if forbidden not in response:
        PASS += 1
        print(f'  PASS: {name}')
    else:
        FAIL += 1
        print(f'  FAIL: {name} -- "{forbidden}" should NOT be in {response.strip()!r}')

# Test 1: basic 256-byte dump has hex output
r = send('0 256 DUMP')
check_re('basic 256-byte dump',
         r, r'00000000: ([0-9A-F]{2} ){16} +.{16}')

# Test 2: address increments by 16
check('address increments', r, '00000010:')

# Test 3: full 16 lines (last line at 0xF0)
check('full 16 lines', r, '000000F0:')

# Test 4: no over-run past 256 bytes
check_not('no over-run past 256', r, '00000100:')

# Test 5: single full line format
r2 = send('0 16 DUMP')
check_re('single line format',
         r2, r'00000000: ([0-9A-F]{2} ){16} +.{16}')

# Test 6: zero-length produces no hex output
r3 = send('0 0 DUMP')
check_not('zero-length no output', r3, '00000000:')

# Test 7: short line (5 bytes) — only one line
r4 = send('0 5 DUMP')
check_not('short line no second line', r4, '00000010:')

# Summary
print()
TOTAL = PASS + FAIL
print(f'Passed: {PASS}/{TOTAL}')
s.close()
sys.exit(0 if FAIL == 0 else 1)
