#!/usr/bin/env python3
"""UEFI-2 red: the kernel runs on its OWN GDT, in the kernel image.

docs/evidence/uefi-2-prereg-2026-09-28.md (with amendments).  Boot path:
bmforth.img on floppy + combined.img on IDE -- the path the amendment (a)
register lines were captured on.  At the `ok` prompt the QEMU HMP monitor's
`info registers` is read -- an instrument outside the kernel.

  1  GDT base in the kernel image, 0x7E00 <= base < 0x23E00   (the red)
  2  GDT limit >= 0x17 (three descriptors)                      (control)
  3  CS = 0x0008                                                (control)
  4  DS = ES = SS = 0x0010                                      (control)
  5  interpreter alive after the PCI-BAR THRU (blocks load)     (control)

While the name is in UEFI_REDS: check 1 failing with 2-5 passing = XFAIL,
exit 0; all passing = XPASS, exit 1 (remove the red).  After removal the
file carries no *_RED_* name and a failure is a plain FAIL, exit 1.
Controls 2-5 failing = FAIL, exit 1, in either state.  Instrument problems
(monitor silent, no GDT= line) = INSTRUMENT FAIL, exit 3.

usage: test_uefi2_gdt.py <bmforth.img> <combined.img> <serial-port> <monitor-port>
"""
import hashlib
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import qemu_pid  # tests/qemu_pid.py: did our QEMU start, on its own ports?

# The red was removed after its XPASS gate fired on exactly its name
# (fix-uefi2-xpass-gate-2026-09-28.log); a failure is now a plain FAIL.
UEFI_REDS = []
TEST_ID = 'uefi2 kernel runs on own GDT'

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLOPPY, COMBINED, PORT, MON = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
KERNEL_LO, KERNEL_HI = 0x7E00, 0x7E00 + 0x1C000      # KERNEL_ORG, + KERNEL_PADDED_SIZE


def die(code, msg):
    print(msg)
    sys.exit(code)


for f in (FLOPPY, COMBINED):
    print(f'input sha256 {hashlib.sha256(open(f, "rb").read()).hexdigest()}  {f}')


def pci_bar_blocks():
    import importlib.util
    spec = importlib.util.spec_from_file_location('wc', os.path.join(ROOT, 'tools', 'write-catalog.py'))
    wc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wc)
    vocabs = wc.scan_vocabs(os.path.join(ROOT, 'forth', 'dict'))
    nb = 1 + (len(vocabs) + wc.CATALOG_DATA_LINES - 1) // wc.CATALOG_DATA_LINES
    for v in vocabs:
        nb = wc.place_vocab(nb, v['blocks_needed'])
        if v['name'] == 'PCI-BAR':
            return nb, nb + v['blocks_needed'] - 1
        nb += v['blocks_needed']
    return None, None


work = tempfile.mkdtemp(prefix='uefi2-')
ide = os.path.join(work, 'ide.img')
shutil.copy(COMBINED, ide)
q = subprocess.Popen(
    ['qemu-system-i386', '-drive', f'file={FLOPPY},format=raw,if=floppy,readonly=on',
     '-drive', f'file={ide},format=raw,if=ide,index=1',
     '-serial', f'tcp:127.0.0.1:{PORT},server=on,wait=on',
     '-monitor', f'tcp:127.0.0.1:{MON},server=on,wait=off',
     '-display', 'none', '-no-reboot'],
    stdout=subprocess.DEVNULL, stderr=open(os.path.join(work, 'qemu.err'), 'w'))
qemu_pid.wait_started(q, None, [PORT, MON], 'uefi2-gdt', os.path.join(work, 'qemu.err'))
try:
    for _ in range(40):
        try:
            s = socket.create_connection(('127.0.0.1', PORT))
            break
        except OSError:
            time.sleep(0.25)
    else:
        die(3, 'INSTRUMENT FAIL: serial never accepted a connection')
    s.settimeout(1)

    def send(cmd, wait=1.0):
        s.sendall((cmd + '\r').encode())
        time.sleep(wait)
        b = b''
        while True:
            try:
                d = s.recv(65536)
                if not d:
                    break
                b += d
            except socket.timeout:
                break
        return b.decode('latin-1')

    time.sleep(3)
    send('')
    if '42' not in send('7 6 * .'):
        die(3, 'INSTRUMENT FAIL: no ok prompt (7 6 * . did not print 42)')

    m = socket.create_connection(('127.0.0.1', MON))
    m.settimeout(1)
    time.sleep(0.5)
    try:
        m.recv(65536)
    except socket.timeout:
        pass
    m.sendall(b'info registers\n')
    time.sleep(1)
    regs = b''
    while True:
        try:
            d = m.recv(65536)
            if not d:
                break
            regs += d
        except socket.timeout:
            break
    regs = regs.decode('latin-1')
    lines = {k: re.search(rf'^{k}\s*=\s*(\S+)(?:\s+(\S+))?', regs, re.M) for k in ('CS', 'DS', 'ES', 'SS', 'GDT')}
    if not lines['GDT'] or not lines['CS']:
        die(3, f'INSTRUMENT FAIL: info registers has no GDT=/CS= line: {regs[:200]!r}')
    for k in ('CS', 'DS', 'ES', 'SS', 'GDT'):
        print(f'  {k:3}= ' + ' '.join(g for g in lines[k].groups() if g))
    gdt_base = int(lines['GDT'].group(1), 16)
    gdt_limit = int(lines['GDT'].group(2), 16)
    sel = {k: int(lines[k].group(1), 16) for k in ('CS', 'DS', 'ES', 'SS')}

    bs, be = pci_bar_blocks()
    if bs is None:
        die(3, 'INSTRUMENT FAIL: host resolver cannot place PCI-BAR')
    send(f'DECIMAL {bs} {be} THRU', 10)
    alive = '42' in send('7 6 * .')
    print(f'  PCI-BAR blocks {bs}-{be} THRU; alive after: {alive}')
finally:
    q.kill()
    q.wait()
    shutil.rmtree(work, ignore_errors=True)

red = KERNEL_LO <= gdt_base < KERNEL_HI
controls = [('GDT limit >= 0x17', gdt_limit >= 0x17),
            ('CS = 0x0008', sel['CS'] == 0x08),
            ('DS = ES = SS = 0x0010', sel['DS'] == sel['ES'] == sel['SS'] == 0x10),
            ('alive after the PCI-BAR THRU', alive)]
print(f'  check 1: GDT base {gdt_base:#x} in the kernel image '
      f'[{KERNEL_LO:#x}, {KERNEL_HI:#x}): {red}')
for name, ok in controls:
    print(f'  control: {name}: {ok}')
bad = [n for n, ok in controls if not ok]
if bad:
    die(1, f'FAIL: controls failed: {bad}')
if UEFI_REDS:
    if red:
        die(1, f'XPASS: {UEFI_REDS[0]} passed -- stop; record it, then remove the red')
    print(f'XFAIL (expected): {UEFI_REDS[0]} -- GDT base {gdt_base:#x} is outside the kernel image')
    sys.exit(0)
if not red:
    die(1, f'FAIL: {TEST_ID}: GDT base {gdt_base:#x} is outside the kernel image')
print(f'PASS: {TEST_ID}')
sys.exit(0)
