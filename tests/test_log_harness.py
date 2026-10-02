#!/usr/bin/env python3
"""LOG-HARNESS Phase 1 smoke test.

Loads the LOG-HARNESS vocab, runs TEST-ACTIVATION (which builds synthetic
Ethernet+IPv4+UDP frames with KEY=0xDEADBEEF and RESPONSE=0xCAFEBABE
payloads and feeds them through INSPECT-PACKET), then asserts:
  - the two activation frames both trigger marker hits
  - the serial mirror of LOG-TRANSACTION shows the expected payload hex
  - LOG-COUNT advances past zero and LOG-RESET returns it to zero
  - LOG-DUMP-TO-BLOCK writes to the TELEMETRY-reserved blocks
"""
import socket
import sys
import time

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4245

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(5)
s.connect(('127.0.0.1', PORT))

time.sleep(1.5)
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


PASS = 0
FAIL = 0


def check(name, response, pattern):
    global PASS, FAIL
    if pattern in response:
        PASS += 1
        print(f'  PASS: {name}')
    else:
        FAIL += 1
        snippet = response.strip()[:200]
        print(f'  FAIL: {name} -- expected {pattern!r} in {snippet!r}')


# Install the ATA block writer so LOG-DUMP-TO-BLOCK can persist.
# This mirrors the test-install / test-vocabs pattern.
r = send("' (BLK-WRITE-ATA) BLK-WRITER!", 2.0)
check('ATA writer installs', r, 'ok')

# Load the vocab from the catalog (then put it on search order).
# LOAD-VOCAB reads block 1 catalog, THRUs the vocab's block range;
# USING is a kernel ALSO primitive that doesn't do catalog lookup.
r = send('S" LOG-HARNESS" LOAD-VOCAB', 5.0)
check('LOAD-VOCAB succeeds', r, 'ok')
r = send('USING LOG-HARNESS', 2.0)
check('USING LOG-HARNESS activates', r, 'ok')

# Run the Phase 1 synthetic activation
r = send('TEST-ACTIVATION', 2.0)
check('TEST-ACTIVATION runs', r, 'TEST-ACTIVATION phase 1')
check('challenge marker hit', r, 'challenge: marker hit')
check('response marker hit', r, 'response: marker hit')

# Serial mirror should contain the KEY= payload hex (4B 45 59 3D)
check('challenge payload hex', r, '4B 45 59 3D')
# And the RESPONSE payload hex (52 45 53 50 = "RESP")
check('response payload hex', r, '52 45 53 50')

# Ring should have records after activation (print count as hex)
r = send('LOG-COUNT @ .', 1.0)
# count should be 2 * (8 header + payload). For KEY=... (14) and
# RESPONSE=... (19) that's 2*8 + 14 + 19 = 49 = 0x31. Non-zero.
# Match that we get a positive hex value, not just '0 ok'.
if ' 0 ok' in r or ' 0\r\nok' in r:
    FAIL += 1
    print(f'  FAIL: LOG-COUNT advanced -- got {r.strip()[:100]!r}')
else:
    PASS += 1
    print('  PASS: LOG-COUNT advanced')

# LOG-RESET should zero the count
r = send('LOG-RESET LOG-COUNT @ .', 1.0)
# Response is like 'LOG-RESET LOG-COUNT @ .\r\n0 ok' — '0 ok' trailing.
if '\n0 ok' in r or r.rstrip().endswith('0 ok'):
    PASS += 1
    print('  PASS: LOG-RESET empties ring')
else:
    FAIL += 1
    print(f'  FAIL: LOG-RESET empties ring -- got {r.strip()[:100]!r}')

# Block persistence: run activation again, dump to block, verify
# the reserved block constant is where we expect it (208 decimal / D0 hex)
r = send('TEST-ACTIVATION LOG-DUMP-TO-BLOCK', 2.0)
check('LOG-DUMP-TO-BLOCK runs', r, 'response: marker hit')

# Verify LOG-BLOCK-FIRST matches the TELEMETRY_RESERVED range (208 dec = D0 hex)
r = send('LOG-BLOCK-FIRST .', 1.0)
check('LOG-BLOCK-FIRST = 0xD0', r, 'D0')

# After dumping, reading the block back should show the record header
# starting with timestamp bytes followed by port 0x1234 at offset 4-5
r = send('LOG-BLOCK-FIRST BLOCK 20 DUMP', 2.0)
# Challenge was logged first with dport=0x1234, so bytes 4-5 of first
# record are 12 34
check('block contains port bytes', r, '12 34')

# Final summary
print()
TOTAL = PASS + FAIL
print(f'Passed: {PASS}/{TOTAL}')
s.close()
sys.exit(0 if FAIL == 0 else 1)
