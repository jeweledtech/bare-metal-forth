#!/usr/bin/env python3
"""LOG-HARNESS Phase 2 NIC test.

Boots QEMU with a real NE2000 and a filter-dump pcap capture of all
NIC traffic. Loads NE2000 and LOG-HARNESS, calls NE2K-INIT and
TEST-ACTIVATION-NIC, then verifies:
  - the challenge frame actually left the NIC (parsed from the pcap)
  - the serial transcript shows the TX marker hit
  - the RX poll loop ran and timed out (RX round-trip verification is
    deferred to Phase 2.5; QEMU SLiRP's gateway stub does not forward
    guest UDP to a host-side loopback listener on an arbitrary port)
"""
import os
import socket
import struct
import sys
import time

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4246
PCAP_PATH = sys.argv[2] if len(sys.argv) > 2 else '/tmp/log-harness-nic.pcap'


s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(10)
s.connect(('127.0.0.1', PORT))
time.sleep(1.5)
try:
    while True:
        s.recv(8192)
except Exception:
    pass


def send(cmd, wait=1.5):
    s.sendall((cmd + '\r').encode())
    time.sleep(wait)
    s.settimeout(5)
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


# Setup: ATA writer, LOG-HARNESS, NE2000, NE2K-INIT
r = send("' (BLK-WRITE-ATA) BLK-WRITER!", 1.0)
check('ATA writer installs', r, 'ok')
r = send('S" LOG-HARNESS" LOAD-VOCAB', 5.0)
check('LOG-HARNESS LOAD-VOCAB', r, 'ok')
r = send('USING LOG-HARNESS USING NE2000 NE2K-INIT', 3.0)
check('NE2K-INIT finds card', r, 'NE2000 at')

# Fire the NIC activation
r = send('TEST-ACTIVATION-NIC', 15.0)
check('TEST-ACTIVATION-NIC banner', r, 'TEST-ACTIVATION-NIC phase 2')
check('TX marker hit', r, 'nic tx: marker hit')
# RX round-trip is deferred (SLiRP constraint); the poll loop should
# complete via timeout, which proves the pipeline is wired.
# RX poll should complete via one of three paths:
#   - timeout: no frame arrived within the deadline
#   - marker hit: a frame arrived, INSPECT-PACKET matched a marker
#   - no marker: a frame arrived (e.g. SLiRP's ARP probe for the
#     guest MAC), INSPECT-PACKET correctly classified it as non-match
# All three prove the poll loop + INSPECT-PACKET pipeline is wired.
if any(p in r for p in (
        'nic rx: timeout',
        'nic rx: marker hit',
        'nic rx: no marker')):
    PASS += 1
    print('  PASS: RX poll pipeline completes')
else:
    FAIL += 1
    print(f'  FAIL: RX poll never completed; got {r.strip()[-200:]!r}')

# Serial-mirror should include the KEY= payload hex
check('TX payload hex visible on serial', r, '4B 45 59 3D')

s.close()

# Verify the challenge frame actually left the NIC by parsing the pcap.
# PCAP file format (little-endian): 24-byte global header, then per-frame:
#   ts_sec(4) ts_usec(4) incl_len(4) orig_len(4) frame_bytes...
if not os.path.exists(PCAP_PATH):
    FAIL += 1
    print(f'  FAIL: pcap missing at {PCAP_PATH}')
else:
    with open(PCAP_PATH, 'rb') as f:
        data = f.read()
    if len(data) < 24:
        FAIL += 1
        print(f'  FAIL: pcap too short ({len(data)} bytes)')
    else:
        frames = []
        off = 24
        while off + 16 <= len(data):
            ts_s, ts_u, incl, orig = struct.unpack('<IIII', data[off:off + 16])
            off += 16
            if off + incl > len(data):
                break
            frames.append(data[off:off + incl])
            off += incl

        if not frames:
            FAIL += 1
            print('  FAIL: pcap has no frames')
        else:
            PASS += 1
            print(f'  PASS: pcap has {len(frames)} frame(s)')

            # Find a frame matching our challenge: EtherType 0x0800
            # (IPv4), proto 0x11 (UDP), dst port 0x1234, payload
            # starts with "KEY=0xDE".
            found_tx = False
            for fr in frames:
                if len(fr) < 42:
                    continue
                etype = (fr[12] << 8) | fr[13]
                if etype != 0x0800:
                    continue
                ihl = (fr[14] & 0x0F) * 4
                proto = fr[14 + 9]
                if proto != 0x11:
                    continue
                l4 = 14 + ihl
                if l4 + 8 > len(fr):
                    continue
                dport = (fr[l4 + 2] << 8) | fr[l4 + 3]
                if dport != 0x1234:
                    continue
                payload = fr[l4 + 8:]
                if payload.startswith(b'KEY=0xDE'):
                    found_tx = True
                    break

            if found_tx:
                PASS += 1
                print('  PASS: challenge TX frame in pcap '
                      '(IPv4+UDP, dport=0x1234, KEY= payload)')
            else:
                FAIL += 1
                print('  FAIL: no challenge TX frame found in pcap')


print()
TOTAL = PASS + FAIL
print(f'Passed: {PASS}/{TOTAL}')
sys.exit(0 if FAIL == 0 else 1)
