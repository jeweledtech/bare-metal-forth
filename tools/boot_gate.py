#!/usr/bin/env python3
"""Boot-log gate: boot a just-built kernel image and refuse it if its boot
stream hit an undefined word (docs/TASK_INTERPRETER_CORRECTNESS.md).

  python3 tools/boot_gate.py <image>

Boots <image> from floppy (read-only), headless, serial to a file, and waits
for the `ok` prompt. Fails (exit 1) on any `<word> ? ` signature, on
`EMBED ABORTED`, or if `ok` never arrives within the budget. Exit 2 =
instrument failure (QEMU did not start). The QEMU is killed by its pidfile,
never by pattern. Needs no TCP port.
"""
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import qemu_pid  # noqa: E402

IMG = sys.argv[1]
BUDGET = 40.0
D = os.path.join(os.path.dirname(os.path.abspath(IMG)), 'boot-gate.d')
os.makedirs(D, exist_ok=True)
name = os.path.basename(IMG)
LOG = os.path.join(D, name + '.serial.log')
PF = os.path.join(D, name + '.pid')
SIG = re.compile(r'(\S+) \? ')

if os.path.exists(LOG):
    os.remove(LOG)
qemu_pid.kill_pidfile(PF)
p = subprocess.Popen(['qemu-system-i386', '-drive', f'file={IMG},format=raw,if=floppy,readonly=on',
                      '-serial', f'file:{LOG}', '-display', 'none', '-pidfile', PF],
                     stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
txt = ''
deadline = time.time() + BUDGET
try:
    while time.time() < deadline:
        if p.poll() is not None:
            print(f'BOOT GATE: QEMU exited early: {p.stderr.read().decode(errors="replace")[-200:]}')
            sys.exit(2)
        if os.path.exists(LOG):
            txt = open(LOG, 'rb').read().decode('ascii', 'replace')
            if re.search(r'\bok\b', txt):
                time.sleep(0.5)
                txt = open(LOG, 'rb').read().decode('ascii', 'replace')
                break
        time.sleep(0.25)
finally:
    qemu_pid.kill_pidfile(PF)

errs = SIG.findall(txt)
bad = []
if errs:
    bad.append(f'undefined word(s) in the boot stream: {errs}')
if 'EMBED ABORTED' in txt:
    bad.append('EMBED ABORTED')
if not re.search(r'\bok\b', txt):
    bad.append(f'no ok prompt within {BUDGET:.0f}s')
if bad:
    print(f'BOOT GATE FAILED: {IMG}: ' + '; '.join(bad))
    print('  boot log: ' + repr(txt.strip()[-300:]))
    sys.exit(1)
print(f'Boot gate OK: {IMG} reached ok, no undefined words in the boot stream')
