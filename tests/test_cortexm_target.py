#!/usr/bin/env python3
"""Test Cortex-M33 metacompilation (runtimes + primitives).

Loads META-COMPILER, THUMB2-ASM, TARGET-CORTEX-M, runs
META-COMPILE-CORTEXM, verifies symbol count and status.

Usage:
    python3 tests/test_cortexm_target.py [PORT]
"""
import socket
import time
import sys
import subprocess
import os

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4592

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


vocabs_needed = [
    'X86-ASM', 'META-COMPILER',
    'THUMB2-ASM', 'TARGET-CORTEX-M'
]
blocks = {}
for v in vocabs_needed:
    s, e = get_vocab_blocks(v)
    if s is None:
        print(f"FAIL: {v} not in catalog")
        sys.exit(1)
    blocks[v] = (s, e)
    print(f"  {v}: blocks {s}-{e}")

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


def extract_number(text):
    words = text.replace('\r', ' ').replace('\n', ' ').split()
    for i in range(len(words) - 1, -1, -1):
        if words[i] in ('ok', 'OK'):
            if i > 0:
                try:
                    return int(words[i - 1])
                except ValueError:
                    pass
    for word in words:
        word = word.strip()
        if word in ('ok', 'OK', ''):
            continue
        try:
            return int(word)
        except ValueError:
            continue
    return None


PASS = FAIL = 0


def check(name, ok, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {name}')
    else:
        FAIL += 1
        msg = f'  FAIL: {name}'
        if detail:
            msg += f' -- {detail}'
        print(msg)


def alive():
    r = send('1 2 + .', 1)
    return '3' in r


# ---- Load all vocabs ----
print('\nLoading vocabs...')
for v in vocabs_needed:
    sb, eb = blocks[v]
    print(f'  {v} ({sb}-{eb})...')
    r = send(f'DECIMAL {sb} {eb} THRU', 15)
    ok = alive()
    check(f'{v} loads', ok,
          f'resp: {r.strip()[:80]!r}')
    if not ok:
        s.close()
        print(f'\nPassed: {PASS}/{PASS + FAIL}')
        sys.exit(1)

# ---- Run metacompiler (phase A) ----
print('\nRunning META-COMPILE-CORTEXM...')
r = send('META-COMPILE-CORTEXM', 30)
print(f'  MC output: {r.strip()[:200]!r}')
ok = alive()
check('META-COMPILE-CORTEXM completes', ok)

if not ok:
    s.close()
    print(f'\nPassed: {PASS}/{PASS + FAIL}')
    sys.exit(1)

# Check META-OK
r = send('META-OK @ .', 1)
val = extract_number(r)
check('META-OK = 1', val == 1,
      f'got: {val}')

# Check symbol count
r = send('DECIMAL TSYM-N @ .', 1)
val = extract_number(r)
check('Symbol count >= 50',
      val is not None and val >= 50,
      f'got: {val}')

# Check image size
r = send('META-SIZE DECIMAL .', 1)
val = extract_number(r)
check('Image size > 0',
      val is not None and val > 0,
      f'got: {val}')

# System alive
check('System alive after MC', alive())

# Stack clean
r = send('.S', 1)
check('Stack clean', '<>' in r,
      f'got: {r.strip()[:40]!r}')

s.close()
print(f'\nPassed: {PASS}/{PASS + FAIL}')
sys.exit(0 if FAIL == 0 else 1)
