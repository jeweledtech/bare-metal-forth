#!/usr/bin/env python3
"""
test_video.py — Test VIDEO vocabulary.

Tests frame geometry constants, FRAME-ADDR math,
BMV360.TASK/TV word existence, VIDEO-TEST-FRAME.
Uses VID-START=500 (safe, well above loaded vocabs).

Usage: python3 tests/test_video.py [port]
"""

import socket
import sys
import time
import subprocess
import os

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4570
passed = 0
failed = 0

PROJECT_DIR = os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))


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
nb = 2
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


def send(sock, cmd, timeout=3):
    sock.sendall((cmd + '\r').encode())
    time.sleep(timeout)
    try:
        return sock.recv(4096).decode('ascii',
                                      errors='replace')
    except socket.timeout:
        return ''


def check(name, cond, detail=''):
    global passed, failed
    if cond:
        passed += 1
        print(f'  PASS: {name}')
    else:
        failed += 1
        msg = f'  FAIL: {name}'
        if detail:
            msg += f' -- {detail}'
        print(msg)


# ---- Resolve block ranges ----
DEPS = {}
for name in ['HARDWARE', 'PCI-ENUM', 'VGA-GRAPHICS',
             'GRAPHICS', 'AUDIO', 'VIDEO']:
    s, e = get_vocab_blocks(name)
    DEPS[name] = (s, e)
    if s is None:
        print(f"FAIL: {name} not in catalog")
        sys.exit(1)

print(f"VIDEO test (port {PORT})")
print("=" * 50)
for n, (s, e) in DEPS.items():
    print(f"  {n}: {s}-{e}")

# ---- Connect ----
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
except:
    pass

# ---- Load all dependencies in order ----
for name in ['HARDWARE', 'PCI-ENUM', 'VGA-GRAPHICS',
             'GRAPHICS', 'AUDIO', 'VIDEO']:
    vs, ve = DEPS[name]
    print(f"\nLoading {name} ({vs} {ve} THRU)...")
    r = send(s, f'{vs} {ve} THRU', 10)
    if '?' in r:
        print(f"  WARNING: {r.strip()[:60]!r}")

# ---- Set up search order ----
send(s, 'USING HARDWARE', 1)
send(s, 'ALSO PCI-ENUM', 1)
send(s, 'ALSO VGA-GRAPHICS', 1)
send(s, 'ALSO GRAPHICS', 1)
send(s, 'ALSO AUDIO', 1)
send(s, 'ALSO VIDEO', 1)

# ---- Test 1: Load ----
print("\nTest 1: VIDEO loads")
# Verify a VIDEO word is findable (not ORDER which
# shows addresses with many vocabs in search order)
r = send(s, "' BMV360.TASK .", 1)
check('VIDEO words accessible',
      '?' not in r and 'ok' in r.lower(),
      f'{r.strip()[:60]!r}')

# ---- Test 2: Frame constants ----
print("\nTest 2: Frame constants")
r = send(s, 'VID-WIDTH DECIMAL . HEX', 1)
check('VID-WIDTH = 320',
      '320' in r, f'{r.strip()!r}')
r = send(s, 'VID-HEIGHT DECIMAL . HEX', 1)
check('VID-HEIGHT = 200',
      '200' in r, f'{r.strip()!r}')
r = send(s, 'VID-FRAME-BLKS DECIMAL . HEX', 1)
check('VID-FRAME-BLKS = 63',
      '63' in r, f'{r.strip()!r}')

# ---- Test 3: FRAME-ADDR math ----
print("\nTest 3: FRAME-ADDR math")
# Set VID-START to 500 (safe block range)
send(s, 'DECIMAL 500 VID-START ! HEX', 1)
r = send(s, '0 FRAME-ADDR DECIMAL . HEX', 1)
check('FRAME-ADDR(0) = 500',
      '500' in r, f'{r.strip()!r}')
r = send(s, '1 FRAME-ADDR DECIMAL . HEX', 1)
check('FRAME-ADDR(1) = 563',
      '563' in r, f'{r.strip()!r}')

# ---- Test 4: BMP-MAGIC ----
print("\nTest 4: BMP-MAGIC")
r = send(s, 'HEX BMP-MAGIC . DECIMAL', 1)
check('BMP-MAGIC = 4D42',
      '4D42' in r.upper(), f'{r.strip()!r}')

# ---- Test 5: VID-START variable ----
print("\nTest 5: VID-START")
r = send(s, 'VID-START @ DECIMAL . HEX', 1)
check('VID-START = 500 (from test 3)',
      '500' in r, f'{r.strip()!r}')

# ---- Test 6: VID-PLAYING initial ----
print("\nTest 6: VID-PLAYING")
r = send(s, 'VID-PLAYING @ .', 1)
check('VID-PLAYING = 0',
      '0' in r.split(), f'{r.strip()!r}')

# ---- Test 7: BMV360.TASK exists ----
print("\nTest 7: BMV360.TASK exists")
r = send(s, "' BMV360.TASK . DECIMAL", 1)
check('BMV360.TASK findable',
      '?' not in r and 'ok' in r.lower(),
      f'{r.strip()!r}')

# ---- Test 8: TV exists ----
print("\nTest 8: TV exists")
r = send(s, "' TV . DECIMAL", 1)
check('TV findable',
      '?' not in r and 'ok' in r.lower(),
      f'{r.strip()!r}')

# ---- Test 9: SLIDESHOW exists ----
print("\nTest 9: SLIDESHOW exists")
r = send(s, "' SLIDESHOW . DECIMAL", 1)
check('SLIDESHOW findable',
      '?' not in r and 'ok' in r.lower(),
      f'{r.strip()!r}')

# ---- Test 10: VIDEO-INFO runs ----
print("\nTest 10: VIDEO-INFO")
r = send(s, 'DECIMAL 500 VIDEO-INFO HEX', 2)
check('VIDEO-INFO runs',
      '63' in r or 'blks' in r.lower()
      or 'frame' in r.lower(),
      f'{r.strip()[:60]!r}')

# ---- Test 11: VIDEO-TEST-FRAME ----
print("\nTest 11: VIDEO-TEST-FRAME")
# VID-START already set to 500
r = send(s, 'VIDEO-TEST-FRAME', 8)
check('VIDEO-TEST-FRAME completes',
      'ok' in r.lower(),
      f'{r.strip()[:60]!r}')

# ---- Test 12: Stack clean ----
print("\nTest 12: Stack clean")
r = send(s, '.S', 1)
check('Stack clean after all tests',
      '<>' in r,
      f'{r.strip()[:60]!r}')

# ---- Summary ----
print()
print(f'Passed: {passed}/{passed + failed}')
s.close()
sys.exit(0 if failed == 0 else 1)
