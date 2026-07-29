#!/usr/bin/env python3
"""Probe: does NUMBER parse full-width hex literals with bit 31 set?

Decides the form the CRC-32 polynomial and init value take in the
ADD-PARTITION source (Task 3b): a bare literal, or built from halves.

Each probe shifts right by 1 before printing. That is what makes it
decisive -- a bare `EDB88320 .` cannot separate a parse fault from a
signed-print quirk, but a correct logical shift of a correctly-parsed
value has exactly one answer, with the high bit cleared.

Probes are typed bare: no `( )` stack comments, which wedge the
interpreter when typed over serial (interactive `(` blocks on read_key).
"""
import socket, time, sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4491

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


PASS = 0
FAIL = 0


def check(name, cmd, expect):
    global PASS, FAIL
    r = send(cmd)
    if expect in r.upper():
        PASS += 1
        print(f'  PASS: {name}')
        print(f'        {cmd!r} -> {r.strip()!r}')
    else:
        FAIL += 1
        print(f'  FAIL: {name}')
        print(f'        {cmd!r} expected {expect!r}, got {r.strip()!r}')


# Guard: an empty transcript from the -daemonize listener race looks
# identical to a mangled literal. Prove the VM is answering first.
r = send('HEX 1 2 + .')
if '3 ok' not in r:
    print(f'ABORT: VM not responding sanely -- {r.strip()!r}')
    s.close()
    sys.exit(2)
print('  (VM responsive, base HEX)')

# Probe 1: the CRC-32 polynomial, reflected. Bit 31 set.
check('poly EDB88320 parses', 'HEX EDB88320 1 RSHIFT .', '76DC4190')

# Probe 2: the CRC-32 init value. All bits set -- exercises the
# all-digits path of the accumulator.
check('init FFFFFFFF parses', 'HEX FFFFFFFF 1 RSHIFT .', '7FFFFFFF')

# Probe 3: the fallback form, run unconditionally. If probes 1-2 pass
# this is redundant confirmation; if they fail this is the green half
# of the pair and the CRC source uses this form.
check('fallback built-from-halves', 'HEX EDB8 10 LSHIFT 8320 OR 1 RSHIFT .', '76DC4190')

print()
TOTAL = PASS + FAIL
print(f'Passed: {PASS}/{TOTAL}')
s.close()
sys.exit(0 if FAIL == 0 else 1)
