#!/usr/bin/env python3
"""
test_ahci_write.py -- AHCI write command test.

Requires QEMU with ICH9-AHCI and a scratch disk.
Boots ForthOS, loads AHCI vocab, inits the controller,
then tests write/read-back and safety guards.

Usage: python3 tests/test_ahci_write.py [port]
"""

import socket
import time
import sys
import subprocess
import os

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4575
PROJECT_DIR = os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))

PASS = FAIL = 0


def get_vocab_blocks(vocab_name):
    try:
        result = subprocess.run(
            [sys.executable, '-c', f"""
import sys, os
sys.path.insert(0, os.path.join('{PROJECT_DIR}', 'tools'))
from importlib.machinery import SourceFileLoader
wc = SourceFileLoader('wc', os.path.join(
    '{PROJECT_DIR}', 'tools', 'write-catalog.py'
)).load_module()
vocabs = wc.scan_vocabs(os.path.join(
    '{PROJECT_DIR}', 'forth', 'dict'))
_nc = (len(vocabs) + wc.CATALOG_DATA_LINES - 1) // wc.CATALOG_DATA_LINES
nb = 1 + _nc
for v in vocabs:
    if v['name'] == '{vocab_name}':
        print(f"{{nb}} {{nb + v['blocks_needed'] - 1}}")
        break
    nb += v['blocks_needed']
"""],
            capture_output=True, text=True, timeout=10
        )
        if result.stdout.strip():
            parts = result.stdout.strip().split()
            return int(parts[0]), int(parts[1])
    except Exception:
        pass
    return None, None


def check(name, ok, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {name}')
    else:
        FAIL += 1
        print(f'  FAIL: {name}' +
              (f' -- {detail}' if detail else ''))


print(f'AHCI Write Test (port {PORT})')
print('=' * 50)

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


def send(cmd, wait=2.0):
    s.sendall((cmd + '\r').encode())
    time.sleep(wait)
    s.settimeout(3)
    resp = b''
    while True:
        try:
            d = s.recv(8192)
            if not d:
                break
            resp += d
        except Exception:
            break
    return resp.decode('ascii', errors='replace')


def alive():
    r = send('1 2 + .', 1)
    return '3' in r


# Load AHCI vocab
ahci_start, ahci_end = get_vocab_blocks('AHCI')
if not ahci_start:
    print("FAIL: Cannot find AHCI blocks")
    sys.exit(1)

print(f'\nLoading AHCI ({ahci_start} {ahci_end} THRU)...')
r = send(f'{ahci_start} {ahci_end} THRU', 15)
check('AHCI vocab loads',
      'ok' in r and '?' not in r,
      repr(r.strip()[-60:]))

# USING AHCI
print('\nTest 1: Vocabulary accessible')
r = send('USING AHCI', 2)
check('USING AHCI succeeds',
      'ok' in r and '?' not in r,
      repr(r.strip()[:60]))

# AHCI-INIT
print('\nTest 2: AHCI initialization')
r = send('AHCI-INIT', 5)
ahci_ok = 'AHCI ok' in r
check('AHCI-INIT finds ICH9 controller',
      ahci_ok,
      repr(r.strip()[:80]))

if not ahci_ok:
    print("FATAL: AHCI not initialized, cannot test writes")
    s.close()
    print(f'\nPassed: {PASS}/{PASS + FAIL}')
    sys.exit(1)

# Test 3: WRITE-TEST (default LBA 0x100)
print('\nTest 3: WRITE-TEST (write+readback)')
r = send('HEX WRITE-TEST', 5)
check('WRITE-TEST signature verified',
      'OK' in r and 'FAIL' not in r and 'MISMATCH' not in r,
      repr(r.strip()[:80]))

# Test 4: LBA 0 guard
print('\nTest 4: LBA 0 refusal')
r = send('HEX 0 TST-LBA ! WRITE-TEST', 5)
check('Refuses write to LBA 0',
      'REFUSE' in r,
      repr(r.strip()[:80]))

# Test 5: Different LBA
print('\nTest 5: Write to LBA 0x200')
r = send('HEX 200 TST-LBA !', 1)
r = send('WRITE-TEST', 5)
check('WRITE-TEST at LBA 0x200 OK',
      'OK' in r and 'FAIL' not in r,
      repr(r.strip()[:80]))

# Test 6: Write different pattern
print('\nTest 6: Different pattern')
r = send('HEX BEEF WR-TST !', 1)
r = send('TST-LBA @ 1 WR-TST AHCI-WRITE .', 3)
check('AHCI-WRITE returns 0 (success)',
      '0 ' in r or '\n0 ' in r or 'ok' in r,
      repr(r.strip()[:80]))

# Read back and verify pattern
r = send('TST-LBA @ 1 AHCI-READ .', 3)
check('Read-back succeeds',
      '0 ' in r or '\n0 ' in r,
      repr(r.strip()[:80]))

r = send('SEC-BUF @ .', 2)
# BEEF hex = 48879 decimal (signed: 48879)
check('Read-back matches BEEF',
      '48879' in r or 'BEEF' in r.upper(),
      repr(r.strip()[:80]))

# Test 7: Overwrite verification
print('\nTest 7: Overwrite old data')
r = send('HEX 100 TST-LBA !', 1)
r = send('HEX CAFE WR-TST !', 1)
r = send('TST-LBA @ 1 WR-TST AHCI-WRITE .', 3)
check('Overwrite succeeds',
      '0 ' in r or '\n0 ' in r,
      repr(r.strip()[:80]))

r = send('TST-LBA @ 1 AHCI-READ .', 3)
r = send('SEC-BUF @ .', 2)
# CAFE hex = 51966 decimal
check('Overwrite data matches CAFE',
      '51966' in r or 'CAFE' in r.upper(),
      repr(r.strip()[:80]))

# Test 8: System alive
print('\nTest 8: System alive')
check('System alive after write tests', alive())

# Test 9: Stack clean
print('\nTest 9: Stack clean')
r = send('.S', 2)
check('Stack clean',
      '<>' in r,
      repr(r.strip()[:60]))

s.close()

print(f'\nPassed: {PASS}/{PASS + FAIL}')
sys.exit(0 if FAIL == 0 else 1)
