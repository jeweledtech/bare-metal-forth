#!/usr/bin/env python3
"""UEFI network boot gate (docs/TASK_UEFI_3_4.md, owner 2026-10-12): a
UEFI-only machine boots ForthOS over the network the way the stick does it,
GRUB EFI loading the kernel by multiboot2 and the image as a module.

  N1  host: the dnsmasq config tools/pxe/setup-dnsmasq.sh writes branches on
      DHCP option 93 (client-arch 7 and 9 = x86-64 UEFI) to a GRUB EFI boot
      file, and leaves every other client on pxelinux.0.
  N2  host: that boot file exists in the staged tree (make grub-net).
  N3  OVMF network boot (QEMU's own DHCP and TFTP serve the staged tree;
      they don't branch on option 93, N1 covers that): banner + ok.
  N4  BOOT-MODE = 3.  N5  HELLO-APP loads from the module.  N6  DEPTH 0.

Never touches the live PXE server: applying the dnsmasq config and pushing
the tree are the owner's steps (make pxe-setup, make pxe-push-grub).

usage: test_uefi_netboot.py <serial port>
"""
import atexit
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

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4471
TREE = os.path.join(ROOT, 'build', 'tftp')
DNSMASQ = os.path.join(ROOT, 'tools', 'pxe', 'setup-dnsmasq.sh')
OVMF_CODE = '/usr/share/OVMF/OVMF_CODE_4M.fd'
OVMF_VARS = '/usr/share/OVMF/OVMF_VARS_4M.fd'
BANNER = 'Bare-Metal Forth v0.1 - Ship Builders System'
WAIT = 90
failures = []


def check(label, cond, detail=''):
    print(f'[{"PASS" if cond else "FAIL"}] {label} {detail}', flush=True)
    if not cond:
        failures.append(label)


def die(code, msg):
    print(msg, flush=True)
    sys.exit(code)


# ---- N1, N2: the dnsmasq branch and its boot file ----
conf = open(DNSMASQ).read()
efi_tags = set(re.findall(r'^dhcp-match=set:(\w+),option:client-arch,([79])\s*$', conf, re.M))
tags = {t for t, _ in efi_tags}
arches = {a for _, a in efi_tags}
boots = dict(re.findall(r'^dhcp-boot=tag:(!?\w+),([^,\s]+),', conf, re.M))
efi_tag = next(iter(tags)) if len(tags) == 1 else None
efi_file = boots.get(efi_tag) if efi_tag else None
check('N1 dnsmasq: client-arch 7 and 9 tagged, that tag gets a GRUB EFI file, the rest pxelinux.0',
      arches == {'7', '9'} and bool(efi_file) and boots.get('!' + str(efi_tag)) == 'pxelinux.0'
      and not re.search(r'^dhcp-boot=pxelinux', conf, re.M),
      f'(arch tags {sorted(efi_tags)}, boots {boots})')
check('N2 the EFI boot file is in the staged tree',
      bool(efi_file) and os.path.exists(os.path.join(TREE, efi_file)), f'({efi_file})')

# ---- N3-N6: OVMF network boot from the staged tree ----
for f in (OVMF_CODE, OVMF_VARS, os.path.join(TREE, 'forth.img')):
    if not os.path.exists(f):
        die(3, f'INSTRUMENT FAIL: missing {f}')
bootfile = efi_file or 'grub/x86_64-efi/core.efi'
work = tempfile.mkdtemp(prefix='uefi-net-')
try:
    vars_copy = os.path.join(work, 'vars.fd')
    shutil.copy(OVMF_VARS, vars_copy)
    errf = os.path.join(work, 'qemu.stderr')
    pf = qemu_pid.pidfile('uefi-netboot')
    atexit.register(qemu_pid.kill_pidfile, pf)
    q = subprocess.Popen(
        ['qemu-system-x86_64', '-M', 'q35', '-m', '512',
         '-drive', f'if=pflash,format=raw,readonly=on,file={OVMF_CODE}',
         '-drive', f'if=pflash,format=raw,file={vars_copy}',
         '-nic', f'user,model=virtio-net-pci,tftp={TREE},bootfile={bootfile}',
         '-boot', 'n', '-display', 'none', '-no-reboot', '-pidfile', pf,
         '-serial', f'tcp:127.0.0.1:{PORT},server=on,wait=on'],
        stdout=subprocess.DEVNULL, stderr=open(errf, 'w'))
    qemu_pid.wait_started(q, pf, PORT, 'uefi-netboot', errf)
    s = socket.create_connection(('127.0.0.1', PORT), timeout=5)
    s.settimeout(1)
    raw, ok, t0 = b'', False, time.time()
    while time.time() - t0 < WAIT and q.poll() is None:
        try:
            d = s.recv(65536)
            if not d:
                break
            raw += d
        except socket.timeout:
            pass
        except OSError as e:
            print(f'serial closed: {e!r}')
            break
        plain = re.sub(r'\x1b\[[0-9;?]*[A-Za-z]', '', raw.decode('utf-8', 'replace'))
        if BANNER in plain and plain.rstrip().endswith('ok'):
            ok = True
            break
    plain = re.sub(r'\x1b\[[0-9;?]*[A-Za-z]', '', raw.decode('utf-8', 'replace'))
    open(os.path.join(ROOT, 'build', 'uefi-netboot.serial.log'), 'w').write(plain)
    print(f'serial: {len(plain)} bytes after {time.time() - t0:.0f} s; banner + ok: {ok}')
    for l in [l for l in plain.splitlines() if l.startswith('MB2:') or 'error' in l.lower()][:12]:
        print(f'  | {l.strip()[:140]}')
    if 'GNU GRUB' not in plain and 'GRUB' not in plain:
        die(3, 'INSTRUMENT FAIL: GRUB never reached serial over the network -- no score')
    check('N3 banner + ok over the network', ok)
    if ok:
        def send(cmd, budget=30):
            rep, how = ser.send_until_prompt(s, cmd, budget=budget)
            body = rep.split('\r\n', 1)[1] if '\r\n' in rep else ''
            print(f'>>> {cmd}\n    {body.strip()[-160:]!r}  [{how}]', flush=True)
            return body
        b = send('DECIMAL BOOT-MODE .')
        check('N4 BOOT-MODE = 3', re.findall(r'(-?\d+) ok', b)[-1:] == ['3'], f'({b.strip()!r})')
        b = send('S" HELLO-APP" LOAD-VOCAB', 90)
        b2 = send("ALSO HELLO-APP ' HELLO-RUN DROP PREVIOUS")
        check('N5 HELLO-APP loads from the module',
              'HELLO-APP present, skipped' not in b and not re.search(r'\S+ \? ', b) and '?' not in b2,
              f'(load {b.strip()[-100:]!r}; {b2.strip()!r})')
        b = send('ONLY FORTH DEFINITIONS DECIMAL DEPTH .')
        check('N6 DEPTH 0', re.findall(r'(-?\d+) ok', b)[-1:] == ['0'], f'({b.strip()!r})')
    s.close()
finally:
    shutil.rmtree(work, ignore_errors=True)

print(f'FAILED: {failures}' if failures else 'All UEFI netboot gates pass')
sys.exit(1 if failures else 0)
