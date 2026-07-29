#!/usr/bin/env python3
"""Probe: does the tableless CRC-32 draft produce the known answer?

Gates the CRC word against GPT-CRC32("123456789") = CBF43926 before it is
ever pointed at a GPT. That vector drives the register through
high-bit-set states, so it distinguishes a logical from an arithmetic
shift and catches a mangled polynomial constant.

Typed over serial, so block-source conventions are stripped: no `( )`
stack comments (interactive `(` is read_key-until-`)` against an
already-buffered line and wedges the VM). Definitions are split across
short lines; a colon def spanning typed lines is fine, STATE stays 1.
"""
import socket, time, sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4492

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(5)
s.connect(('127.0.0.1', PORT))

time.sleep(1.5)
try:
    while True:
        if not s.recv(4096):
            break
except Exception:
    pass


def send(cmd, wait=0.5):
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


r = send('HEX 1 2 + .')
if '3 ok' not in r:
    print(f'ABORT: VM not responding sanely -- {r.strip()!r}')
    s.close()
    sys.exit(2)
print('  (VM responsive)')

# Constants in HEX before the colon defs. Literals inside : ... ; are
# parsed by NUMBER at COMPILE time, in the base live at that moment.
SETUP = [
    'HEX',
    'EDB88320 CONSTANT GCRC-POLY',
    'FFFFFFFF CONSTANT GCRC-ONES',
    'DECIMAL',
    'VARIABLE GCRC-ACC',
    ': GCRC-BIT GCRC-ACC @ DUP 1 AND',
    '  IF 1 RSHIFT GCRC-POLY XOR ELSE 1 RSHIFT THEN',
    '  GCRC-ACC ! ;',
    ': GCRC-BYTE GCRC-ACC @ XOR GCRC-ACC !',
    '  8 0 DO GCRC-BIT LOOP ;',
    ': GPT-CRC32 GCRC-ONES GCRC-ACC ! DUP 0>',
    '  IF OVER + SWAP DO I C@ GCRC-BYTE LOOP',
    '  ELSE 2DROP THEN',
    '  GCRC-ACC @ GCRC-ONES XOR ;',
]
for line in SETUP:
    out = send(line, 0.4)
    if '?' in out:
        print(f'ABORT: undefined word while loading -- {line!r} -> {out.strip()!r}')
        s.close()
        sys.exit(2)
print('  (CRC-32 loaded, no undefined words)')

PASS = 0
FAIL = 0


def check(name, cmd, expect, wait=1.5):
    global PASS, FAIL
    r = send(cmd, wait)
    if expect in r.upper():
        PASS += 1
        print(f'  PASS: {name} -> {r.strip()!r}')
    else:
        FAIL += 1
        print(f'  FAIL: {name} expected {expect!r}, got {r.strip()!r}')


# KAT compiled in HEX so CBF43926 parses at compile time. Compare and
# branch rather than printing the value: CBF43926 has bit 31 set, so a
# signed `.` would render it negative and muddy the assertion.
send('HEX', 0.4)
send(': GCRC-KAT S" 123456789" GPT-CRC32 CBF43926 =', 0.4)
send('  IF ." KAT-OK" ELSE ." KAT-FAIL" THEN ;', 0.4)
check('KAT GPT-CRC32("123456789") = CBF43926', 'GCRC-KAT', 'KAT-OK')

# Empty input must not wedge: 0 0 DO runs once under this kernel, so
# GPT-CRC32 guards len<1. Result is GCRC-ONES XOR GCRC-ONES = 0.
#
# The assertion is wrapped in a colon def and invoked by name. Sending
# the `." EMPTY-OK"` line directly would put the expected string in the
# command echo, and the check would pass on the echo alone -- green
# even against a wedged VM. The invoking name must not contain the
# string being matched.
send(': GCRC-EMPTY HERE 0 GPT-CRC32 0 =', 0.4)
send('  IF ." EMPTY-OK" ELSE ." EMPTY-BAD" THEN ;', 0.4)
check('empty input returns 0 without wedging', 'GCRC-EMPTY', 'EMPTY-OK')

print()
TOTAL = PASS + FAIL
print(f'Passed: {PASS}/{TOTAL}')
s.close()
sys.exit(0 if FAIL == 0 else 1)
