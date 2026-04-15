#!/usr/bin/env python3
"""
test_disk_survey_phase2.py — Smoke test for Phase 2 vocabs.

Tests that DEFLATE, ZIP-READER, CAB-EXTRACT, MSI-READER,
SURVEYOR-DEEP, and SURVEYOR-DETAIL load and their words
are accessible. Full testing requires real hardware.

Usage: python3 tests/test_disk_survey_phase2.py [port]
"""

import socket
import sys
import time
import subprocess
import os

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4560

PROJECT = os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))


def get_blocks(vname):
    """Get start/end blocks for vocabulary."""
    try:
        r = subprocess.run(
            [sys.executable, '-c', f"""
import sys, os
sys.path.insert(0, os.path.join('{PROJECT}', 'tools'))
from importlib.machinery import SourceFileLoader
wc = SourceFileLoader('wc', os.path.join(
    '{PROJECT}', 'tools', 'write-catalog.py'
)).load_module()
vocabs = wc.scan_vocabs(os.path.join(
    '{PROJECT}', 'forth', 'dict'))
nb = 2
for v in vocabs:
    if v['name'] == '{vname}':
        print(f"{{nb}} {{nb + v['blocks_needed'] - 1}}")
        break
    nb += v['blocks_needed']
"""],
            capture_output=True, text=True, timeout=10
        )
        if r.stdout.strip():
            p = r.stdout.strip().split()
            return int(p[0]), int(p[1])
    except Exception:
        pass
    return None, None


# Connect with retries
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


def load_vocab(name, wait=10):
    """Load a vocabulary via THRU blocks."""
    sb, eb = get_blocks(name)
    if sb is None:
        return f'{name} not in catalog'
    cmd = f'DECIMAL {sb} {eb} THRU'
    return send(cmd, wait)


print(f'Phase 2 smoke test (port {PORT})')
print('=' * 50)

# Pre-load HARDWARE (dependency for all)
print('\nPre-load HARDWARE...')
r = load_vocab('HARDWARE', 10)
check('HARDWARE loads', alive(),
      f'resp: {r.strip()[:80]!r}')

# Test 1: Load DEFLATE
print('\nTest 1: DEFLATE')
r = load_vocab('DEFLATE', 10)
ok = alive()
check('DEFLATE loads from blocks', ok,
      f'resp: {r.strip()[:80]!r}')

r = send('USING DEFLATE', 2)
check('USING DEFLATE succeeds', alive(),
      f'resp: {r.strip()[:80]!r}')

# Test 2: DEFLATE variables
print('\nTest 2: DEFLATE variables')
r = send('DFL-SRC @ .', 1)
check('DFL-SRC accessible', '0' in r,
      f'got: {r.strip()!r}')
r = send('DFL-DST @ .', 1)
check('DFL-DST accessible', '0' in r,
      f'got: {r.strip()!r}')

# Test 3: Load ZIP-READER
print('\nTest 3: ZIP-READER')
r = load_vocab('ZIP-READER', 10)
ok = alive()
check('ZIP-READER loads from blocks', ok,
      f'resp: {r.strip()[:80]!r}')

r = send('USING ZIP-READER', 2)
check('USING ZIP-READER succeeds', alive(),
      f'resp: {r.strip()[:80]!r}')

# Test 4: ZIP counters
print('\nTest 4: ZIP counters')
r = send('ZIP-NFILES @ .', 1)
check('ZIP-NFILES accessible',
      '0' in r,
      f'got: {r.strip()!r}')

# Test 5: Load CAB-EXTRACT
print('\nTest 5: CAB-EXTRACT')
r = load_vocab('CAB-EXTRACT', 10)
ok = alive()
check('CAB-EXTRACT loads from blocks', ok,
      f'resp: {r.strip()[:80]!r}')

r = send('USING CAB-EXTRACT', 2)
check('USING CAB-EXTRACT succeeds', alive(),
      f'resp: {r.strip()[:80]!r}')

# Test 6: CAB-CHECK
print('\nTest 6: CAB-CHECK')
r = send('HEX 28200 CAB-CHECK .', 1)
check('CAB-CHECK returns 0 on non-CAB',
      '0' in r,
      f'got: {r.strip()!r}')

# Test 7: Load MSI-READER
print('\nTest 7: MSI-READER')
r = load_vocab('MSI-READER', 10)
ok = alive()
check('MSI-READER loads from blocks', ok,
      f'resp: {r.strip()[:80]!r}')

r = send('USING MSI-READER', 2)
check('USING MSI-READER succeeds', alive(),
      f'resp: {r.strip()[:80]!r}')

# Test 8: OLE2-CHECK
print('\nTest 8: OLE2-CHECK')
r = send('HEX 28200 OLE2-CHECK .', 1)
check('OLE2-CHECK returns 0 on non-OLE2',
      '0' in r,
      f'got: {r.strip()!r}')

# Test 9: Load SURVEYOR + SURVEYOR-DEEP
print('\nTest 9: SURVEYOR-DEEP')
# Load dependencies: AHCI, NTFS, FAT32, SURVEYOR
for dep in ('AHCI', 'NTFS', 'FAT32', 'SURVEYOR'):
    r = load_vocab(dep, 10)
r = load_vocab('SURVEYOR-DEEP', 10)
ok = alive()
check('SURVEYOR-DEEP loads from blocks', ok,
      f'resp: {r.strip()[:80]!r}')

r = send('USING SURVEYOR-DEEP', 2)
check('USING SURVEYOR-DEEP succeeds', alive(),
      f'resp: {r.strip()[:80]!r}')

# Test 10: Deep counters
print('\nTest 10: Deep counters')
r = send('SV-NCAB @ .', 1)
check('SV-NCAB accessible',
      '0' in r,
      f'got: {r.strip()!r}')
r = send('SV-ARCBIN @ .', 1)
check('SV-ARCBIN accessible',
      '0' in r,
      f'got: {r.strip()!r}')

# Test 11: Load SURVEYOR-DETAIL
print('\nTest 11: SURVEYOR-DETAIL')
# NTFS already loaded above
r = load_vocab('SURVEYOR-DETAIL', 10)
ok = alive()
check('SURVEYOR-DETAIL loads from blocks', ok,
      f'resp: {r.strip()[:80]!r}')

r = send('USING SURVEYOR-DETAIL', 2)
check('USING SURVEYOR-DETAIL succeeds', alive(),
      f'resp: {r.strip()[:80]!r}')

# Test 12: Detail counters
print('\nTest 12: Detail counters')
r = send('SD-NSYS @ .', 1)
check('SD-NSYS accessible',
      '0' in r,
      f'got: {r.strip()!r}')
r = send('SD-SYSTEM32 @ .', 1)
check('SD-SYSTEM32 accessible',
      '0' in r,
      f'got: {r.strip()!r}')

# Test 13: System alive
print('\nTest 13: Final health')
check('System alive after all tests', alive())

# Test 14: Stack clean
r = send('.S', 1)
check('Stack clean', '<>' in r,
      f'got: {r.strip()[:40]!r}')

s.close()

print(f'\nPassed: {PASS}/{PASS + FAIL}')
sys.exit(0 if FAIL == 0 else 1)
