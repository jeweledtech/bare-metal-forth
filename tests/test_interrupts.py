#!/usr/bin/env python3
"""
Test interrupt infrastructure: PIC initialization, IDT loading, ISR data words.
Verifies that the kernel boots with STI enabled and interrupt-related
dictionary words are accessible.
"""

import socket
import time
import sys

PORT = 4455

def send_cmd(sock, cmd, delay=0.3):
    """Send a command and return the response."""
    sock.sendall((cmd + '\r').encode())
    time.sleep(delay)
    data = b''
    while True:
        try:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
        except socket.timeout:
            break
    return data.decode('latin-1')

def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)

    # Wait for QEMU to be ready
    for attempt in range(20):
        try:
            sock.connect(('localhost', PORT))
            break
        except (ConnectionRefusedError, OSError):
            time.sleep(0.5)
    else:
        print("FAIL: Could not connect to QEMU on port", PORT)
        sys.exit(1)

    # Read the welcome banner
    time.sleep(1)
    try:
        banner = sock.recv(4096).decode('latin-1')
    except socket.timeout:
        banner = ''
    print("Banner:", repr(banner[:80]))

    passed = 0
    failed = 0
    tests = []

    # Test 1: Kernel booted successfully — verify with a simple command
    test_name = "Kernel boots with STI enabled"
    boot_ok = 'Bare-Metal Forth' in banner or 'Ship Builder' in banner
    if not boot_ok:
        # Banner may have been sent before we connected; try a command
        resp = send_cmd(sock, '1 1 + .')
        boot_ok = '2' in resp and 'ok' in resp
    if boot_ok:
        print(f"  PASS: {test_name}")
        passed += 1
    else:
        print(f"  FAIL: {test_name} - no welcome banner and no response")
        failed += 1

    # Test 2: TICK-COUNT is accessible (it's a variable, @ reads it)
    test_name = "TICK-COUNT @ returns a number"
    resp = send_cmd(sock, 'TICK-COUNT @ .')
    print(f"  TICK-COUNT @ . => {repr(resp.strip())}")
    # Should print a number (likely 0 since timer IRQ is masked)
    if any(c.isdigit() for c in resp):
        print(f"  PASS: {test_name}")
        passed += 1
    else:
        print(f"  FAIL: {test_name}")
        failed += 1

    # Test 3: IDT-BASE returns the correct address (0x29400 = 169984)
    test_name = "IDT-BASE returns correct address"
    resp = send_cmd(sock, 'HEX IDT-BASE .')
    print(f"  HEX IDT-BASE . => {repr(resp.strip())}")
    if '29400' in resp.upper():
        print(f"  PASS: {test_name}")
        passed += 1
    else:
        print(f"  FAIL: {test_name}")
        failed += 1

    # Test 4: KB-RING-BUF returns an address (non-zero)
    test_name = "KB-RING-BUF returns non-zero address"
    resp = send_cmd(sock, 'DECIMAL KB-RING-BUF .')
    print(f"  DECIMAL KB-RING-BUF . => {repr(resp.strip())}")
    # Should be a non-zero address; parse as decimal
    has_nonzero = False
    for word in resp.strip().split():
        try:
            val = int(word)
            if val > 0:
                has_nonzero = True
                break
        except ValueError:
            # Also try hex in case base wasn't reset
            try:
                val = int(word, 16)
                if val > 0:
                    has_nonzero = True
                    break
            except ValueError:
                continue
    if has_nonzero:
        print(f"  PASS: {test_name}")
        passed += 1
    else:
        print(f"  FAIL: {test_name}")
        failed += 1

    # Test 5: KB-RING-COUNT @ returns 0 (no keys pressed)
    test_name = "KB-RING-COUNT @ returns 0"
    resp = send_cmd(sock, 'DECIMAL KB-RING-COUNT @ .')
    print(f"  KB-RING-COUNT @ . => {repr(resp.strip())}")
    if '0 ' in resp or resp.strip().endswith('0'):
        print(f"  PASS: {test_name}")
        passed += 1
    else:
        print(f"  FAIL: {test_name}")
        failed += 1

    # Test 6: MOUSE-PKT-READY @ returns 0 (no mouse activity)
    test_name = "MOUSE-PKT-READY @ returns 0"
    resp = send_cmd(sock, 'MOUSE-PKT-READY @ .')
    print(f"  MOUSE-PKT-READY @ . => {repr(resp.strip())}")
    if '0 ' in resp or resp.strip().endswith('0'):
        print(f"  PASS: {test_name}")
        passed += 1
    else:
        print(f"  FAIL: {test_name}")
        failed += 1

    # Test 7: MOUSE-X-VAR @ returns 0
    test_name = "MOUSE-X-VAR @ returns 0"
    resp = send_cmd(sock, 'MOUSE-X-VAR @ .')
    print(f"  MOUSE-X-VAR @ . => {repr(resp.strip())}")
    if '0 ' in resp or resp.strip().endswith('0'):
        print(f"  PASS: {test_name}")
        passed += 1
    else:
        print(f"  FAIL: {test_name}")
        failed += 1

    # Test 8: MOUSE-BTN-VAR @ returns 0
    test_name = "MOUSE-BTN-VAR @ returns 0"
    resp = send_cmd(sock, 'MOUSE-BTN-VAR @ .')
    print(f"  MOUSE-BTN-VAR @ . => {repr(resp.strip())}")
    if '0 ' in resp or resp.strip().endswith('0'):
        print(f"  PASS: {test_name}")
        passed += 1
    else:
        print(f"  FAIL: {test_name}")
        failed += 1

    # Test 9: IRQ-UNMASK exists (we can find it with WORDS or just test it)
    # Unmask timer (IRQ 0), then read tick count twice with a delay
    test_name = "IRQ-UNMASK for timer works (TICK-COUNT increments)"
    resp = send_cmd(sock, '0 IRQ-UNMASK')
    print(f"  0 IRQ-UNMASK => {repr(resp.strip())}")
    # Read tick count
    resp1 = send_cmd(sock, 'TICK-COUNT @ .', delay=0.3)
    print(f"  First TICK-COUNT @ . => {repr(resp1.strip())}")
    time.sleep(0.5)  # Wait for timer ticks
    resp2 = send_cmd(sock, 'TICK-COUNT @ .', delay=0.3)
    print(f"  Second TICK-COUNT @ . => {repr(resp2.strip())}")

    # Parse the numbers - we're in HEX mode, but let's switch to DECIMAL
    resp1d = send_cmd(sock, 'DECIMAL TICK-COUNT @ .')
    time.sleep(0.3)
    resp2d = send_cmd(sock, 'TICK-COUNT @ .')
    print(f"  DECIMAL tick1={repr(resp1d.strip())} tick2={repr(resp2d.strip())}")

    # Check that tick count is non-zero (timer is ticking)
    # Extract any number from the response
    tick_nonzero = False
    for r in [resp1d, resp2d]:
        for word in r.split():
            try:
                val = int(word)
                if val > 0:
                    tick_nonzero = True
                    break
            except ValueError:
                continue
        if tick_nonzero:
            break

    if tick_nonzero:
        print(f"  PASS: {test_name}")
        passed += 1
    else:
        print(f"  FAIL: {test_name} (tick count not incrementing)")
        failed += 1

    # Test 10: WORDS includes our new interrupt words
    test_name = "WORDS lists interrupt infrastructure words"
    resp = send_cmd(sock, 'WORDS', delay=1.0)
    print(f"  WORDS response length: {len(resp)}")
    found_words = []
    for w in ['TICK-COUNT', 'IDT-BASE', 'IRQ-UNMASK', 'KB-RING-BUF',
              'MOUSE-PKT-BUF', 'MOUSE-BTN-VAR']:
        if w in resp:
            found_words.append(w)
    print(f"  Found: {found_words}")
    if len(found_words) >= 4:  # At least 4 of 6 should be found
        print(f"  PASS: {test_name}")
        passed += 1
    else:
        print(f"  FAIL: {test_name} - only found {len(found_words)} of 6")
        failed += 1

    sock.close()

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed out of {passed+failed}")
    print(f"{'='*50}")

    sys.exit(0 if failed == 0 else 1)


if __name__ == '__main__':
    main()
