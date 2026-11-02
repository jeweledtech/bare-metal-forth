#!/usr/bin/env python3
"""The build is pinned to nasm 2.16.01 (owner 2026-11-02, private
TASK_UNICORN_WRITER rule 5).  The committed kernel hashes are 2.16.01's;
nasm 3.01 assembles a different kernel.bin from the same source.

Checks, all host-side through `make -n` (nothing is built), with fake nasm
binaries that print a version line:
  P1 NASM pointing at a 3.01 nasm: make refuses, exit != 0, says 2.16.01
     is needed and how to install it
  P2 NASM pointing at nothing runnable: refused the same way
  P3 a bare `make` (no goal) with a 3.01 `nasm` first on PATH: refused
  P4 NASM pointing at a 2.16.01 nasm: accepted, and the kernel rule's
     dry-run command names that binary
  P5 `make -n clean` with a 3.01 nasm: not refused (clean needs no nasm)
  P6 every Python caller that assembles (tools/pad_report.py,
     tests/test_abort_routes.py, tests/test_interp_abort.py) takes the
     binary from $NASM, which the Makefile exports
"""
import os
import re
import stat
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASS = FAIL = 0


def check(name, ok, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {name}')
    else:
        FAIL += 1
        print(f'  FAIL: {name} -- {detail}')


def fake(d, ver):
    p = os.path.join(d, f'nasm-{ver}', 'nasm')
    os.makedirs(os.path.dirname(p))
    with open(p, 'w') as f:
        f.write(f'#!/bin/sh\necho "NASM version {ver} compiled on Jan  1 2026"\n')
    os.chmod(p, os.stat(p).st_mode | stat.S_IXUSR)
    return p


def make(args, path=None):
    env = {k: v for k, v in os.environ.items()
           if k not in ('MAKEFLAGS', 'MFLAGS', 'MAKELEVEL', 'NASM')}
    if path:
        env['PATH'] = path + os.pathsep + env['PATH']
    r = subprocess.run(['make', '-n', '-C', ROOT] + args, env=env,
                       capture_output=True, text=True, timeout=120)
    return r.returncode, r.stdout + r.stderr


print('=== nasm pinned to 2.16.01 ===')
with tempfile.TemporaryDirectory() as d:
    bad, good = fake(d, '3.01'), fake(d, '2.16.01')
    HINT = 'releasebuilds/2.16.01'

    rc, out = make([f'NASM={bad}', 'build/kernel.bin'])
    check('P1 NASM at a 3.01 nasm: refused, names 2.16.01 and how to install it',
          rc != 0 and 'nasm 2.16.01 required' in out and HINT in out
          and 'version 3.01' in out, f'rc {rc}: {out[-300:]!r}')

    rc, out = make([f'NASM={os.path.join(d, "absent", "nasm")}', 'build/kernel.bin'])
    check('P2 NASM at nothing runnable: refused', rc != 0 and 'nasm 2.16.01 required' in out
          and 'not runnable' in out, f'rc {rc}: {out[-300:]!r}')

    rc, out = make([], path=os.path.dirname(bad))
    check('P3 bare make, a 3.01 nasm first on PATH: refused',
          rc != 0 and 'nasm 2.16.01 required' in out, f'rc {rc}: {out[-300:]!r}')

    rc, out = make([f'NASM={good}', '-B', 'build/kernel.bin'])
    check('P4 NASM at a 2.16.01 nasm: accepted, the kernel rule runs that binary',
          rc == 0 and re.search(re.escape(good) + r' -f bin -o build/kernel\.bin', out) is not None,
          f'rc {rc}: {out[-400:]!r}')

    rc, out = make([f'NASM={bad}', 'clean'])
    check('P5 make -n clean with a 3.01 nasm: not refused',
          rc == 0 and 'required' not in out, f'rc {rc}: {out[-300:]!r}')

callers = ['tools/pad_report.py', 'tests/test_abort_routes.py', 'tests/test_interp_abort.py']
bare = [c for c in callers
        if re.search(r"\[\s*'nasm'", open(os.path.join(ROOT, c)).read())
        or "os.environ.get('NASM'" not in open(os.path.join(ROOT, c)).read()]
mk = open(os.path.join(ROOT, 'Makefile')).read()
check('P6 the assembling Python callers take $NASM, which the Makefile exports',
      not bare and re.search(r'^export NASM\b', mk, re.M) is not None,
      f'bare nasm in {bare}; export NASM {"present" if "export NASM" in mk else "absent"}')

print(f'\nPassed: {PASS}/{PASS + FAIL}')
sys.exit(0 if FAIL == 0 else 1)
