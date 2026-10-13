#!/usr/bin/env python3
"""UEFI-3/4 gate: the FORTHBOOT stick boots whichever way the machine
offers.  The same stick replica is booted under OVMF (UEFI, no CSM:
multiboot2 kernel, blocks served from the GRUB module, framebuffer console)
and under SeaBIOS (legacy: GRUB BIOS, memdisk) (docs/TASK_UEFI_3_4.md).

Was UEFI-1's registered red (the stick boots to ok under OVMF,
docs/evidence/uefi-1-prereg-2026-09-28.md), XFAIL until UEFI-3; retired
in the register 2026-10-12.

  H1  grub-file --is-x86-multiboot2 accepts combined.img.
  H2  the header, read from the image: 8-aligned, inside the first 32 KiB,
      checksum; the address tag loads the kernel only (load_addr 0x7E00,
      load_end = 0x7E00 + KERNEL_PADDED_SIZE, header_addr consistent with
      the file offset); the entry tag points into the kernel.
  H3  the console font: forth.asm FONT_BLK = write-catalog FONT_RESERVED,
      and the image carries `FNT1` (first 0x20, 95 glyphs) there.
  H4  the stick script writes the font's license (FONT-LICENSE.txt, SIL OFL)
      next to forth.img; the replica carries it too.
  OVMF:
  B1  control: GRUB's UEFI menu title reaches serial (else INSTRUMENT FAIL).
  B2  the kernel's report: `MB2: module <start>-<end>`, a line per window
      (three), no `REFUSED` (a module inside a window is moved above them
      first: `MB2: module moved to <start>-<end>`).
  B3  banner + ok.  B4  `MB2: framebuffer console on`.
  I1  BLK_IMAGE_BASE (0x28098) = the module's final start, as reported.
  U1  BOOT-MODE = 3.  U2  HELLO-APP loads from the module.
  U3  AUTO-DETECT-REPORT says `Boot: UEFI (multiboot2)`.  U4  DEPTH 0.
  F1  after PAGE and `.( UEF) .( I4)` (so only the output, not the echo,
      spells it), a QEMU screen dump shows UEFI4 drawn in the image's font,
      pixel for pixel, at a cell-aligned position.
  U9 / L9: PCI-TYPES on the xHCI: under OVMF its 64-bit BAR printed in full
      (0xC000000000) and flagged `above 4 GiB: unreachable`; under SeaBIOS
      an 8-digit base below 4 GiB, no flag.
  U5-U8 / L5-L8 (both legs): the display contract's FB-BASE = 0x80000 (OVMF)
      / 0xB8000 (SeaBIOS);
      HELLO-RUN's form and notepad's editor (entered with the New button,
      so RAW-SCAN's wait runs) leave their text in that memory (pmemsave),
      the form with inverse-video cells (6b, so S1 compares colours too);
      back at the prompt, DEPTH 0.  On OVMF, S1/S2: all 2,000 cells of the
      screen dump equal that memory drawn in the font and the VGA palette.
  SeaBIOS, the same image:
  L0  banner + ok.  L1  BOOT-MODE = 1.  L2  HELLO-APP loads from blocks.
  L3  AUTO-DETECT-REPORT says `Boot: BIOS (memdisk)`.  L4  DEPTH 0.

Exit 0 all pass, 1 a gate fails, 3 an instrument control fails (no score).

The image is built the way tools/make-uefi-usb.sh builds the stick, but
rootless and without any block device: sgdisk on a file, mkfs.fat on a
file, mtools to populate, dd to place.  grub.cfg is read from the
script's heredoc at run time (rule 28: test the shipped artifact), and
the grub-mkstandalone block is asserted to be the one replayed here.
Not exercised: the i386-pc half (grub-install needs a device; OVMF
never reads it).

usage: test_uefi_boot.py <serial port> <monitor port> [combined.img]
"""
import atexit
import hashlib
import struct
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
import qemu_pid          # noqa: E402
import serial as ser     # noqa: E402

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4474
MON = int(sys.argv[2]) if len(sys.argv) > 2 else 4476
SCRIPT = os.path.join(ROOT, 'tools', 'make-uefi-usb.sh')
ASM = os.path.join(ROOT, 'src', 'kernel', 'forth.asm')
IMG = sys.argv[3] if len(sys.argv) > 3 else os.path.join(ROOT, 'build', 'combined.img')
OUT = os.path.join(ROOT, 'build', 'uefi-stick-test.img')
OVMF_CODE = '/usr/share/OVMF/OVMF_CODE_4M.fd'
OVMF_VARS = '/usr/share/OVMF/OVMF_VARS_4M.fd'
MEMDISK = '/usr/lib/syslinux/memdisk'
BANNER = 'Bare-Metal Forth v0.1 - Ship Builders System'   # forth.asm:5755
WAIT = 60
DISK_MIB = 64

# The script's grub-mkstandalone block, replayed below.  If the script
# changes, this test must change with it -- it FAILs rather than drift.
MKSTANDALONE = '''grub-mkstandalone --format=x86_64-efi \\
    --output="$MOUNTPOINT/EFI/BOOT/BOOTX64.EFI" \\
    --locales="" \\
    --fonts="" \\
    --themes="" \\
    "boot/grub/grub.cfg=$MOUNTPOINT/boot/grub/grub.cfg"'''


def die(code, msg):
    print(msg)
    sys.exit(code)


def run(argv, **kw):
    r = subprocess.run(argv, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        die(3, f'INSTRUMENT FAIL: {" ".join(argv[:3])} ... rc {r.returncode}: '
               f'{(r.stderr or r.stdout).strip()[:300]}')
    return r


print(f'input sha256 {hashlib.sha256(open(IMG, "rb").read()).hexdigest()}  {IMG}')
src = open(SCRIPT).read()
print(f'script sha256 {hashlib.sha256(src.encode()).hexdigest()}  tools/make-uefi-usb.sh')

# ---- drift guards: FAIL, never XFAIL ----
m = re.search(r"<< 'GRUBCFG'\n(.*?)\nGRUBCFG\n", src, re.S)
if not m:
    die(1, 'FAIL: no GRUBCFG heredoc in make-uefi-usb.sh (the stick config moved)')
grub_cfg = m.group(1) + '\n'
if MKSTANDALONE not in src:
    die(1, 'FAIL: make-uefi-usb.sh grub-mkstandalone block is not the one this test replays')
efi_branch = grub_cfg.split('\nelse\n', 1)
if len(efi_branch) != 2:
    die(1, 'FAIL: grub.cfg has no UEFI (else) branch to anchor the control on')
t = re.search(r'menuentry "([^"]+)"', efi_branch[1])
if not t:
    die(1, 'FAIL: the UEFI branch has no menuentry title')
# GRUB draws the title truncated to the menu width, and the title holds a
# UTF-8 em dash: the control is the title's first 40 characters, matched
# on serial decoded as UTF-8 (first run: latin-1 + full title never matched).
CONTROL = t.group(1)[:40]
print(f'control: the UEFI branch title {CONTROL!r} must reach serial')

# ---- the stick's BIOS half, rootless ----
# make-uefi-usb.sh runs `grub-install --target=i386-pc` on the device; that
# needs root (and grub-bios-setup, which it calls, needs an openable root
# device).  Laid out here by hand, the way grub-bios-setup embeds GRUB on a
# GPT disk: boot.img's code in the protective MBR, pointing at core.img in
# the BIOS-boot partition, and core.img's first-sector blocklist pointing at
# the rest of it.  The bytes differ from grub-install's (core.img here
# embeds the modules grub.cfg's BIOS branch needs instead of loading them
# from /boot/grub/i386-pc); the boot path is the stick's: BIOS -> GRUB ->
# grub.cfg's `pc` branch -> linux16 memdisk -> forth.img.
BIOS_MODULES = ['biosdisk', 'part_gpt', 'fat', 'normal', 'configfile', 'test',
                'echo', 'linux16', 'reboot', 'search']
KERNEL_SECTOR = 0x5C       # boot.img: LBA of core.img's first sector (u64)
BLOCKLIST = 0x200 - 12     # core.img sector 0 (diskboot): u64 start, u16 len, u16 segment


def bios_half(disk, bios_lba, bios_sectors, work):
    core = os.path.join(work, 'core.img')
    run(['grub-mkimage', '-O', 'i386-pc', '-o', core, '-p', '(hd0,gpt2)/boot/grub'] + BIOS_MODULES)
    c = bytearray(open(core, 'rb').read())
    c += b'\0' * (-len(c) % 512)
    n = len(c) // 512
    if n > bios_sectors:
        die(3, f'INSTRUMENT FAIL: core.img is {n} sectors, the BIOS-boot partition {bios_sectors}')
    struct.pack_into('<QHH', c, BLOCKLIST, bios_lba + 1, n - 1, 0x820)
    boot = open('/usr/lib/grub/i386-pc/boot.img', 'rb').read()
    with open(disk, 'r+b') as f:
        mbr = bytearray(f.read(512))
        mbr[:0x1B8] = boot[:0x1B8]          # keep the protective MBR's table + signature
        struct.pack_into('<Q', mbr, KERNEL_SECTOR, bios_lba)
        f.seek(0)
        f.write(mbr)
        f.seek(bios_lba * 512)
        f.write(c)
    return n


def mon_cmd(cmd):
    """One HMP command over the monitor socket, read to the next prompt."""
    m = socket.create_connection(('127.0.0.1', MON), timeout=5)
    buf, t0 = b'', time.time()
    while not buf.rstrip().endswith(b'(qemu)') and time.time() - t0 < 5:
        buf += m.recv(4096)
    m.sendall((cmd + '\n').encode())
    buf, t0 = b'', time.time()
    while not buf.rstrip().endswith(b'(qemu)') and time.time() - t0 < 10:
        buf += m.recv(4096)
    m.close()
    return buf.decode('ascii', 'replace')


def font_from_image():
    """The font as the kernel finds it: block FONT_BLK of the image."""
    off = 512 + KPS + FONT_BLK * 1024
    return data[off:off + 16 + 95 * 16]


def screen_matches(ppm, text):
    """(ok, detail): TEXT drawn as 8x16 glyphs (light grey 0xAAAAAA on black)
    at some cell-aligned position of the screen dump, pixel for pixel."""
    if not os.path.exists(ppm):
        return False, '(no screen dump)'
    raw = open(ppm, 'rb').read()
    m = re.match(rb'P6\s+(\d+)\s+(\d+)\s+(\d+)\s', raw)
    if not m:
        return False, f'(not a P6 dump: {raw[:16]!r})'
    w, h = int(m.group(1)), int(m.group(2))
    px = raw[m.end():]
    font = font_from_image()
    if font[:4] != b'FNT1':
        return False, '(no font in the image)'

    def cell_ok(cx, cy, c):
        for r in range(16):
            bits = font[16 + (ord(c) - 0x20) * 16 + r]
            row = (cy * 16 + r) * w * 3
            for b in range(8):
                o = row + (cx * 8 + b) * 3
                on = bits >> (7 - b) & 1
                if px[o:o + 3] != (b'\xaa\xaa\xaa' if on else b'\x00\x00\x00'):
                    return False
        return True
    for cy in range(min(25, h // 16)):
        for cx in range(min(80, w // 8) - len(text) + 1):
            if all(cell_ok(cx + i, cy, c) for i, c in enumerate(text)):
                return True, f'(found at cell {cx},{cy} on a {w}x{h} dump)'
    return False, f'({text!r} not found on a {w}x{h} dump)'


# VGA's 16 colours, as fb_cell draws an attribute byte (bit 7 ignored)
PALETTE = [0x000000, 0x0000AA, 0x00AA00, 0x00AAAA, 0xAA0000, 0xAA00AA, 0xAA5500, 0xAAAAAA,
           0x555555, 0x5555FF, 0x55FF55, 0x55FFFF, 0xFF5555, 0xFF55FF, 0xFFFF55, 0xFFFFFF]


def screen_equals_memory(ppm, mem):
    """(ok, detail): every one of the 80x25 cells on the dump is MEM's
    character drawn in the image's font, fg/bg from its attribute."""
    raw = open(ppm, 'rb').read()
    m = re.match(rb'P6\s+(\d+)\s+(\d+)\s+(\d+)\s', raw)
    w = int(m.group(1))
    px = raw[m.end():]
    font = font_from_image()
    bad = []
    for cell in range(80 * 25):
        ch, at = mem[2 * cell], mem[2 * cell + 1]
        g = ch - 0x20 if 0x20 <= ch <= 0x7E else 0
        fg = PALETTE[at & 15].to_bytes(3, 'big')
        bg = PALETTE[at >> 4 & 7].to_bytes(3, 'big')
        cx, cy = cell % 80, cell // 80
        for r in range(16):
            bits = font[16 + g * 16 + r]
            row = (cy * 16 + r) * w * 3
            for b in range(8):
                o = row + (cx * 8 + b) * 3
                if px[o:o + 3] != (fg if bits >> (7 - b) & 1 else bg):
                    bad.append((cx, cy))
                    break
            else:
                continue
            break
    return not bad, f'({len(bad)} of 2000 cells differ{": first " + str(bad[:4]) if bad else ""})'


failures = []


def check(label, cond, detail=''):
    print(f'[{"PASS" if cond else "FAIL"}] {label} {detail}', flush=True)
    if not cond:
        failures.append(label)


# ---- H1, H2: the multiboot2 header, host side ----
r = subprocess.run(['grub-file', '--is-x86-multiboot2', IMG])
check('H1 grub-file --is-x86-multiboot2 accepts the image', r.returncode == 0, f'(rc {r.returncode})')
asm = open(ASM).read()
ORG = int(re.search(r'^KERNEL_ORG\s+equ\s+0x([0-9A-Fa-f]+)', asm, re.M).group(1), 16)
KPS = int(re.search(r'^KERNEL_PADDED_SIZE\s+equ\s+0x([0-9A-Fa-f]+)', asm, re.M).group(1), 16)
data = open(IMG, 'rb').read()
offs = [o for o in range(0, 32768, 8) if data[o:o + 4] == struct.pack('<I', 0xE85250D6)]
h2 = []
if len(offs) == 1:
    o = offs[0]
    magic, arch, hlen, csum = struct.unpack_from('<IIII', data, o)
    h2.append(('checksum', (magic + arch + hlen + csum) & 0xFFFFFFFF == 0 and arch == 0))
    tags, q = {}, o + 16
    while q < o + hlen:
        ttype, tflags, tsize = struct.unpack_from('<HHI', data, q)
        tags[ttype] = data[q:q + tsize]
        if ttype == 0:
            break
        q += (tsize + 7) & ~7
    a = tags.get(2)
    if a:
        haddr, laddr, lend, bend = struct.unpack_from('<IIII', a, 8)
        h2 += [('load_addr = KERNEL_ORG', laddr == ORG),
               ('header_addr matches the file offset', haddr - laddr == o - 512),
               ('load_end = KERNEL_ORG + KERNEL_PADDED_SIZE', lend == ORG + KPS and bend in (0, lend))]
    else:
        h2.append(('address tag present', False))
    e = tags.get(3)
    h2.append(('entry tag points into the kernel',
               bool(e) and ORG <= struct.unpack_from('<I', e, 8)[0] < ORG + KPS))
    h2.append(('end tag present', 0 in tags))
check('H2 header: one, 8-aligned, in the first 32 KiB, tags consistent',
      len(offs) == 1 and all(ok for _, ok in h2),
      f'(magic at {offs}; {[n for n, ok in h2 if not ok] or "all tags ok"})')

# ---- H4: the font's license travels with the image ----
check('H4 make-uefi-usb.sh writes FONT-LICENSE.txt next to forth.img',
      '--license "$MOUNTPOINT/FONT-LICENSE.txt"' in src)

# ---- H3: the console font, where the kernel looks for it ----
spec_wc = __import__('importlib.util').util.spec_from_file_location(
    'wc', os.path.join(ROOT, 'tools', 'write-catalog.py'))
wc = __import__('importlib.util').util.module_from_spec(spec_wc)
spec_wc.loader.exec_module(wc)
m_fb = re.search(r'^FONT_BLK\s+equ\s+(\d+)', asm, re.M)
FONT_BLK = int(m_fb.group(1)) if m_fb else -1
fres = getattr(wc, 'FONT_RESERVED', None)
check('H3 the font: FONT_BLK = write-catalog FONT_RESERVED.start, FNT1 there in the image',
      fres is not None and FONT_BLK == fres.start and font_from_image()[:6] == b'FNT1\x20\x5f',
      f'(FONT_BLK {FONT_BLK}, FONT_RESERVED {fres}, header {font_from_image()[:8]!r})')

for f in (OVMF_CODE, OVMF_VARS, MEMDISK, IMG):
    if not os.path.exists(f):
        die(3, f'INSTRUMENT FAIL: missing {f}')

# ---- build the stick replica, rootless ----
work = tempfile.mkdtemp(prefix='uefi1-')
try:
    mnt = os.path.join(work, 'esp')             # stands for $MOUNTPOINT
    os.makedirs(os.path.join(mnt, 'boot', 'grub'))
    os.makedirs(os.path.join(mnt, 'EFI', 'BOOT'))
    shutil.copy(MEMDISK, os.path.join(mnt, 'memdisk'))
    shutil.copy(IMG, os.path.join(mnt, 'forth.img'))
    run([sys.executable, os.path.join(ROOT, 'tools', 'make_font_blocks.py'), '--license',
         os.path.join(mnt, 'FONT-LICENSE.txt')])
    open(os.path.join(mnt, 'boot', 'grub', 'grub.cfg'), 'w').write(grub_cfg)
    run(['grub-mkstandalone', '--format=x86_64-efi',
         f'--output={mnt}/EFI/BOOT/BOOTX64.EFI',
         '--locales=', '--fonts=', '--themes=',
         f'boot/grub/grub.cfg={mnt}/boot/grub/grub.cfg'])

    with open(OUT, 'wb') as f:
        f.truncate(DISK_MIB * 1024 * 1024)
    # Determinism (owner ruling 2026-09-28): the replica's sha must repeat
    # run to run.  Measured sources of drift: sgdisk's random disk and
    # partition GUIDs, and FAT directory timestamps.  All three pinned.
    run(['sgdisk', '--zap-all', OUT])
    run(['sgdisk', '-n', '1:2048:+1M', '-t', '1:ef02', '-c', '1:BIOS Boot', OUT])
    run(['sgdisk', '-n', '2:0:0', '-t', '2:ef00', '-c', '2:EFI System', OUT])
    run(['sgdisk', '-U', 'F0E7B007-0000-4000-8000-000000000000',
         '-u', '1:F0E7B007-0000-4000-8000-000000000001',
         '-u', '2:F0E7B007-0000-4000-8000-000000000002', OUT])
    info = run(['sgdisk', '-i', '2', OUT]).stdout
    first = int(re.search(r'First sector: (\d+)', info).group(1))
    last = int(re.search(r'Last sector: (\d+)', info).group(1))
    esp = os.path.join(work, 'esp.fat')
    with open(esp, 'wb') as f:
        f.truncate((last - first + 1) * 512)
    epoch = 1790000000                          # fixed; any constant
    env = dict(os.environ, MTOOLS_SKIP_CHECK='1', SOURCE_DATE_EPOCH=str(epoch))
    # fixed volume ID; --invariant fixes the label entry's time (mkfs.fat
    # ignores SOURCE_DATE_EPOCH, measured 2026-09-28)
    run(['mkfs.fat', '-F', '32', '-n', 'FORTHBOOT', '--invariant', '-i', 'F0E7B007', esp], env=env)
    for dp, _, fs in os.walk(mnt):
        for f in fs:
            os.utime(os.path.join(dp, f), (epoch, epoch))
    for d in ('/boot', '/boot/grub', '/EFI', '/EFI/BOOT'):
        run(['mmd', '-i', esp, '::' + d], env=env)
    for rel in ('memdisk', 'forth.img', 'FONT-LICENSE.txt', 'boot/grub/grub.cfg', 'EFI/BOOT/BOOTX64.EFI'):
        run(['mcopy', '-m', '-i', esp, os.path.join(mnt, rel), '::/' + rel], env=env)
    run(['dd', f'if={esp}', f'of={OUT}', 'bs=512', f'seek={first}', 'conv=notrunc',
         'status=none'])
    nbios = bios_half(OUT, 2048, 2048, work)
    print(f'stick replica {OUT}: GPT, ESP sectors {first}-{last}, BIOS core {nbios} sectors, '
          f'sha256 {hashlib.sha256(open(OUT, "rb").read()).hexdigest()[:16]}')

    def boot(fw):
        """Boot the replica; return (socket or None, serial text, ok seen)."""
        argv = ['qemu-system-x86_64', '-M', 'q35', '-m', '512']
        if fw == 'ovmf':
            vars_copy = os.path.join(work, 'vars.fd')
            shutil.copy(OVMF_VARS, vars_copy)
            argv += ['-drive', f'if=pflash,format=raw,readonly=on,file={OVMF_CODE}',
                     '-drive', f'if=pflash,format=raw,file={vars_copy}']
        pf = qemu_pid.pidfile(f'uefi-boot-{fw}')
        atexit.register(qemu_pid.kill_pidfile, pf)
        errf = os.path.join(work, f'qemu-{fw}.stderr')
        q = subprocess.Popen(
            argv + ['-drive', f'if=none,id=stick,format=raw,file={OUT}',
                    '-device', 'qemu-xhci', '-device', 'usb-storage,drive=stick',
                    '-display', 'none', '-net', 'none', '-no-reboot', '-pidfile', pf,
                    '-monitor', f'tcp:127.0.0.1:{MON},server=on,wait=off',
                    '-serial', f'tcp:127.0.0.1:{PORT},server=on,wait=on'],
            stdout=subprocess.DEVNULL, stderr=open(errf, 'w'))
        # Our QEMU owns both ports before the connect, or the run stops naming
        # why (a QEMU that exited, e.g. on an image lock).  wait=on: the guest
        # does not start until this client attaches, so no firmware or GRUB
        # output is lost before the connect.
        qemu_pid.wait_started(q, pf, [PORT, MON], f'uefi-boot ({fw})', errf)
        s, t0 = None, time.time()
        while s is None and time.time() - t0 < 10:
            try:
                s = socket.create_connection(('127.0.0.1', PORT), timeout=1)
            except OSError:
                time.sleep(0.2)
        if s is None:
            die(3, f'INSTRUMENT FAIL: no serial listener on {PORT} ({fw})')
        s.settimeout(1)
        raw, ok, plain = b'', False, ''
        while time.time() - t0 < WAIT and q.poll() is None:
            try:
                d = s.recv(65536)
                if not d:
                    break
                raw += d
            except socket.timeout:
                pass
            except OSError as e:
                print(f'[{fw}] serial closed: {e!r}; QEMU stderr: {open(errf).read().strip()[-200:]!r}')
                break
            plain = re.sub(r'\x1b\[[0-9;?]*[A-Za-z]', '', raw.decode('utf-8', 'replace'))
            if plain.find(BANNER) >= 0 and plain.rstrip().endswith('ok'):
                ok = True
                break
        open(f'{OUT}.{fw}.serial.log', 'w').write(plain)
        print(f'[{fw}] serial: {len(plain)} bytes after {time.time() - t0:.0f} s; banner + ok: {ok}')
        for l in [l for l in plain.splitlines() if l.startswith('MB2:')]:
            print(f'  | {l}')
        return s, plain, ok, (pf, q)

    def send(s, cmd, budget=30):
        rep, how = ser.send_until_prompt(s, cmd, budget=budget)
        body = rep.split('\r\n', 1)[1] if '\r\n' in rep else ''
        print(f'>>> {cmd}\n    {body.strip()[-200:]!r}  [{how}]', flush=True)
        return body

    def last_num(b):
        v = re.findall(r'(-?[0-9A-F]+) ok', b)
        return v[-1] if v else None

    def common(fw, s, tag):
        """I2/I3 and the boot report, on either firmware."""
        b = send(s, 'DECIMAL BOOT-MODE .')
        want = '3' if fw == 'ovmf' else '1'
        check(f'{tag}1 BOOT-MODE = {want} ({"UEFI multiboot2" if fw == "ovmf" else "BIOS memdisk"})',
              last_num(b) == want, f'({b.strip()!r})')
        b = send(s, 'S" HELLO-APP" LOAD-VOCAB', 90)
        b2 = send(s, "ALSO HELLO-APP ' HELLO-RUN DROP PREVIOUS")
        check(f'{tag}2 HELLO-APP loads from blocks and HELLO-RUN is found',
              'HELLO-APP present, skipped' not in b and not re.search(r'\S+ \? ', b) and '?' not in b2,
              f'(load {b.strip()[-120:]!r}; {b2.strip()!r})')
        b = send(s, 'ONLY FORTH DEFINITIONS ALSO AUTO-DETECT AUTO-DETECT-REPORT PREVIOUS')
        want = 'Boot: UEFI (multiboot2)' if fw == 'ovmf' else 'Boot: BIOS (memdisk)'
        check(f'{tag}3 AUTO-DETECT-REPORT says {want!r}', want in b, f'({b.strip()[:160]!r})')
        b = send(s, 'ONLY FORTH DEFINITIONS DECIMAL DEPTH .')
        check(f'{tag}4 DEPTH 0', last_num(b) == '0', f'({b.strip()!r})')
        # PCI-TYPES and the xHCI BAR: OVMF puts it above 4 GiB (64-bit BAR,
        # 0xC0_0000_0000, measured 2026-10-12); SeaBIOS below
        b = send(s, 'USING PCI-ENUM PCI-TYPES ONLY FORTH DEFINITIONS')
        usb = [l for l in b.splitlines() if 'USB host' in l]
        if fw == 'ovmf':
            check(f'{tag}9 PCI-TYPES: the xHCI 64-bit BAR in full, 0xC000000000, flagged unreachable by name',
                  any(' MMIO 0xC000000000 ' in l and 'above 4 GiB: unreachable' in l for l in usb), f'({usb})')
        else:
            check(f'{tag}9 PCI-TYPES: the xHCI base below 4 GiB, 8 hex digits, no flag',
                  bool(usb) and re.search(r' at [0-9A-F]{2} [0-9A-F]{2} [0-9A-F]{2} MMIO [0-9A-F]{8}\b', usb[0]) is not None
                  and 'unreachable' not in usb[0], f'({usb})')
        screens(fw, s, tag)

    def raw_send(s, text, settle=3.0):
        """Type TEXT (an app owns the keyboard: no prompt to wait for),
        then read for SETTLE seconds."""
        s.sendall(text.encode())
        t0, got = time.time(), b''
        while time.time() - t0 < settle:
            try:
                got += s.recv(65536)
            except socket.timeout:
                pass
        return got.decode('ascii', 'replace')

    def screen_mem(addr, name):
        path = os.path.join(work, name)
        # quoted: HMP reads `4000 /tmp/...` as the expression 4000 / tmp...
        reply = mon_cmd(f'pmemsave 0x{addr} 4000 "{path}"')
        t0 = time.time()
        while (not os.path.exists(path) or os.path.getsize(path) < 4000) and time.time() - t0 < 5:
            time.sleep(0.1)
        if not os.path.exists(path) or os.path.getsize(path) < 4000:
            die(3, f'INSTRUMENT FAIL: pmemsave wrote no screen memory; monitor said {reply[-300:]!r}')
        return open(path, 'rb').read()

    def text_of(mem):
        return ''.join(chr(mem[2 * i]) if 0x20 <= mem[2 * i] < 0x7F else ' ' for i in range(2000))

    def screens(fw, s, tag):
        """The forms and the editor draw on this firmware's screen."""
        want = '80000' if fw == 'ovmf' else 'B8000'
        b = send(s, 'HEX ALSO HAL FB-BASE . PREVIOUS DECIMAL')
        check(f'{tag}5 the display contract: FB-BASE = {want}', last_num(b) == want, f'({b.strip()!r})')
        # a form, in FORM-RUN's KEY loop
        send(s, 'ALSO HELLO-APP')
        raw_send(s, 'HELLO-RUN\r')
        mem = screen_mem(want, f'{fw}-hello.bin')
        check(f'{tag}6 HELLO-RUN draws its form in the screen memory', 'Hello Form Test' in text_of(mem),
              f'({text_of(mem)[:80].strip()!r})')
        inv = sum(1 for i in range(2000) if mem[2 * i + 1] == 0x70)
        check(f'{tag}6b the form uses inverse video (attribute 0x70 cells), so the colours are compared too',
              inv > 0, f'({inv} cells)')
        if fw == 'ovmf':
            dump = os.path.join(work, 'hello.ppm')
            mon_cmd(f'screendump {dump}')
            check('S1 the form on the framebuffer, all 2000 cells (KEY wait flush)',
                  *screen_equals_memory(dump, mem))
        raw_send(s, '\x1b', 2)                   # ESC: FORM-RUN quits
        send(s, 'ONLY FORTH DEFINITIONS')
        # notepad's editor, in RAW-SCAN's wait (entered with the New button)
        send(s, 'S" NOTEPAD" LOAD-VOCAB', 90)
        send(s, 'ALSO NOTEPAD')
        raw_send(s, 'NOTEPAD-RUN\r')
        raw_send(s, '1')                          # button 1 = New: edit mode
        mem = screen_mem(want, f'{fw}-notepad.bin')
        txt = text_of(mem)
        check(f'{tag}7 notepad\'s editor draws (title, and the status line Ln1 Col1)',
              'ForthOS Notepad' in txt and 'Ln1 Col1' in txt, f'({txt[:80].strip()!r} ... {txt[-80:].strip()!r})')
        if fw == 'ovmf':
            dump = os.path.join(work, 'notepad.ppm')
            mon_cmd(f'screendump {dump}')
            check('S2 the editor on the framebuffer, all 2000 cells (RAW-SCAN flush)',
                  *screen_equals_memory(dump, mem))
        mon_cmd('sendkey esc')                    # leave edit mode (the keyboard ring)
        time.sleep(1)
        raw_send(s, '\x1b', 2)                   # ESC: the form quits
        b = send(s, 'ONLY FORTH DEFINITIONS DECIMAL DEPTH .')
        check(f'{tag}8 back at the prompt after both apps, DEPTH 0', last_num(b) == '0', f'({b.strip()!r})')

    # ---- UEFI: OVMF, no CSM ----
    s, plain, seen_ok, pf = boot('ovmf')
    if CONTROL not in plain:
        die(3, 'INSTRUMENT FAIL: GRUB\'s UEFI menu never reached serial -- '
               'the gate would say nothing about ForthOS; no score')
    mod = re.search(r'MB2: module ([0-9A-F]{8})-([0-9A-F]{8})', plain)
    moved = re.search(r'MB2: module moved to ([0-9A-F]{8})-([0-9A-F]{8})', plain)
    final = moved or mod                # where BLK_IMAGE_BASE must point
    wins = re.findall(r'MB2: window ([0-9A-F]{8})-([0-9A-F]{8}) available ([0-9A-F]{8}) of ([0-9A-F]{8})', plain)
    check('B2 report: module range, three windows, no REFUSED',
          bool(mod) and len(wins) == 3 and 'REFUSED' not in plain,
          f'(module {mod.groups() if mod else None}, windows {wins})')
    check('B3 banner + ok', seen_ok)
    check('B4 framebuffer console on', 'MB2: framebuffer console on' in plain,
          f'({[l for l in plain.splitlines() if "framebuffer" in l or "font" in l]})')
    if seen_ok and mod:
        b = send(s, 'HEX 28098 @ . DECIMAL')
        check('I1 BLK_IMAGE_BASE = the module start (after any move)',
              last_num(b) == (final.group(1).lstrip('0') or '0'),
              f'(cell {last_num(b)}, module {final.group(1)}{" moved" if moved else ""})')
        common('ovmf', s, 'U')
        # F1: the framebuffer shows what print_char writes
        send(s, 'PAGE')
        # split, so only the output spells UEFI4 (the echoed command line
        # reads `.( UEF) .( I4)`): F1 sees what the words print
        send(s, '.( UEF) .( I4)')
        F1_text = 'UEFI4'
        dump = os.path.join(work, 'screen.ppm')
        mon_cmd(f'screendump {dump}')
        check('F1 the framebuffer shows the text, glyph for glyph', *screen_matches(dump, F1_text))
    s.close()
    qemu_pid.kill_pidfile(pf[0])
    pf[1].wait(timeout=10)              # reaped: its ports and image lock are free

    # ---- legacy: SeaBIOS, the same image ----
    s, plain, seen_ok, pf = boot('seabios')
    check('L0 SeaBIOS: banner + ok from the same image', seen_ok)
    if seen_ok:
        common('seabios', s, 'L')
    s.close()
    qemu_pid.kill_pidfile(pf[0])
    pf[1].wait(timeout=10)
finally:
    shutil.rmtree(work, ignore_errors=True)

print(f'FAILED: {failures}' if failures else 'All UEFI-3/4 gates pass')
sys.exit(1 if failures else 0)
