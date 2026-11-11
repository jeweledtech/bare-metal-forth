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

Two more memdisk `vbe` boots run under QEMU's gdb stub (Brenden's review,
2026-11-06: on VBE 3.0+ the stub must judge the linear colour masks,
ModeInfoBlock 0x36-0x3B, not the banked ones at 0x1F-0x24, since the mode
it sets is the linear one).  A hardware breakpoint on the instruction
after the stub's 4F01h `int 0x10` (found in kernel.bin by its bytes, not
hard-coded; each stop is checked against guest memory, since pxelinux and
memdisk run near 0x7E00 too) stops the guest at every mode-info return,
and the test overwrites one mask set with a BGR layout (R 8@0, G 8@8,
B 8@16) before the stub reads it:
  L  linear masks BGR, banked left as the BIOS wrote them -> no mode
  B  banked masks BGR, linear left as the BIOS wrote them -> a mode
L0 records QEMU's own linear masks (the authority that the V leg's
mode is still found once the stub reads them).

The console on the framebuffer (private TASK_UNICORN_WRITER Phase 2 slice
(b), owner 2026-11-10: the kernel's UEFI-4 console with the Terminus font,
in a right-hand panel beside the page; its buffers out of 0x80000-0xA0000):
  F5 / N5  text boots: SCREEN = 0xB8000, FB-CON 0 0 0 0
  V16 vbe: SCREEN = forth.asm FB_SHADOW, and FB_SHADOW..FB_DRAWN + 4000
      lies outside 0x80000-0xA0000
  V17 vbe: FB-CON = FB-W - 640, FB-H - 400, 640, 400 (bottom right)
  V18 vbe: the panel on QEMU's screen is SCREEN's 2,000 cells drawn in
      the FNT1 font read from build/combined.img, VGA palette, the cursor
      (glyph rows 14-15 in the foreground) at CURSOR-CELL only
  V19 vbe: "5 ok" (the answer to 2 3 + .) is among those cells
  V20 vbe: every pixel outside the panel is black (the console draws
      only in its panel)

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
KERNEL = os.path.join(ROOT, 'build', 'kernel.bin')
PREFS = [(1366, 768), (1360, 768), (1280, 800), (1280, 768),
         (1024, 768), (800, 600), (640, 480)]
KERNEL_ORG = 0x7E00
MI = 0x28400                    # VBE_SCRATCH_SEG * 16 + VBE_MI: the ModeInfoBlock
# mov ax, 0x4F01 / mov di, VBE_MI / int 0x10: the stub's mode-info call
MI_CALL = bytes.fromhex('b8014f' 'bf0002' 'cd10')
MASKS_888 = bytes.fromhex('081008080800')   # R 8@16, G 8@8, B 8@0
MASKS_BGR = bytes.fromhex('080008081008')   # R 8@0,  G 8@8, B 8@16
TOTAL = 38
FONT_BLK = 536                  # forth.asm FONT_BLK: FNT1, the console font
COMBINED_HEADER = 512 + 0x1C000
PALETTE = [0x000000, 0x0000AA, 0x00AA00, 0x00AAAA, 0xAA0000, 0xAA00AA, 0xAA5500, 0xAAAAAA,
           0x555555, 0x5555FF, 0x55FF55, 0x55FFFF, 0xFF5555, 0xFF55FF, 0xFFFF55, 0xFFFFFF]
_asm = open(os.path.join(ROOT, 'src', 'kernel', 'forth.asm')).read()
SHADOW = int(re.search(r'^FB_SHADOW\s+equ\s+(0x[0-9A-Fa-f]+)', _asm, re.M).group(1), 16)
DRAWN = int(re.search(r'^FB_DRAWN\s+equ\s+(0x[0-9A-Fa-f]+)', _asm, re.M).group(1), 16)
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


def read_ppm(path):
    with open(path, 'rb') as f:
        data = f.read()
    parts = data.split(b'\n', 3)
    w, h = (int(t) for t in parts[1].split())
    return w, h, parts[3]


def pmem(addr, size, name):
    path = os.path.join(ROOT, 'build', name)
    if os.path.exists(path):
        os.remove(path)
    monitor(f'pmemsave {addr} {size} "{path}"', wait=1.0)
    t0 = time.time()
    while (not os.path.exists(path) or os.path.getsize(path) < size) and time.time() - t0 < 5:
        time.sleep(0.1)
    return open(path, 'rb').read() if os.path.exists(path) else b''


def panel_cells(ppm, mem, x0, y0, cursor):
    """The cells whose pixels at (x0, y0) + cell differ from mem drawn in
    the FNT1 font (host-side, from build/combined.img) and the palette."""
    w, h, rgb = ppm
    with open(COMBINED, 'rb') as f:
        f.seek(COMBINED_HEADER + FONT_BLK * 1024 + 16)
        font = f.read(95 * 16)
    bad = []
    for i in range(2000):
        ch, at = mem[2 * i], mem[2 * i + 1]
        fg, bg = PALETTE[at & 15], PALETTE[(at >> 4) & 7]
        g = font[(ch - 0x20) * 16:(ch - 0x1F) * 16] if 0x20 <= ch <= 0x7E else bytes(16)
        cx, cy = x0 + (i % 80) * 8, y0 + (i // 80) * 16
        ok = True
        for r in range(16):
            bits = 0xFF if (i == cursor and r >= 14) else g[r]
            for b in range(8):
                x, y = cx + b, cy + r
                if not (0 <= x < w and 0 <= y < h):
                    ok = False
                    break
                o = (y * w + x) * 3
                got = (rgb[o] << 16) | (rgb[o + 1] << 8) | rgb[o + 2]
                if got != (fg if bits & (0x80 >> b) else bg):
                    ok = False
                    break
            if not ok:
                break
        if not ok:
            bad.append(i)
    return bad


def console_q(s):
    """SCREEN, then FB-CON's x y w h (None where the reply has no number)."""
    r = ser.send_until_prompt(s, 'SCREEN U. FB-CON . . . .', budget=20)[0]
    v = nums(r)
    if len(v) != 5:
        return None, None
    return v[0], (v[4], v[3], v[2], v[1])


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
        con = console_q(s)
        CON[leg] = con
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
        if leg == 'vbe':
            # the panel: once more at a quiet prompt, then memory and screen
            ser.send_until_prompt(s, '2 3 + .', budget=10)
            cur = nums(ser.send_until_prompt(s, 'CURSOR-CELL U.', budget=10)[0])
            ser.send_until_prompt(s, '2 3 + .', budget=10)
            scr = con[0] if con[0] is not None else 0xB8000
            mem = pmem(scr, 4000, 'vbe-panel.bin')
            c = pmem(cur[0], 4, 'vbe-cursor.bin') if cur else b''
            ppm_path = os.path.join(ROOT, 'build', 'vbe-panel.ppm')
            if os.path.exists(ppm_path):
                os.remove(ppm_path)
            monitor('screendump ' + ppm_path, wait=2.0)
            PANEL['mem'], PANEL['ppm'] = mem, read_ppm(ppm_path)
            PANEL['cursor'] = int.from_bytes(c, 'little', signed=True) if len(c) == 4 else None
        s.close()
        return q, five, table, pci, size, extra
    finally:
        qemu_pid.kill_pidfile(pidf)


class Gdb:
    """Just enough of the gdb remote protocol (as in test_vbe_nostub.py)."""

    def __init__(self, path, budget=20):
        t0 = time.time()
        while True:
            try:
                self.s = socket.socket(socket.AF_UNIX)
                self.s.connect(path)
                break
            except OSError:
                if time.time() - t0 > budget:
                    raise
                time.sleep(0.2)
        self.s.settimeout(1)

    def recv(self, budget):
        buf, t0 = b'', time.time()
        while time.time() - t0 < budget:
            try:
                d = self.s.recv(4096)
            except socket.timeout:
                continue
            if not d:
                break
            buf += d
            m = re.search(rb'\$([^#]*)#[0-9a-fA-F]{2}', buf)
            if m:
                self.s.sendall(b'+')
                return m.group(1).decode()
        raise TimeoutError(f'gdb: no reply in {budget} s ({buf[-80:]!r})')

    def cmd(self, body, budget=10):
        ck = sum(body.encode()) & 0xFF
        self.s.sendall(f'${body}#{ck:02x}'.encode())
        return self.recv(budget)

    def read(self, addr, n):
        return bytes.fromhex(self.cmd(f'm{addr:x},{n:x}'))

    def write(self, addr, data):
        return self.cmd(f'M{addr:x},{len(data):x}:{data.hex()}')

    def eip(self):
        return int.from_bytes(bytes.fromhex(self.cmd('g')[64:72]), 'little')

    def close(self):
        try:
            self.s.sendall(b'$D#44')
        except OSError:
            pass
        self.s.close()


def stub_addrs():
    """(after the 4F01h int 0x10, kernel_start) from kernel.bin's bytes."""
    k = open(KERNEL, 'rb').read()
    hits = [m.start() for m in re.finditer(re.escape(MI_CALL), k)]
    assert len(hits) == 1, f'4F01h call found {len(hits)} times in kernel.bin'
    assert k[0] == 0xE9, 'kernel_entry is not a near jmp'
    ks = KERNEL_ORG + 5 + int.from_bytes(k[1:5], 'little', signed=True)
    return KERNEL_ORG + hits[0] + len(MI_CALL), ks, k


def patch_masks(gdbpath, field, budget=120):
    """Stop at every 4F01h return of the stub, record the BIOS's linear
    masks of each usable 32-bpp direct-colour mode, overwrite the 6 mask
    bytes at MI + field with MASKS_BGR; detach at kernel_start."""
    ret, ks, k = stub_addrs()
    want_ret = k[ret - len(MI_CALL) - KERNEL_ORG:ret - KERNEL_ORG]
    want_ks = k[ks - KERNEL_ORG:ks - KERNEL_ORG + 8]
    g = Gdb(gdbpath)
    hits, spurious, lin = 0, 0, []
    try:
        for a in (ret, ks):
            assert g.cmd(f'Z1,{a:x},1') == 'OK'
        t0 = time.time()
        while time.time() - t0 < budget:
            g.s.sendall(b'$c#63')
            g.recv(budget)
            pc = g.eip()
            if pc == ks and g.read(ks, 8) == want_ks:
                break
            if pc == ret and g.read(ret - len(MI_CALL), len(MI_CALL)) == want_ret:
                hits += 1
                mi = g.read(MI, 0x3C)
                if (int.from_bytes(mi[0:2], 'little') & 0x99) == 0x99 \
                        and mi[0x19] == 32 and mi[0x1B] == 6:
                    lin.append(mi[0x36:0x3C].hex())
                g.write(MI + field, MASKS_BGR)
            else:
                spurious += 1
            # step off the breakpoint before continuing
            g.cmd(f'z1,{pc:x},1') if pc in (ret, ks) else None
            g.cmd('s', budget)
            if pc in (ret, ks):
                g.cmd(f'Z1,{pc:x},1')
        else:
            raise TimeoutError('kernel_start never reached')
        for a in (ret, ks):
            g.cmd(f'z1,{a:x},1')
        return {'ret': hex(ret), 'kernel_start': hex(ks), 'hits': hits,
                'spurious': spurious, 'linear': sorted(set(lin)), 'usable32': len(lin)}
    finally:
        g.close()
        time.sleep(0.3)
        monitor('cont', wait=0.5)    # QEMU pauses the VM when gdb detaches


def run_patched(leg, args, field):
    sock = os.path.join(SOCKDIR, f'{leg}.gdb')
    pidf = boot(leg, args + ['-S', '-chardev', f'socket,id=gdb0,path={sock},server=on,wait=off',
                             '-gdb', 'chardev:gdb0'])
    try:
        info = patch_masks(sock, field)
        s = ser.connect_and_sync(SPORT, budget=90)
        q = nums(ser.send_until_prompt(s, Q, budget=20)[0])
        five = ser.send_until_prompt(s, '2 3 + .', budget=10)[0]
        size = screen_size(os.path.join(ROOT, 'build', f'vbe-{leg}.ppm'))
        s.close()
        return q, five, size, info
    finally:
        qemu_pid.kill_pidfile(pidf)


CON, PANEL = {}, {}
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
check('F5 floppy: SCREEN 0xB8000, FB-CON 0 0 0 0 (no framebuffer console)',
      CON.get('floppy') == (0xB8000, (0, 0, 0, 0)), CON.get('floppy'))

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
check('N5 memdisk, no vbe: SCREEN 0xB8000, FB-CON 0 0 0 0 (no framebuffer console)',
      CON.get('novbe') == (0xB8000, (0, 0, 0, 0)), CON.get('novbe'))

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
v_wh = (w, h)
scr, rect = CON.get('vbe') or (None, None)
print(f'  console: SCREEN {scr and hex(scr)} FB-CON {rect}; FB_SHADOW {hex(SHADOW)} FB_DRAWN {hex(DRAWN)}')
check('V16 vbe: SCREEN = FB_SHADOW, and the console buffers lie outside 0x80000-0xA0000',
      scr == SHADOW and (DRAWN + 4000 <= 0x80000 or SHADOW >= 0xA0000),
      f'SCREEN {scr} FB_SHADOW {hex(SHADOW)} FB_DRAWN {hex(DRAWN)}')
want_rect = (w - 640, h - 400, 640, 400) if w and h else None
check('V17 vbe: FB-CON = FB-W - 640, FB-H - 400, 640, 400 (the bottom-right panel)',
      rect == want_rect, f'{rect} want {want_rect}')
mem, ppm, cur = PANEL.get('mem', b''), PANEL.get('ppm'), PANEL.get('cursor')
x0, y0 = (w - 640, h - 400) if w and h else (0, 0)
bad = panel_cells(ppm, mem, x0, y0, cur) if ppm and len(mem) == 4000 else list(range(2000))
check('V18 vbe: the panel shows SCREEN\'s 2000 cells in the FNT1 font, the cursor at CURSOR-CELL',
      not bad and cur is not None, f'{len(bad)} cells differ (first {bad[:8]}); CURSOR-CELL {cur}')
txt = ''.join(chr(mem[2 * i]) if len(mem) == 4000 and 0x20 <= mem[2 * i] < 0x7F else ' '
              for i in range(2000))
at = txt.rfind('5 ok')
check('V19 vbe: "5 ok" is in the panel, drawn',
      at >= 0 and not any(at <= b < at + 4 for b in bad), f'at {at}, differing {bad[:8]}')
outside = 0
if ppm:
    pw, ph, rgb = ppm
    for y in range(ph):
        for x in range(pw):
            if x >= x0 and y >= y0:
                continue
            o = (y * pw + x) * 3
            if rgb[o:o + 3] != b'\x00\x00\x00':
                outside += 1
check('V20 vbe: every pixel outside the panel is black', ppm is not None and outside == 0,
      f'{outside} non-black pixels outside the panel')

# L and B: one mask set rewritten at every 4F01h return (gdb stub)
SOCKDIR = tempfile.mkdtemp(prefix='fvb-')
try:
    d = tftp_root(' vbe')
    q, five, size, info = run_patched('linbad', net(d), 0x36)
    shutil.rmtree(d)
    print(f'  linear masks BGR: {q} screen {size} gdb {info}')
    st, mode, fb, pitch, w, h, bpp, ver, bm = (q + [None] * 9)[:9]
    check('L0 QEMU VBE 3 BIOS: every usable 32-bpp mode has linear masks 8@16 8@8 8@0',
          info['usable32'] >= 1 and info['linear'] == [MASKS_888.hex()], info)
    check('L1 linear masks rewritten at every 4F01h return (VBE-VERSION 3)',
          info['hits'] >= 1 and ver == 3, f"hits {info['hits']} version {ver}")
    check('L2 linear masks BGR: VBE-STATUS 3 (no mode), VBE-MODE 0, FB-ADDR 0',
          st == 3 and mode == 0 and fb == 0, q)
    check('L3 linear masks BGR: QEMU shows text mode (720x400)', size == (720, 400), size)
    check('L4 linear masks BGR: console answers 5', '5 ok' in five, five)

    d = tftp_root(' vbe')
    q, five, size, info = run_patched('bankbad', net(d), 0x1F)
    shutil.rmtree(d)
    print(f'  banked masks BGR: {q} screen {size} gdb {info}')
    st, mode, fb, pitch, w, h, bpp, ver, bm = (q + [None] * 9)[:9]
    check('B1 banked masks BGR, linear intact: VBE-STATUS 1, FB-BPP 32, the V leg\'s FB-W x FB-H',
          st == 1 and bpp == 32 and (w, h) == v_wh and info['hits'] >= 1, f'{q} V {v_wh}')
    check('B2 banked masks BGR: QEMU shows FB-W x FB-H', size == (w, h) and st == 1,
          f'{size} vs {(w, h)}')
    check('B3 banked masks BGR: console answers 5', '5 ok' in five, five)
finally:
    shutil.rmtree(SOCKDIR, ignore_errors=True)

print(f'\nPassed: {PASS}/{TOTAL}')
sys.exit(0 if PASS == TOTAL and FAIL == 0 else 1)
