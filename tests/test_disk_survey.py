#!/usr/bin/env python3
"""
test_disk_survey.py — Smoke test for SURVEYOR vocabulary.

Tests that the SURVEYOR vocabulary loads and its words are
accessible. Full NTFS/FAT32 scanning requires real hardware
(HP 15-bs0xx) — see docs/TASK_DISK_SURVEY.md.

Usage: python3 tests/test_disk_survey.py [port]
"""

import socket
import sys
import time

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4555
passed = 0
failed = 0


def send(sock, cmd, timeout=3):
    sock.sendall((cmd + '\r').encode())
    time.sleep(timeout)
    try:
        return sock.recv(4096).decode('ascii', errors='replace')
    except socket.timeout:
        return ''


def check(name, cond, detail=''):
    global passed, failed
    if cond:
        print(f'  PASS: {name}')
        passed += 1
    else:
        print(f'  FAIL: {name}  {detail}')
        failed += 1


def alive(sock):
    r = send(sock, '1 2 + .', 2)
    return '3' in r


print(f'SURVEYOR smoke test (port {PORT})')
print('=' * 50)

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(5)
try:
    s.connect(('127.0.0.1', PORT))
except (ConnectionRefusedError, OSError) as e:
    print(f'FAIL: Could not connect: {e}')
    sys.exit(1)

time.sleep(2)
# Drain boot output
try:
    s.recv(4096)
except socket.timeout:
    pass

# Test 1: USING SURVEYOR
print('\nTest 1: USING SURVEYOR')
r = send(s, 'USING SURVEYOR', 2)
check('USING SURVEYOR succeeds',
      '?' not in r or 'ok' in r,
      repr(r.strip()[:80]))

# Test 2: Constants are accessible
print('\nTest 2: Constants accessible')
r = send(s, 'HEX GUID-EFI .', 2)
# High bit set: . prints signed -3ED58CD8
check('GUID-EFI accessible',
      '3ED58CD8' in r.upper() or 'C12A7328' in r.upper(),
      repr(r.strip()[:80]))

r = send(s, 'MZ-SIG .', 2)
check('MZ-SIG = 5A4D',
      '5A4D' in r.upper() or '23117' in r,
      repr(r.strip()[:80]))

# Test 3: Partition table exists
print('\nTest 3: Partition table')
r = send(s, 'PART-N @ DECIMAL . HEX', 2)
check('PART-N accessible (starts at 0)',
      '0' in r,
      repr(r.strip()[:80]))

# Test 4: PARTITION-MAP runs (no AHCI = "AHCI not init")
print('\nTest 4: PARTITION-MAP graceful failure')
r = send(s, 'PARTITION-MAP', 3)
check('PARTITION-MAP handles no AHCI',
      'AHCI' in r or 'GPT' in r or 'No' in r,
      repr(r.strip()[:80]))

# Test 5: Counter variables accessible
print('\nTest 5: Counter variables')
r = send(s, 'SV-NSYS @ DECIMAL . HEX', 2)
check('SV-NSYS accessible',
      '0' in r,
      repr(r.strip()[:80]))

r = send(s, 'SV-NDLL @ DECIMAL . HEX', 2)
check('SV-NDLL accessible',
      '0' in r,
      repr(r.strip()[:80]))

# Test 6: PE-CHECK doesn't crash on empty buffer
print('\nTest 6: PE-CHECK on empty buffer')
r = send(s, 'PE-CHECK', 2)
check('PE-CHECK handles non-PE gracefully',
      '?' not in r,
      repr(r.strip()[:80]))

# Test 7: ELF-CHECK doesn't crash on empty buffer
print('\nTest 7: ELF-CHECK on empty buffer')
r = send(s, 'ELF-CHECK', 2)
check('ELF-CHECK handles non-ELF gracefully',
      '?' not in r,
      repr(r.strip()[:80]))

# Test 8: CLASSIFY dispatches correctly
print('\nTest 8: CLASSIFY on empty buffer')
r = send(s, 'CLASSIFY', 2)
check('CLASSIFY handles unknown format',
      'unknown' in r.lower() or 'ok' in r,
      repr(r.strip()[:80]))

# Test 9: Extension matching words exist
print('\nTest 9: Extension matching')
r = send(s, 'EXT-SYS C@ DECIMAL . HEX', 2)
check('EXT-SYS counted string (len=4)',
      '4' in r,
      repr(r.strip()[:80]))

# Test 10: DISK-SURVEY handles no AHCI
print('\nTest 10: DISK-SURVEY graceful failure')
r = send(s, 'DISK-SURVEY', 3)
check('DISK-SURVEY reports no AHCI',
      'AHCI' in r or 'Survey' in r,
      repr(r.strip()[:80]))

# Test 11: System still alive
print('\nTest 11: System alive')
check('System alive after all tests', alive(s))

# Test 12: Stack clean
print('\nTest 12: Stack clean')
r = send(s, '.S', 2)
check('Stack clean',
      '<>' in r,
      repr(r.strip()[:40]))

s.close()

print(f'\nPassed: {passed}/{passed + failed}')
sys.exit(0 if failed == 0 else 1)
