#!/usr/bin/env python3
"""Test FE-STRIP-ALL-CR: unconditional CR stripping in FILE-EDITOR.

Loads embedded vocabs, writes known byte patterns into FE-BUF,
calls FE-STRIP-ALL-CR, verifies all 0x0D bytes removed.
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


def setup_buf(hex_bytes):
    """Write hex byte list to FE-BUF, set FE-SIZE."""
    n = len(hex_bytes)
    send(f'FE-BUF {n + 4} 0 FILL', 0.5)
    for i, b in enumerate(hex_bytes):
        send(f'{b:X} FE-BUF {i:X} + C!', 0.15)
    send(f'{n:X} FE-SIZE !', 0.3)


def get_size():
    """Read FE-SIZE in decimal."""
    r = send('DECIMAL FE-SIZE @ .', 1)
    for tok in r.replace('\r', ' ').replace('\n', ' ').split():
        if tok.isdigit():
            return int(tok)
    return -1


def get_byte(offset):
    """Read one byte from FE-BUF in decimal."""
    r = send(f'DECIMAL FE-BUF {offset} + C@ .', 0.5)
    # Response format: "echo...\r\nVALUE ok"
    # Extract VALUE from after the last newline, before "ok"
    lines = r.strip().split('\n')
    last = lines[-1].strip() if lines else ''
    # last looks like "65 ok" or similar
    for tok in last.split():
        if tok.isdigit():
            return int(tok)
    return -1


# ---- Activate FILE-EDITOR ----
print("\nActivating FILE-EDITOR...")
r = send('USING FILE-EDITOR', 3)
ok = alive()
check('USING FILE-EDITOR succeeds', ok)
if not ok:
    s.close()
    sys.exit(1)

send('HEX', 1)

# ---- Test 1: Standard CRLF ----
# "A\r\nB" → "A\nB" (4 bytes → 3 bytes)
print("\nTest 1: Standard CRLF pair")
setup_buf([0x41, 0x0D, 0x0A, 0x42])
send('FE-STRIP-ALL-CR', 2)
ok = alive()
check('FE-STRIP-ALL-CR no crash', ok)
sz = get_size()
check('FE-SIZE = 3', sz == 3, f'got {sz}')
check('Byte 0 = 65 (A)', get_byte(0) == 65)
check('Byte 1 = 10 (LF)', get_byte(1) == 10)
check('Byte 2 = 66 (B)', get_byte(2) == 66)

# ---- Test 2: Standalone CR ----
# "A\rB" → "AB" (3 bytes → 2 bytes)
print("\nTest 2: Standalone CR (no following LF)")
send('HEX', 0.5)
setup_buf([0x41, 0x0D, 0x42])
send('FE-STRIP-ALL-CR', 2)
sz = get_size()
check('FE-SIZE = 2', sz == 2, f'got {sz}')
check('Byte 0 = 65 (A)', get_byte(0) == 65)
check('Byte 1 = 66 (B)', get_byte(1) == 66)

# ---- Test 3: Double CR before LF ----
# "A\r\r\nB" → "A\nB" (5 bytes → 3 bytes)
print("\nTest 3: Double CR before LF")
send('HEX', 0.5)
setup_buf([0x41, 0x0D, 0x0D, 0x0A, 0x42])
send('FE-STRIP-ALL-CR', 2)
sz = get_size()
check('FE-SIZE = 3', sz == 3, f'got {sz}')
check('Byte 0 = 65 (A)', get_byte(0) == 65)
check('Byte 1 = 10 (LF)', get_byte(1) == 10)
check('Byte 2 = 66 (B)', get_byte(2) == 66)

# ---- Test 4: All LF, no CR ----
# "A\nB" → "A\nB" (3 bytes → 3 bytes, unchanged)
print("\nTest 4: LF-only (no change expected)")
send('HEX', 0.5)
setup_buf([0x41, 0x0A, 0x42])
send('FE-STRIP-ALL-CR', 2)
sz = get_size()
check('FE-SIZE = 3 (unchanged)', sz == 3, f'got {sz}')
check('Byte 0 = 65 (A)', get_byte(0) == 65)
check('Byte 1 = 10 (LF)', get_byte(1) == 10)
check('Byte 2 = 66 (B)', get_byte(2) == 66)

# ---- Test 5: Empty buffer ----
print("\nTest 5: Empty buffer (FE-SIZE = 0)")
send('HEX', 0.5)
send('0 FE-SIZE !', 0.3)
send('FE-STRIP-ALL-CR', 2)
ok = alive()
check('FE-SIZE=0 does not crash', ok)
sz = get_size()
check('FE-SIZE remains 0', sz == 0, f'got {sz}')

# ---- Test 6: Single CR byte ----
print("\nTest 6: Single CR byte")
send('HEX', 0.5)
setup_buf([0x0D])
send('FE-STRIP-ALL-CR', 2)
sz = get_size()
check('FE-SIZE = 0 (CR removed)', sz == 0, f'got {sz}')

# ---- Test 7: Multi-line CRLF (hello.txt pattern) ----
# "Line one.\r\nLine two.\r\n" = 22 bytes → 20 bytes
print("\nTest 7: Multi-line CRLF (hello.txt pattern)")
send('HEX', 0.5)
data = [0x4C, 0x69, 0x6E, 0x65, 0x20, 0x6F, 0x6E, 0x65,
        0x2E, 0x0D, 0x0A,
        0x4C, 0x69, 0x6E, 0x65, 0x20, 0x74, 0x77, 0x6F,
        0x2E, 0x0D, 0x0A]
setup_buf(data)
send('FE-STRIP-ALL-CR', 3)
sz = get_size()
check('FE-SIZE = 20 (2 CRs removed)', sz == 20, f'got {sz}')
# Verify no CR bytes remain (13 = 0x0D in decimal)
cr_found = False
for i in range(20):
    b = get_byte(i)
    if b == 13:
        cr_found = True
        break
check('No CR bytes remain in buffer', not cr_found)

# ---- Final ----
print("\nFinal check:")
ok = alive()
check('System alive after all tests', ok)
if ok:
    r = send('.S', 1)
    check('Stack clean', '<>' in r, f'stack: {r.strip()!r}')

print(f'\nPassed: {PASS}/{PASS + FAIL}')
s.close()
sys.exit(0 if FAIL == 0 else 1)
