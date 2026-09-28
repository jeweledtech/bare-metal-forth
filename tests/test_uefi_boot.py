#!/usr/bin/env python3
"""UEFI-1 red: the FORTHBOOT stick, booted by UEFI firmware with no CSM,
reaches the Forth `ok` prompt on serial.

docs/evidence/uefi-1-prereg-2026-09-28.md.  Registered red, predicted
XFAIL until UEFI-3 (multiboot2 entry) lands:

  XFAIL  -> prints 'XFAIL (expected)', exit 0 (make test stays green)
  XPASS  -> prints 'XPASS ... remove the red', exit 1 (the gate)
  instrument control fails -> 'INSTRUMENT FAIL', exit 3 (no score)
  drift from make-uefi-usb.sh -> 'FAIL', exit 1

The image is built the way tools/make-uefi-usb.sh builds the stick, but
rootless and without any block device: sgdisk on a file, mkfs.fat on a
file, mtools to populate, dd to place.  grub.cfg is read from the
script's heredoc at run time (rule 28: test the shipped artifact), and
the grub-mkstandalone block is asserted to be the one replayed here.
Not exercised: the i386-pc half (grub-install needs a device; OVMF
never reads it).

usage: test_uefi_boot.py [combined.img]
"""
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

UEFI_REDS = ['uefi1_RED_stick_boots_to_ok_under_ovmf']

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, 'tools', 'make-uefi-usb.sh')
IMG = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'build', 'combined.img')
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
    run(['sgdisk', '--zap-all', OUT])
    run(['sgdisk', '-n', '1:2048:+1M', '-t', '1:ef02', '-c', '1:BIOS Boot', OUT])
    run(['sgdisk', '-n', '2:0:0', '-t', '2:ef00', '-c', '2:EFI System', OUT])
    info = run(['sgdisk', '-i', '2', OUT]).stdout
    first = int(re.search(r'First sector: (\d+)', info).group(1))
    last = int(re.search(r'Last sector: (\d+)', info).group(1))
    esp = os.path.join(work, 'esp.fat')
    with open(esp, 'wb') as f:
        f.truncate((last - first + 1) * 512)
    run(['mkfs.fat', '-F', '32', '-n', 'FORTHBOOT', esp])
    env = dict(os.environ, MTOOLS_SKIP_CHECK='1')
    for d in ('/boot', '/boot/grub', '/EFI', '/EFI/BOOT'):
        run(['mmd', '-i', esp, '::' + d], env=env)
    for rel in ('memdisk', 'forth.img', 'boot/grub/grub.cfg', 'EFI/BOOT/BOOTX64.EFI'):
        run(['mcopy', '-i', esp, os.path.join(mnt, rel), '::/' + rel], env=env)
    run(['dd', f'if={esp}', f'of={OUT}', 'bs=512', f'seek={first}', 'conv=notrunc',
         'status=none'])
    print(f'stick replica {OUT}: GPT, ESP sectors {first}-{last}, '
          f'sha256 {hashlib.sha256(open(OUT, "rb").read()).hexdigest()[:16]}')

    # ---- boot it under OVMF (no CSM) ----
    vars_copy = os.path.join(work, 'vars.fd')
    shutil.copy(OVMF_VARS, vars_copy)
    log = OUT + '.serial.log'                 # kept for the evidence copy
    q = subprocess.Popen(
        ['qemu-system-x86_64', '-M', 'q35', '-m', '512',
         '-drive', f'if=pflash,format=raw,readonly=on,file={OVMF_CODE}',
         '-drive', f'if=pflash,format=raw,file={vars_copy}',
         '-drive', f'if=none,id=stick,format=raw,file={OUT}',
         '-device', 'qemu-xhci', '-device', 'usb-storage,drive=stick',
         '-display', 'none', '-serial', f'file:{log}', '-net', 'none', '-no-reboot'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    seen_control = seen_ok = False
    t0 = time.time()
    while time.time() - t0 < WAIT and q.poll() is None:
        time.sleep(1)
        text = open(log, 'rb').read().decode('utf-8', 'replace') if os.path.exists(log) else ''
        plain = re.sub(r'\x1b\[[0-9;?]*[A-Za-z]', '', text)
        seen_control = seen_control or CONTROL in plain
        i = plain.find(BANNER)
        if i >= 0 and re.search(r'\bok\b', plain[i + len(BANNER):]):
            seen_ok = True
            break
    q.kill()
    q.wait()
    print(f'serial: {len(plain)} bytes after {time.time() - t0:.0f} s; '
          f'control seen: {seen_control}; banner + ok seen: {seen_ok}')
    tail = [l for l in plain.splitlines() if l.strip()][-4:]
    for l in tail:
        print(f'  | {l[:100]}')
finally:
    shutil.rmtree(work, ignore_errors=True)

if not seen_control and not seen_ok:
    die(3, 'INSTRUMENT FAIL: GRUB\'s UEFI menu never reached serial -- '
           'the red would say nothing about ForthOS; no score')
if seen_ok:
    die(1, f'XPASS: {UEFI_REDS[0]} passed -- stop; record it, then remove the red')
print(f'XFAIL (expected): {UEFI_REDS[0]} -- no banner/ok within {WAIT} s')
sys.exit(0)
