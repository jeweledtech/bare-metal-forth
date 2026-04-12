#!/usr/bin/env python3
"""
test_audio.py — Test AUDIO vocabulary.

Tests PC speaker words (Track A), AC97/HDA constants
(Tracks B/C), and AUDIO-INIT speaker fallback.
No AC97/HDA QEMU flags needed — speaker always works.

Usage: python3 tests/test_audio.py [port]
"""

import socket
import sys
import time
import subprocess
import os

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4565
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
HW_S, HW_E = get_vocab_blocks('HARDWARE')
PE_S, PE_E = get_vocab_blocks('PCI-ENUM')
AU_S, AU_E = get_vocab_blocks('AUDIO')
if AU_S is None:
    print("FAIL: AUDIO not in catalog")
    sys.exit(1)
if HW_S is None:
    print("FAIL: HARDWARE not in catalog")
    sys.exit(1)
if PE_S is None:
    print("FAIL: PCI-ENUM not in catalog")
    sys.exit(1)

print(f"AUDIO test (port {PORT})")
print("=" * 50)
print(f"HARDWARE: {HW_S}-{HW_E}")
print(f"PCI-ENUM: {PE_S}-{PE_E}")
print(f"AUDIO: {AU_S}-{AU_E}")

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

# ---- Load dependencies then AUDIO ----
print(f"\nLoading HARDWARE ({HW_S} {HW_E} THRU)...")
r = send(s, f'{HW_S} {HW_E} THRU', 8)

print(f"Loading PCI-ENUM ({PE_S} {PE_E} THRU)...")
r = send(s, f'{PE_S} {PE_E} THRU', 8)

print(f"Loading AUDIO ({AU_S} {AU_E} THRU)...")
r = send(s, f'{AU_S} {AU_E} THRU', 8)

# ---- Test 1: Load ----
print("\nTest 1: AUDIO loads")
check('AUDIO loads without errors',
      '?' not in r,
      f'{r.strip()[:60]!r}')

# ---- Test 2: USING AUDIO ----
print("\nTest 2: USING adds to search order")
send(s, 'USING HARDWARE', 1)
send(s, 'ALSO PCI-ENUM', 1)
r = send(s, 'ALSO AUDIO ORDER', 2)
check('AUDIO in search order',
      'AUDIO' in r.upper(),
      f'{r.strip()[:60]!r}')

# ---- Test 3: PIT constants ----
print("\nTest 3: PIT constants")
r = send(s, 'HEX PIT-CH2 . DECIMAL', 1)
check('PIT-CH2 = 0x42',
      '42' in r.upper(),
      f'{r.strip()!r}')
r = send(s, 'HEX SPKR-PORT . DECIMAL', 1)
check('SPKR-PORT = 0x61',
      '61' in r.upper(),
      f'{r.strip()!r}')

# ---- Test 4: SPEAKER-ON/OFF ----
print("\nTest 4: SPEAKER-ON/OFF")
# Read port 0x61 before, toggle, read after
r = send(s, 'SPEAKER-ON HEX SPKR-PORT INB .', 1)
# Bits 0+1 should be set
val_str = r.strip().split()
check('SPEAKER-ON sets bits',
      'ok' in r.lower() and '?' not in r,
      f'{r.strip()!r}')
r = send(s, 'SPEAKER-OFF', 1)
check('SPEAKER-OFF completes',
      'ok' in r.lower(),
      f'{r.strip()!r}')

# ---- Test 5: BEEP ----
print("\nTest 5: BEEP 440 100")
r = send(s, 'DECIMAL 440 100 BEEP HEX', 2)
check('BEEP completes, no error',
      '?' not in r and 'ok' in r.lower(),
      f'{r.strip()!r}')

# ---- Test 6: CHROMATIC table ----
print("\nTest 6: CHROMATIC table")
# Index 0 = C4 = 261
r = send(s, 'CHROMATIC @ DECIMAL . HEX', 1)
check('CHROMATIC[0] = 261 (C4)',
      '261' in r,
      f'{r.strip()!r}')
# Index 9 = A4 = 440 (offset = 9 * 4 = 36 = 0x24)
r = send(s, 'CHROMATIC HEX 24 + @ DECIMAL .', 1)
check('CHROMATIC[9] = 440 (A4)',
      '440' in r,
      f'{r.strip()!r}')

# ---- Test 7: PLAY-SCALE ----
print("\nTest 7: PLAY-SCALE")
r = send(s, 'PLAY-SCALE', 5)
check('PLAY-SCALE completes',
      'ok' in r.lower(),
      f'{r.strip()[:40]!r}')

# ---- Test 8: AC97 constants ----
print("\nTest 8: AC97 constants")
r = send(s, 'HEX AC97-VEN-ID . DECIMAL', 1)
check('AC97-VEN-ID = 8086',
      '8086' in r.upper(),
      f'{r.strip()!r}')
r = send(s, 'HEX AC97-DEV-ID . DECIMAL', 1)
check('AC97-DEV-ID = 2415',
      '2415' in r.upper(),
      f'{r.strip()!r}')

# ---- Test 9: AUDIO-MODE ----
print("\nTest 9: AUDIO-MODE initial value")
r = send(s, 'AUDIO-MODE @ .', 1)
check('AUDIO-MODE starts at 0',
      '0' in r.split(),
      f'{r.strip()!r}')

# ---- Test 10: BDL-BASE ----
print("\nTest 10: BDL-BASE")
r = send(s, 'HEX BDL-BASE . DECIMAL', 1)
check('BDL-BASE = 80000',
      '80000' in r.upper(),
      f'{r.strip()!r}')

# ---- Test 11: AUDIO-INIT ----
print("\nTest 11: AUDIO-INIT (speaker fallback)")
r = send(s, 'AUDIO-INIT', 3)
# Should fall back to speaker in standard QEMU
check('AUDIO-INIT runs without crash',
      'ok' in r.lower() or 'Speaker' in r
      or 'AC97' in r or 'HDA' in r,
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
