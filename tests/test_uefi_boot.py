#!/usr/bin/env python3
"""UEFI-3 gate: the FORTHBOOT stick, booted by UEFI firmware with no CSM,
loads the kernel by multiboot2 and reaches the Forth `ok` prompt, with its
blocks served from the GRUB module (docs/TASK_UEFI_3_4.md).

Was UEFI-1's registered red (the stick boots to ok under OVMF,
docs/evidence/uefi-1-prereg-2026-09-28.md), XFAIL until UEFI-3; retired
in the register 2026-10-12.

  H1  grub-file --is-x86-multiboot2 accepts combined.img.
  H2  the header, read from the image: 8-aligned, inside the first 32 KiB,
      checksum; the address tag loads the kernel only (load_addr 0x7E00,
      load_end = 0x7E00 + KERNEL_PADDED_SIZE, header_addr consistent with
      the file offset); the entry tag points into the kernel.
  B1  control: GRUB's UEFI menu title reaches serial (else INSTRUMENT FAIL).
  B2  the kernel's report: `MB2: module <start>-<end>`, a line per window,
      no `REFUSED` (a module inside a window is moved above them first:
      `MB2: module moved to <start>-<end>`).
  B3  banner + ok.
  I1  BLK_IMAGE_BASE (0x28098) = the module's final start, as reported.
  I2  a block-loaded vocabulary loads from the module: S" HELLO-APP"
      LOAD-VOCAB, then HELLO-RUN is found.
  I3  DEPTH 0.

Exit 0 all pass, 1 a gate fails, 3 an instrument control fails (no score).

The image is built the way tools/make-uefi-usb.sh builds the stick, but
rootless and without any block device: sgdisk on a file, mkfs.fat on a
file, mtools to populate, dd to place.  grub.cfg is read from the
script's heredoc at run time (rule 28: test the shipped artifact), and
the grub-mkstandalone block is asserted to be the one replayed here.
Not exercised: the i386-pc half (grub-install needs a device; OVMF
never reads it).

usage: test_uefi_boot.py <serial port> [combined.img]
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
SCRIPT = os.path.join(ROOT, 'tools', 'make-uefi-usb.sh')
ASM = os.path.join(ROOT, 'src', 'kernel', 'forth.asm')
IMG = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, 'build', 'combined.img')
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
    for rel in ('memdisk', 'forth.img', 'boot/grub/grub.cfg', 'EFI/BOOT/BOOTX64.EFI'):
        run(['mcopy', '-m', '-i', esp, os.path.join(mnt, rel), '::/' + rel], env=env)
    run(['dd', f'if={esp}', f'of={OUT}', 'bs=512', f'seek={first}', 'conv=notrunc',
         'status=none'])
    print(f'stick replica {OUT}: GPT, ESP sectors {first}-{last}, '
          f'sha256 {hashlib.sha256(open(OUT, "rb").read()).hexdigest()[:16]}')

    # ---- boot it under OVMF (no CSM), serial over TCP ----
    vars_copy = os.path.join(work, 'vars.fd')
    shutil.copy(OVMF_VARS, vars_copy)
    log = OUT + '.serial.log'                 # kept for the evidence copy
    pf = qemu_pid.pidfile('uefi-boot')
    atexit.register(qemu_pid.kill_pidfile, pf)
    q = subprocess.Popen(
        ['qemu-system-x86_64', '-M', 'q35', '-m', '512',
         '-drive', f'if=pflash,format=raw,readonly=on,file={OVMF_CODE}',
         '-drive', f'if=pflash,format=raw,file={vars_copy}',
         '-drive', f'if=none,id=stick,format=raw,file={OUT}',
         '-device', 'qemu-xhci', '-device', 'usb-storage,drive=stick',
         '-display', 'none', '-net', 'none', '-no-reboot', '-pidfile', pf,
         '-serial', f'tcp:127.0.0.1:{PORT},server=on,wait=on'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # wait=on: the guest does not start until this client attaches, so no
    # firmware or GRUB output is lost before the connect.
    s = None
    t0 = time.time()
    while s is None and time.time() - t0 < 10:
        try:
            s = socket.create_connection(('127.0.0.1', PORT), timeout=1)
        except OSError:
            time.sleep(0.2)
    if s is None:
        die(3, f'INSTRUMENT FAIL: no serial listener on {PORT}')
    s.settimeout(1)
    raw = b''
    seen_control = seen_ok = False
    plain = ''
    while time.time() - t0 < WAIT and q.poll() is None:
        try:
            d = s.recv(65536)
            if not d:
                break
            raw += d
        except socket.timeout:
            pass
        plain = re.sub(r'\x1b\[[0-9;?]*[A-Za-z]', '', raw.decode('utf-8', 'replace'))
        seen_control = seen_control or CONTROL in plain
        i = plain.find(BANNER)
        if i >= 0 and plain.rstrip().endswith('ok'):
            seen_ok = True
            break
    open(log, 'w').write(plain)
    print(f'serial: {len(plain)} bytes after {time.time() - t0:.0f} s; '
          f'control seen: {seen_control}; banner + ok seen: {seen_ok}')
    for l in [l for l in plain.splitlines() if l.startswith('MB2:')]:
        print(f'  | {l}')
    if not seen_control:
        die(3, 'INSTRUMENT FAIL: GRUB\'s UEFI menu never reached serial -- '
               'the gate would say nothing about ForthOS; no score')
    tail = [l for l in plain.splitlines() if l.strip()][-4:]
    for l in tail:
        print(f'  | {l[:100]}')

    mod = re.search(r'MB2: module ([0-9A-F]{8})-([0-9A-F]{8})', plain)
    moved = re.search(r'MB2: module moved to ([0-9A-F]{8})-([0-9A-F]{8})', plain)
    final = moved or mod                # where BLK_IMAGE_BASE must point
    wins = re.findall(r'MB2: window ([0-9A-F]{8})-([0-9A-F]{8}) available ([0-9A-F]{8}) of ([0-9A-F]{8})', plain)
    check('B2 report: module range, two windows, no REFUSED',
          bool(mod) and len(wins) == 2 and 'REFUSED' not in plain,
          f'(module {mod.groups() if mod else None}, windows {wins})')
    check('B3 banner + ok', seen_ok)

    if seen_ok and mod:
        def send(cmd, budget=30):
            rep, how = ser.send_until_prompt(s, cmd, budget=budget)
            body = rep.split('\r\n', 1)[1] if '\r\n' in rep else ''
            print(f'>>> {cmd}\n    {body.strip()[-200:]!r}  [{how}]', flush=True)
            return body
        b = send('HEX 28098 @ . DECIMAL')
        v = re.findall(r'([0-9A-F]+) ok', b)
        check('I1 BLK_IMAGE_BASE = the module start (after any move)',
              v[-1:] == [final.group(1).lstrip('0') or '0'],
              f'(cell {v[-1:]}, module {final.group(1)}{" moved" if moved else ""})')
        b = send('S" HELLO-APP" LOAD-VOCAB', 90)
        b2 = send("ALSO HELLO-APP ' HELLO-RUN DROP PREVIOUS")
        check('I2 HELLO-APP loads from the module and HELLO-RUN is found',
              'HELLO-APP present, skipped' not in b and not re.search(r'\S+ \? ', b) and '?' not in b2,
              f'(load {b.strip()[-120:]!r}; {b2.strip()!r})')
        b = send('ONLY FORTH DEFINITIONS DECIMAL DEPTH .')
        check('I3 DEPTH 0', re.findall(r'(-?\d+) ok', b)[-1:] == ['0'], f'({b.strip()!r})')
    s.close()
finally:
    shutil.rmtree(work, ignore_errors=True)

print(f'FAILED: {failures}' if failures else 'All UEFI-3 gates pass')
sys.exit(1 if failures else 0)
