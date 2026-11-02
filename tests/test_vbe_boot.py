#!/usr/bin/env python3
"""BIOS VBE opt-in at boot (private TASK_UNICORN_WRITER Phase 1; the kernel
and boot-sector halves are public).

boot.asm far-calls forth.asm's vbe_stub (KERNEL_ORG + 8) in real mode.
The stub sets a 32-bpp linear-framebuffer VBE mode only when memdisk's
command line carries the word `vbe` (the PXE label "ForthOS - URWriter
(graphics)"), and always writes the result cells read by VBE-STATUS,
VBE-MODE, FB-ADDR, FB-PITCH, FB-W, FB-H, FB-BPP, VBE-VERSION, and lists
VBE-MODES (the usable modes), VBE-OFFERED and VBE-DEPTHS.

Three boots, each its own QEMU (serial on argv[1], monitor on argv[2]):
  F  floppy, no memdisk          -> nothing requested, all cells 0, text
  N  pxelinux -> memdisk harddisk -> same (memdisk without `vbe`)
  V  pxelinux -> memdisk harddisk vbe -> a mode is set
The V checks take their authority from QEMU, not from the code under
test: BAR0 of the 1234:1111 VGA from the monitor's `info pci`, and the
display size from `screendump`.

memdisk / pxelinux.0 / ldlinux.c32 default to the Ubuntu package paths
(syslinux-common, pxelinux); FORTHOS_MEMDISK, FORTHOS_PXELINUX and
FORTHOS_LDLINUX override them.  Absent, the N and V legs cannot run and
the suite fails, naming the package.

Not covered here: the vbr.asm and multiboot2 entries, which never call
the stub; kernel_start zeroes the cells for them (vbe_fresh = 0).
"""
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import qemu_pid  # noqa: E402
import serial as ser  # noqa: E402

SPORT, MPORT = int(sys.argv[1]), int(sys.argv[2])
IMG = os.path.join(ROOT, 'build', 'bmforth.img')
COMBINED = os.path.join(ROOT, 'build', 'combined.img')
MEMDISK = os.environ.get('FORTHOS_MEMDISK', '/usr/lib/syslinux/memdisk')
PXELINUX = os.environ.get('FORTHOS_PXELINUX', '/usr/lib/PXELINUX/pxelinux.0')
LDLINUX = os.environ.get('FORTHOS_LDLINUX',
                         '/usr/lib/syslinux/modules/bios/ldlinux.c32')
PREFS = [(1366, 768), (1360, 768), (1280, 800), (1280, 768),
         (1024, 768), (800, 600), (640, 480)]
TOTAL = 23
PASS = FAIL = 0


def check(name, ok, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {name}')
    else:
        FAIL += 1
        print(f'  FAIL: {name} -- {detail}')


def tftp_root(append):
    d = tempfile.mkdtemp(prefix='forthos-vbe-')
    for f in (PXELINUX, LDLINUX, MEMDISK):
        shutil.copy(f, d)
    shutil.copy(COMBINED, os.path.join(d, 'forth.img'))
    os.mkdir(os.path.join(d, 'pxelinux.cfg'))
    with open(os.path.join(d, 'pxelinux.cfg', 'default'), 'w') as f:
        f.write('DEFAULT f\nPROMPT 0\nTIMEOUT 1\nLABEL f\n'
                '  KERNEL memdisk\n'
                f'  APPEND initrd=forth.img harddisk{append}\n')
    return d


def boot(leg, args):
    pidf = qemu_pid.pidfile('vbe-' + leg)
    qemu_pid.kill_pidfile(pidf)
    err = os.path.join(ROOT, 'build', f'vbe-{leg}-qemu.err')
    cmd = ['qemu-system-i386', '-m', '128'] + args + [
        '-serial', f'tcp:127.0.0.1:{SPORT},server=on,wait=off',
        '-monitor', f'tcp:127.0.0.1:{MPORT},server=on,wait=off',
        '-display', 'none', '-pidfile', pidf]
    proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.DEVNULL,
                            stderr=open(err, 'w'))
    qemu_pid.wait_started(proc, pidf, [SPORT, MPORT], 'vbe-' + leg, err)
    return pidf


def monitor(cmd, wait=1.5):
    m = socket.create_connection(('127.0.0.1', MPORT), timeout=5)
    time.sleep(0.3)
    try:
        m.recv(65536)
    except socket.timeout:
        pass
    m.sendall((cmd + '\n').encode())
    time.sleep(wait)
    out = b''
    m.settimeout(1.0)
    try:
        while True:
            d = m.recv(65536)
            if not d:
                break
            out += d
    except socket.timeout:
        pass
    m.close()
    return re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', out.decode(errors='replace'))


def screen_size(path):
    if os.path.exists(path):
        os.remove(path)
    monitor('screendump ' + path, wait=2.0)
    with open(path, 'rb') as f:
        head = f.read(32).split(b'\n')
    w, h = head[1].split()
    return int(w), int(h)


def nums(reply):
    line = [l for l in reply.splitlines() if l.strip().endswith('ok')]
    return [int(t) for t in re.findall(r'-?\d+', line[-1])] if line else []


Q = ('VBE-STATUS . VBE-MODE . FB-ADDR U. FB-PITCH . FB-W . FB-H . '
     'FB-BPP . VBE-VERSION . BOOT-MODE .')


def run_leg(leg, args):
    pidf = boot(leg, args)
    try:
        s = ser.connect_and_sync(SPORT, budget=90)
        q = nums(ser.send_until_prompt(s, Q, budget=20)[0])
        five = ser.send_until_prompt(s, '2 3 + .', budget=10)[0]
        table, extra = [], []
        if q and q[0] == 1:
            # No ?DO in this kernel, and DO compiles only inside a
            # definition: a guarded DO in a colon word
            ser.send_until_prompt(s, ': VBE-W@ DUP C@ SWAP 1+ C@ 256 * + ;')
            ser.send_until_prompt(
                s, ': VBE-DUMP VBE-MODES DUP IF 0 DO DUP I 8 * + DUP VBE-W@ . '
                   'DUP 2 + VBE-W@ . DUP 4 + VBE-W@ . DUP 6 + C@ . 7 + C@ . '
                   'LOOP ELSE DROP THEN DROP ;')
            extra = nums(ser.send_until_prompt(
                s, 'VBE-OFFERED . VBE-DEPTHS DUP C@ . DUP 1+ C@ . DUP 2 + C@ . '
                   'DUP 3 + C@ . 4 + C@ .', budget=20)[0])
            r = ser.send_until_prompt(s, 'VBE-DUMP', budget=20)[0]
            # the dump wraps over several console lines: every number
            # after the echoed command, up to the final prompt
            body = r.split('VBE-DUMP', 1)[-1].rsplit('ok', 1)[0]
            v = [int(t) for t in re.findall(r'-?\d+', body)]
            table = [tuple(v[i:i + 5]) for i in range(0, len(v) - len(v) % 5, 5)]
        pci = monitor('info pci') if q and q[0] == 1 else ''
        size = screen_size(os.path.join(ROOT, 'build', f'vbe-{leg}.ppm'))
        s.close()
        return q, five, table, pci, size, extra
    finally:
        qemu_pid.kill_pidfile(pidf)


print('=== VBE opt-in at boot (vbe_stub, FB-* words) ===')
for p, pkg in ((MEMDISK, 'syslinux-common'), (PXELINUX, 'pxelinux'),
               (LDLINUX, 'syslinux-common')):
    if not os.path.exists(p):
        print(f'  FAIL: {p} absent (apt install {pkg}, or set FORTHOS_*)')
        print(f'\nPassed: 0/{TOTAL}')
        sys.exit(1)

# F: floppy, no memdisk
q, five, _, _, size, _ = run_leg('floppy', ['-drive', f'file={IMG},format=raw,if=floppy'])
print(f'  floppy: {q} screen {size}')
check('F1 floppy: VBE-STATUS 0 and every cell 0', q[:8] == [0] * 8, q)
check('F2 floppy: BOOT-MODE 0', q[8:9] == [0], q)
check('F3 floppy: console answers 5', '5 ok' in five, five)
check('F4 floppy: QEMU shows text mode (720x400)', size == (720, 400), size)

# N: memdisk without vbe
net = lambda d: ['-netdev', f'user,id=n0,tftp={d},bootfile=pxelinux.0',
                 '-device', 'e1000,netdev=n0', '-boot', 'n']
d = tftp_root('')
q, five, _, _, size, _ = run_leg('novbe', net(d))
shutil.rmtree(d)
print(f'  memdisk: {q} screen {size}')
check('N1 memdisk, no vbe: VBE-STATUS 0 and every cell 0', q[:8] == [0] * 8, q)
check('N2 memdisk, no vbe: BOOT-MODE 1', q[8:9] == [1], q)
check('N3 memdisk, no vbe: console answers 5', '5 ok' in five, five)
check('N4 memdisk, no vbe: QEMU shows text mode (720x400)', size == (720, 400), size)

# V: memdisk with vbe
d = tftp_root(' vbe')
q, five, table, pci, size, extra = run_leg('vbe', net(d))
shutil.rmtree(d)
print(f'  memdisk vbe: {q} screen {size}')
print(f'  VBE-MODES ({len(table)}): {table}')
print(f'  VBE-OFFERED, VBE-DEPTHS 8/15/16/24/32: {extra}')
st, mode, fb, pitch, w, h, bpp, ver, bm = (q + [None] * 9)[:9]
check('V1 vbe: VBE-STATUS 1 (mode set)', st == 1, q)
check('V2 vbe: BOOT-MODE 1', bm == 1, q)
check('V3 vbe: FB-BPP 32', bpp == 32, q)
check('V4 vbe: VBE-VERSION >= 2', ver is not None and ver >= 2, q)
check('V5 vbe: VBE-MODE names a mode (not 0, no LFB bit)',
      mode is not None and 0 < mode < 0x4000, q)
check('V6 vbe: (FB-W, FB-H) is one of the preferences', (w, h) in PREFS, (w, h))
check('V7 vbe: FB-PITCH >= FB-W * 4', pitch is not None and w is not None
      and pitch >= w * 4, q)
bar = None
blk = re.search(r'PCI device 1234:1111.*?BAR0: 32 bit (?:prefetchable )?memory at '
                r'(0x[0-9a-f]+)', pci, re.S)
if blk:
    bar = int(blk.group(1), 16)
check('V8 vbe: FB-ADDR == BAR0 of VGA 1234:1111 (QEMU info pci)',
      bar is not None and fb == bar, f'FB-ADDR {fb} BAR0 {bar}')
check('V9 vbe: QEMU shows FB-W x FB-H', size == (w, h), f'{size} vs {(w, h)}')
check('V10 vbe: VBE-MODES holds 1..32 usable modes, every one 32 bpp model 6',
      1 <= len(table) <= 32 and all(e[3] == 32 and e[4] == 6 for e in table),
      table)
check('V11 vbe: the set mode is in VBE-MODES with the same w, h, 32 bpp',
      any(e[0] == mode and e[1] == w and e[2] == h and e[3] == 32 for e in table),
      f'mode {mode}')
cands = [PREFS.index((e[1], e[2])) for e in table if (e[1], e[2]) in PREFS]
check('V12 vbe: no usable mode ranks above the one set',
      (w, h) in PREFS and all(PREFS.index((w, h)) <= c for c in cands),
      f'chosen {(w, h)} candidates {sorted(set(cands))}')
check('V13 vbe: console still answers 5 (serial after the mode set)',
      '5 ok' in five, five)
off, depths = (extra[:1] or [None])[0], extra[1:6]
check('V14 vbe: VBE-OFFERED >= the usable modes, and >= all LFB depths counted',
      off is not None and len(depths) == 5 and off >= len(table)
      and off >= sum(depths), extra)
check('V15 vbe: VBE-DEPTHS 32-bpp count >= the usable modes recorded',
      len(depths) == 5 and depths[4] >= len(table), extra)

print(f'\nPassed: {PASS}/{TOTAL}')
sys.exit(0 if PASS == TOTAL and FAIL == 0 else 1)
