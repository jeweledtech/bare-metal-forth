#!/usr/bin/env python3
"""SHUTDOWN vocabulary test — Tier 1 (QEMU).

Boots QEMU with combined image, sends USING SHUTDOWN then
SHUTDOWN, and confirms the QEMU process terminates within
a bounded timeout.  QEMU i440FX responds to the ACPI S5
write (0x2000 to port 0x604) by exiting cleanly.

The ACPI table walk path (ACPI-SHUTDOWN) also works on
QEMU because QEMU's SeaBIOS provides standard ACPI tables
with a valid RSDP, FADT, and DSDT containing _S5_.
"""

import os
import socket
import subprocess
import sys
import time

PORT = 4495

def kill_qemu():
    subprocess.run(
        ['pkill', '-9', '-f', f'[q]emu.*{PORT}'],
        capture_output=True
    )
    time.sleep(0.5)

def start_qemu():
    kill_qemu()
    time.sleep(0.5)
    proc = subprocess.Popen([
        'qemu-system-i386',
        '-drive', 'file=build/combined.img,format=raw,if=floppy',
        '-drive', 'file=build/combined-ide.img,format=raw,if=ide,index=1',
        '-serial', f'tcp::{PORT},server=on,wait=off',
        '-display', 'none',
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(4)
    return proc

def connect():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(8)
    s.connect(('127.0.0.1', PORT))
    time.sleep(1)
    try:
        s.recv(4096)
    except socket.timeout:
        pass
    return s

def cmd(s, text, timeout=3):
    s.sendall((text + '\r').encode())
    time.sleep(timeout)
    try:
        data = b''
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            data += chunk
    except socket.timeout:
        pass
    return data.decode('ascii', errors='replace')

def chk(name, response, expected, unwanted=None):
    ok = expected in response
    if unwanted and unwanted in response:
        ok = False
    if ok:
        print(f'  PASS: {name}')
    else:
        print(f'  FAIL: {name}')
        print(f'    expected: {expected}')
        print(f'    got: {response.strip()[:200]}')
    return ok

def wait_exit(proc, timeout=10):
    """Wait for QEMU process to exit, return True if it
    exits within timeout."""
    start = time.time()
    while time.time() - start < timeout:
        ret = proc.poll()
        if ret is not None:
            return True
        time.sleep(0.5)
    return False


def main():
    passed = 0
    failed = 0
    total = 0

    print('SHUTDOWN Tier 1 Tests (QEMU)')
    print('=' * 40)

    # --- Test 1: QEMU-OFF (direct port write) ---
    print('\nTest 1: QEMU-OFF (port 0x604 shortcut)')
    proc = start_qemu()
    s = connect()

    total += 1
    r = cmd(s, 'S" SHUTDOWN" LOAD-VOCAB', 8)
    r2 = cmd(s, 'USING SHUTDOWN', 2)
    if chk('LOAD-VOCAB+USING SHUTDOWN', r2, 'ok',
           unwanted='?'):
        passed += 1
    else:
        failed += 1

    total += 1
    r = cmd(s, 'QEMU-OFF', 1)
    exited = wait_exit(proc, 10)
    if exited:
        print(f'  PASS: QEMU-OFF terminated process')
        passed += 1
    else:
        print(f'  FAIL: QEMU-OFF did not terminate')
        failed += 1
        kill_qemu()

    # --- Test 2: ACPI-SHUTDOWN (full table walk) ---
    print('\nTest 2: ACPI-SHUTDOWN (RSDP/FADT/DSDT)')
    proc = start_qemu()
    s = connect()

    total += 1
    r = cmd(s, 'S" SHUTDOWN" LOAD-VOCAB', 15)
    r2 = cmd(s, 'USING SHUTDOWN', 2)
    if chk('LOAD-VOCAB+USING SHUTDOWN (2)', r2, 'ok',
           unwanted='?'):
        passed += 1
    else:
        failed += 1

    # Probe: verify RSDP found
    total += 1
    r = cmd(s, 'SCAN-RSDP DUP . 0<> .', 3)
    if chk('SCAN-RSDP found', r, '-1'):
        passed += 1
    else:
        failed += 1

    total += 1
    r = cmd(s, 'ACPI-SHUTDOWN', 2)
    exited = wait_exit(proc, 10)
    if exited:
        print(f'  PASS: ACPI-SHUTDOWN terminated process')
        passed += 1
    else:
        print(f'  FAIL: ACPI-SHUTDOWN did not terminate')
        failed += 1
        kill_qemu()

    # --- Test 3: SHUTDOWN (user-facing word) ---
    print('\nTest 3: SHUTDOWN (user-facing)')
    proc = start_qemu()
    s = connect()

    total += 1
    r = cmd(s, 'S" SHUTDOWN" LOAD-VOCAB', 15)
    r2 = cmd(s, 'USING SHUTDOWN', 2)
    if chk('LOAD-VOCAB+USING SHUTDOWN (3)', r2, 'ok',
           unwanted='?'):
        passed += 1
    else:
        failed += 1

    total += 1
    r = cmd(s, 'SHUTDOWN', 2)
    exited = wait_exit(proc, 10)
    if exited:
        print(f'  PASS: SHUTDOWN terminated process')
        passed += 1
    else:
        print(f'  FAIL: SHUTDOWN did not terminate')
        failed += 1
        kill_qemu()

    # --- Summary ---
    print(f'\nPassed: {passed}/{total}')
    if failed:
        print(f'FAILED: {failed}')
        sys.exit(1)
    else:
        print('All tests passed.')
        sys.exit(0)


if __name__ == '__main__':
    main()
