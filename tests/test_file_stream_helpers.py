#!/usr/bin/env python3
"""Test CRC-32 and BE!/BE-W! helpers in QEMU.

These are standalone definitions sent interactively —
no vocab loading or NTFS/RTL8168 deps needed.
"""
import socket, time, sys

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
        print(f'  FAIL: {name}'
              f' -- expected "{pattern}"'
              f' in {response.strip()!r}')


# ================================================
# Define BE-W! and BE! interactively
# ================================================
send('HEX', 0.5)

# BE-W! stores 16-bit big-endian
send(': BE-W! OVER 8 RSHIFT OVER C! '
     '1+ SWAP FF AND SWAP C! ;', 1.0)

# BE! stores 32-bit big-endian
# Split across multiple sends to stay under
# QEMU serial buffer limits
send(': BE! OVER 18 RSHIFT OVER C!', 0.5)
send('1+ OVER 10 RSHIFT FF AND', 0.5)
send('OVER C! 1+ OVER 8 RSHIFT', 0.5)
send('FF AND OVER C! 1+ SWAP', 0.5)
send('FF AND SWAP C! ;', 1.0)

# Allocate test buffer
send('VARIABLE TB1', 0.5)
send('VARIABLE TB2', 0.5)

# ---- BE-W! tests ----

# Test 1: BE-W! with 0x1234
send('1234 TB1 BE-W!', 0.5)
r = send('TB1 C@ .', 0.5)
check('BE-W! high byte 0x12', r, '18')

r = send('TB1 1+ C@ .', 0.5)
check('BE-W! low byte 0x34', r, '52')

# Test 2: BE-W! with 0x0001
send('1 TB1 BE-W!', 0.5)
r = send('TB1 C@ .', 0.5)
check('BE-W! 0x0001 high=0', r, '0')

r = send('TB1 1+ C@ .', 0.5)
check('BE-W! 0x0001 low=1', r, '1')

# ---- BE! tests ----

# Test 3: BE! with 0x12345678
send('12345678 TB1 BE!', 0.5)
r = send('TB1 C@ .', 0.5)
check('BE! byte0=0x12', r, '18')

r = send('TB1 1+ C@ .', 0.5)
check('BE! byte1=0x34', r, '52')

r = send('TB1 2 + C@ .', 0.5)
check('BE! byte2=0x56', r, '86')

r = send('TB1 3 + C@ .', 0.5)
check('BE! byte3=0x78', r, '120')

# Test 4: BE! with 0xDEADBEEF
send('DEADBEEF TB1 BE!', 0.5)
r = send('TB1 C@ .', 0.5)
check('BE! 0xDE=222', r, '222')

r = send('TB1 1+ C@ .', 0.5)
check('BE! 0xAD=173', r, '173')

r = send('TB1 2 + C@ .', 0.5)
check('BE! 0xBE=190', r, '190')

r = send('TB1 3 + C@ .', 0.5)
check('BE! 0xEF=239', r, '239')

# ================================================
# Define CRC-32 interactively
# ================================================
send('HEX', 0.5)
send('EDB88320 CONSTANT CRC32-POLY', 0.5)
send('FFFFFFFF CONSTANT CRC32-MASK', 0.5)
send('DECIMAL', 0.5)
send('CREATE CRC32-TABLE 1024 ALLOT', 1.0)

# CRC32-INIT: build the 256-entry table
send(': CRC32-INIT 256 0 DO', 0.5)
send('I 8 0 DO DUP 1 AND IF', 0.5)
send('1 RSHIFT CRC32-POLY XOR', 0.5)
send('ELSE 1 RSHIFT THEN', 0.5)
send('LOOP CRC32-TABLE I 4 * + !', 0.5)
send('LOOP ;', 1.0)

# CRC32: compute CRC-32 of (addr len)
send(': CRC32 CRC32-MASK -ROT', 0.5)
send('0 DO OVER I + C@', 0.5)
send('OVER XOR 255 AND 4 *', 0.5)
send('CRC32-TABLE + @', 0.5)
send('SWAP 8 RSHIFT XOR', 0.5)
send('LOOP NIP CRC32-MASK XOR ;', 1.0)

# Build the table
r = send('CRC32-INIT', 2.0)

# Test 5: CRC-32 of empty string
# CRC-32("") = 0x00000000 (length 0 loop
# does nothing, mask XOR mask = 0)
r = send('HEX', 0.3)
r = send('TB1 0 CRC32 .', 1.0)
check('CRC32 empty=0', r, '0')

# Test 6: CRC-32 table entry 0
# Entry 0 should be 0 (0 XOR'd 8 times)
r = send('CRC32-TABLE @ .', 0.5)
check('CRC32-TABLE[0]=0', r, '0')

# Test 7: CRC-32 table entry 1
# Byte 1: shift right 1, XOR poly = EDB88320
r = send('CRC32-TABLE 4 + @ .', 0.5)
check('CRC32-TABLE[1]=EDB88320',
      r, 'EDB88320')

# Test 8: CRC-32 of "123456789"
# Standard test vector: CRC32 = 0xCBF43926
send('DECIMAL', 0.3)
send('CREATE TVEC 9 ALLOT', 0.5)
# Store "123456789" byte by byte
send('49 TVEC C!', 0.3)       # '1'
send('50 TVEC 1+ C!', 0.3)    # '2'
send('51 TVEC 2 + C!', 0.3)   # '3'
send('52 TVEC 3 + C!', 0.3)   # '4'
send('53 TVEC 4 + C!', 0.3)   # '5'
send('54 TVEC 5 + C!', 0.3)   # '6'
send('55 TVEC 6 + C!', 0.3)   # '7'
send('56 TVEC 7 + C!', 0.3)   # '8'
send('57 TVEC 8 + C!', 0.3)   # '9'
send('HEX', 0.3)
r = send('TVEC 9 CRC32 .', 1.0)
check('CRC32 "123456789"=CBF43926',
      r, 'CBF43926')

# ================================================
# Summary
# ================================================
s.close()

print(f'\n{PASS} passed, {FAIL} failed'
      f' out of {PASS + FAIL}')
sys.exit(1 if FAIL else 0)
