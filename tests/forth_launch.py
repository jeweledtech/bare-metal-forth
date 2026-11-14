#!/usr/bin/env python3
"""forth_launch.py - boot the in-machine test image and read its verdict
(TASK_FORTH_TEST_RUNNER step 6, `make test-forth`).

The checking happens inside the machine (tests/forth/). This script only
boots a copy of the test image, checks the banner, types the start line
the build wrote to TEST_IMG.start, waits, kills its own QEMU by PID, and
compares RESULT lines with EXPECTED. It knows nothing about the tests.

It reads until every suite in EXPECTED has printed its RESULT line, or a
RESULT FAIL or ABORT line appears, or TIMEOUT. A RESULT line passes when
it reads `RESULT <NAME> PASS n/n` and EXPECTED holds `<NAME> PASS n`. A
missing suite, an unlisted suite, a wrong or missing banner each fail.

Usage: forth_launch.py TEST_IMG PRODUCT EXPECTED PORT [TIMEOUT]
"""
import hashlib
import os
import re
import shutil
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import qemu_pid                      # noqa: E402
import serial as ser                 # noqa: E402

RESULT = re.compile(r'^RESULT (\S+) (PASS|FAIL|ABORT)\b(.*)$')


def stamp(what):
    print(f'{what} {time.strftime("%Y-%m-%d %H:%M:%S")}', flush=True)


def main(argv):
    if len(argv) not in (4, 5):
        sys.exit(__doc__)
    img, product, expected_path = argv[0], argv[1], argv[2]
    port = int(sys.argv[4])    # from sys.argv: port_inventory traces it
    timeout = float(argv[4]) if len(argv) == 5 else 120.0
    start = open(img + '.start').read().strip()
    tag = hashlib.sha256(open(product, 'rb').read()).hexdigest()[:8]
    want = {}
    for ln in open(expected_path).read().splitlines():
        if ln.strip():
            name, verdict, n = ln.split()
            want[name] = (verdict, int(n))
    work = os.path.join(os.path.dirname(os.path.abspath(img)), 'forth.d')
    os.makedirs(work, exist_ok=True)
    pf = os.path.join(work, 'qemu.pid')
    fl, ide = os.path.join(work, 'floppy.img'), os.path.join(work, 'ide.img')
    qemu_pid.kill_pidfile(pf)
    shutil.copyfile(img, fl)          # run from copies (R6): the
    shutil.copyfile(img, ide)         # built image is never written
    print(f'image {img}  banner wanted TEST-IMAGE {tag}', flush=True)
    print(f'start line: {start}', flush=True)
    stamp('start')
    t0 = time.time()
    q = subprocess.run(['qemu-system-i386', '-drive', f'file={fl},format=raw,if=floppy', '-m', '256',
                        '-drive', f'file={ide},format=raw,if=ide,index=1', '-display', 'none',
                        '-serial', f'tcp:127.0.0.1:{port},server=on,wait=off',
                        '-daemonize', '-pidfile', pf], capture_output=True)
    qemu_pid.check_launch(q, pf, port, 'test-forth')
    seen, banner, why = {}, None, 'timeout'
    try:
        s = ser.connect_and_sync(port, budget=60)
        s.sendall(start.encode('ascii') + b'\r')
        buf, deadline = '', t0 + timeout
        while time.time() < deadline:
            try:
                d = s.recv(4096)
            except socket.timeout:
                continue
            if not d:
                why = 'serial closed'
                break
            buf += d.decode('ascii', errors='replace')
            *lines, buf = buf.split('\n')
            done = False
            for ln in (x.strip('\r ') for x in lines):
                print(f'  | {ln}', flush=True)
                if ln.startswith('TEST-IMAGE ') and banner is None:
                    banner = ln.split()[1]
                m = RESULT.match(ln)
                if m:
                    seen.setdefault(m.group(1), []).append((m.group(2), m.group(3).strip()))
                    if m.group(2) != 'PASS':
                        done, why = True, f'RESULT {m.group(2)}'
                    elif set(want) <= set(seen):
                        done, why = True, 'every suite reported'
            if done:
                break
            if banner is not None and banner != tag:
                why = 'wrong banner'
                break
    finally:
        qemu_pid.kill_pidfile(pf)
    stamp('end')
    print(f'elapsed {time.time() - t0:.1f} s, read ended by: {why}', flush=True)

    bad, matched = [], 0
    if banner != tag:
        bad.append(f'banner: want TEST-IMAGE {tag}, got {banner}')
    for name, (verdict, n) in want.items():
        got = seen.get(name)
        if not got:
            bad.append(f'{name}: no RESULT line')
            continue
        v, rest = got[-1]
        if len(got) > 1 or v != verdict or rest != f'{n}/{n}':
            bad.append(f'{name}: want {verdict} {n}/{n}, got {v} {rest}')
        else:
            print(f'  match: {name} {verdict} {n}/{n}', flush=True)
            matched += 1
    for name in seen:
        if name not in want:
            bad.append(f'{name}: not listed in {expected_path}')
    for b in bad:
        print(f'  FAIL: {b}', flush=True)
    print(f'test-forth: {"PASS" if not bad else "FAIL"} '
          f'({matched}/{len(want)} suites as expected)', flush=True)
    return 0 if not bad else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
