#!/usr/bin/env python3
"""The VBE result cells on boot paths that never call vbe_stub (private
TASK_UNICORN_WRITER Phase 1; owner 2026-11-02: verify the zeroed cells on
the no-stub paths).

Only boot.asm far-calls vbe_stub.  vbr.asm and the multiboot2 entry do
not; for them kernel_start must zero the six cells at 0x280BC-0x280D3
(vbe_fresh is 0 in every freshly loaded kernel image), so VBE-STATUS,
VBE-MODE, FB-ADDR, FB-PITCH, FB-W, FB-H, FB-BPP and VBE-VERSION read 0.

RAM after a cold QEMU start is already 0, which would pass without any
zeroing, and the firmware clears low memory during POST (measured
2026-11-02: a QEMU loader-device poison at 0x280F0 reads back while the
VM is paused before boot, and 0 once the kernel runs under SeaBIOS).  So
the poison goes in at the one moment that tests the claim: each leg
stops the guest at kernel_start (QEMU's gdb stub, a hardware breakpoint;
the address is decoded from kernel.bin's entry jump, not hard-coded),
writes POISON into the six cells and a CONTROL value at 0x280F0, which
nothing in the kernel touches (0x280D4-0x280FF is unassigned,
docs/ARCHITECTURE.md), and lets it run.  The control reading back proves
the write landed and survived to the prompt; the cells reading 0 then
prove kernel_start cleared them.  The gdb stub is a Unix socket in a
short temp directory (no TCP port; under build/ its path passes the
108-byte sun_path limit in a checkout at a long path).

Legs (serial on argv[1], monitor on argv[2]):
  R  vbr.bin (DAP LBA baked to 1) + kernel.bin as a SeaBIOS hard disk;
     BOOT-MODE 0, text mode 720x400 (screendump)
  M  OVMF (UEFI, no CSM) -> GRUB x86_64-efi from a QEMU vvfat ESP ->
     multiboot2 /forth.img + module2 /forth.img (the config embedded in
     BOOTX64.EFI by grub-mkimage; no menu); BOOT-MODE 3.  GRUB sets
     a GOP framebuffer here; the VBE words must still read 0 (they report
     only the BIOS VBE mode the stub set).

Tools: OVMF at /usr/share/OVMF (FORTHOS_OVMF_CODE / FORTHOS_OVMF_VARS),
grub-mkimage on PATH (FORTHOS_GRUB_MKIMAGE), GRUB's x86_64-efi
modules at /usr/lib/grub/x86_64-efi (FORTHOS_GRUB_EFI).  Absent, the M
leg fails naming the package (a skip must not read like a pass).
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
VBR = os.path.join(ROOT, 'build', 'vbr.bin')
KERNEL = os.path.join(ROOT, 'build', 'kernel.bin')
COMBINED = os.path.join(ROOT, 'build', 'combined.img')
OVMF_CODE = os.environ.get('FORTHOS_OVMF_CODE', '/usr/share/OVMF/OVMF_CODE_4M.fd')
OVMF_VARS = os.environ.get('FORTHOS_OVMF_VARS', '/usr/share/OVMF/OVMF_VARS_4M.fd')
MKIMAGE = os.environ.get('FORTHOS_GRUB_MKIMAGE', 'grub-mkimage')
GRUB_EFI = os.environ.get('FORTHOS_GRUB_EFI', '/usr/lib/grub/x86_64-efi')

KERNEL_ORG = 0x7E00
CELLS = 0x280BC
CONTROL = 0x280F0
POISON = 0xA5C3E1F7            # every cell, every byte nonzero
CONTROL_POISON = 0x5A5A1234
TOTAL = 9
PASS = FAIL = 0


def check(name, ok, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {name}')
    else:
        FAIL += 1
        print(f'  FAIL: {name} -- {detail}')


class Gdb:
    """Just enough of the gdb remote protocol: hw breakpoint, write, go."""

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

    def _recv_packet(self, budget):
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
        return self._recv_packet(budget)

    def write(self, addr, data):
        return self.cmd(f'M{addr:x},{len(data):x}:{data.hex()}')

    def close(self):
        try:
            self.s.sendall(b'$D#44')
        except OSError:
            pass
        self.s.close()


def kernel_start_addr():
    """kernel_start: the target of the jmp at KERNEL_ORG (kernel_entry), or
    KERNEL_ORG itself in a kernel without that entry jump (before Phase 1,
    kernel_start was the first instruction)."""
    b = open(KERNEL, 'rb').read(5)
    if b[0] == 0xE9:
        return KERNEL_ORG + 5 + int.from_bytes(b[1:5], 'little', signed=True)
    if b[0] == 0xEB:
        return KERNEL_ORG + 2 + int.from_bytes(b[1:2], 'little', signed=True)
    return KERNEL_ORG


def plant_poison(gdbpath, budget):
    """Stop at kernel_start, poison the cells and the control, continue."""
    g = Gdb(gdbpath)
    try:
        ks = kernel_start_addr()
        r1 = g.cmd(f'Z1,{ks:x},1')
        g.s.sendall(b'$c#63')
        stop = g._recv_packet(budget)
        w1 = g.write(CELLS, POISON.to_bytes(4, 'little') * 6)
        w2 = g.write(CONTROL, CONTROL_POISON.to_bytes(4, 'little'))
        back = g.cmd(f'm{CELLS:x},18')
        r2 = g.cmd(f'z1,{ks:x},1')
        return {'kernel_start': hex(ks), 'bp': r1, 'stop': stop, 'write': (w1, w2),
                'readback': back, 'unbp': r2}
    finally:
        g.close()
        # QEMU pauses the VM when the gdb client goes away: resume it
        time.sleep(0.3)
        monitor('cont', wait=0.5)


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
    return out.decode(errors='replace')


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


# Raw cells by address (not only through the words), then the words.
Q_RAW = ('HEX 280BC @ U. 280C0 @ U. 280C4 @ U. 280C8 @ U. 280CC @ U. '
         '280D0 @ U. 280F0 @ U. DECIMAL')
Q = ('VBE-STATUS . VBE-MODE . FB-ADDR U. FB-PITCH . FB-W . FB-H . '
     'FB-BPP . VBE-VERSION . BOOT-MODE .')


def hexnums(reply):
    line = [l for l in reply.splitlines() if l.strip().endswith('ok')]
    if not line:
        return []
    body = line[-1].rsplit('ok', 1)[0]
    body = body.split('DECIMAL')[0] if 'DECIMAL' in body else body
    return [int(t, 16) for t in re.findall(r'\b[0-9A-Fa-f]+\b', body)]


def run_leg(leg, cmd, screendump):
    pidf = qemu_pid.pidfile('vbe-nostub-' + leg)
    qemu_pid.kill_pidfile(pidf)
    err = os.path.join(ROOT, 'build', f'vbe-nostub-{leg}-qemu.err')
    gdbpath = os.path.join(SOCKDIR, f'{leg}.gdb')
    if os.path.exists(gdbpath):
        os.remove(gdbpath)
    cmd = cmd + [
        '-S', '-chardev', f'socket,id=gdb0,path={gdbpath},server=on,wait=off',
        '-gdb', 'chardev:gdb0',
        '-serial', f'tcp:127.0.0.1:{SPORT},server=on,wait=off',
        '-monitor', f'tcp:127.0.0.1:{MPORT},server=on,wait=off',
        '-display', 'none', '-pidfile', pidf]
    proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.DEVNULL,
                            stderr=open(err, 'w'))
    try:
        qemu_pid.wait_started(proc, pidf, [SPORT, MPORT], 'vbe-nostub-' + leg, err)
        planted = plant_poison(gdbpath, 120)
        print(f'  {leg} gdb: {planted}')
        s = ser.connect_and_sync(SPORT, budget=120)
        raw = ser.send_until_prompt(s, Q_RAW, budget=20)[0]
        q = nums(ser.send_until_prompt(s, Q, budget=20)[0])
        five = ser.send_until_prompt(s, '2 3 + .', budget=10)[0]
        size = screen_size(os.path.join(ROOT, 'build', f'vbe-nostub-{leg}.ppm')) \
            if screendump else None
        s.close()
        return raw, hexnums(raw), q, five, size, planted
    finally:
        qemu_pid.kill_pidfile(pidf)


print('=== VBE cells on the no-stub boot paths (VBR, multiboot2) ===')
print(f'  poison {POISON:#x} at {CELLS:#x}..{CELLS + 23:#x}, '
      f'control {CONTROL_POISON:#x} at {CONTROL:#x}')

# R: vbr.bin + kernel.bin, SeaBIOS hard disk (test_vbr_boot.py's layout)
work = tempfile.mkdtemp(prefix='forthos-vbe-nostub-')
SOCKDIR = tempfile.mkdtemp(prefix='fvn-')
try:
    vbr = bytearray(open(VBR, 'rb').read())
    dap = re.compile(b'\x10\x00..\x00\x7e\x00\x00\xef\xbe\xad\xde\x00\x00\x00\x00',
                     re.DOTALL)
    hits = [m.start() for m in dap.finditer(bytes(vbr))]
    if len(hits) != 1:
        print(f'  FAIL: vbr.bin sentinel DAP hits {hits}')
        print(f'\nPassed: 0/{TOTAL}')
        sys.exit(1)
    off = hits[0] + 8
    vbr[off:off + 4] = (1).to_bytes(4, 'little')
    disk = os.path.join(work, 'vbr-disk.img')
    with open(disk, 'wb') as f:
        f.write(bytes(vbr) + open(KERNEL, 'rb').read())
    raw, h, q, five, size, pl = run_leg(
        'vbr', ['qemu-system-i386', '-m', '128',
                '-drive', f'file={disk},format=raw,if=ide'], True)
    print(f'  vbr raw cells + control: {[hex(x) for x in h]}')
    print(f'  vbr words: {q} screen {size}')
    check('R1 vbr: stopped at kernel_start, poison written (read back), control kept to the prompt',
          pl['write'] == ('OK', 'OK') and pl['readback'] == POISON.to_bytes(4, 'little').hex() * 6
          and h[6:7] == [CONTROL_POISON], f'{pl} {raw}')
    check('R2 vbr: the six cells, poisoned, read 0 (kernel_start zeroed them)',
          h[:6] == [0] * 6, raw)
    check('R3 vbr: VBE-STATUS 0 and every VBE word 0', q[:8] == [0] * 8, q)
    check('R4 vbr: BOOT-MODE 0, console answers 5, text mode 720x400',
          q[8:9] == [0] and '5 ok' in five and size == (720, 400),
          f'{q} {five!r} {size}')

    # M: OVMF -> GRUB EFI (vvfat ESP) -> multiboot2
    missing = [p for p in (OVMF_CODE, OVMF_VARS, GRUB_EFI) if not os.path.exists(p)]
    if shutil.which(MKIMAGE) is None:
        missing.append(MKIMAGE)
    if missing:
        print(f'  FAIL: M leg cannot run: {missing} absent '
              '(apt install ovmf grub-efi-amd64-bin grub-common, or set FORTHOS_*)')
        print(f'\nPassed: {PASS}/{TOTAL}')
        sys.exit(1)
    esp = os.path.join(work, 'esp')
    os.makedirs(os.path.join(esp, 'EFI', 'BOOT'))
    shutil.copy(COMBINED, os.path.join(esp, 'forth.img'))
    cfg = os.path.join(work, 'early.cfg')
    with open(cfg, 'w') as f:
        f.write('search --no-floppy --file --set=root /forth.img\n'
                'multiboot2 /forth.img\nmodule2 /forth.img\nboot\n')
    r = subprocess.run([MKIMAGE, '-O', 'x86_64-efi', '-d', GRUB_EFI, '-c', cfg,
                        '-p', '/EFI/BOOT', '-o', f'{esp}/EFI/BOOT/BOOTX64.EFI',
                        'part_msdos', 'part_gpt', 'fat', 'search', 'search_fs_file',
                        'multiboot2', 'efi_gop', 'boot'],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f'  FAIL: grub-mkimage rc {r.returncode}: {r.stderr.strip()[-300:]}')
        print(f'\nPassed: {PASS}/{TOTAL}')
        sys.exit(1)
    vars_copy = os.path.join(work, 'vars.fd')
    shutil.copy(OVMF_VARS, vars_copy)
    raw, h, q, five, _, pl = run_leg(
        'mb2', ['qemu-system-x86_64', '-M', 'q35', '-m', '512', '-net', 'none',
                '-drive', f'if=pflash,format=raw,readonly=on,file={OVMF_CODE}',
                '-drive', f'if=pflash,format=raw,file={vars_copy}',
                '-drive', f'file=fat:{esp},format=raw,if=virtio,readonly=on'], False)
    print(f'  mb2 raw cells + control: {[hex(x) for x in h]}')
    print(f'  mb2 words: {q}')
    check('M1 mb2: BOOT-MODE 3 (multiboot2 under UEFI)', q[8:9] == [3], q)
    check('M2 mb2: stopped at kernel_start, poison written (read back), control kept to the prompt',
          pl['write'] == ('OK', 'OK') and pl['readback'] == POISON.to_bytes(4, 'little').hex() * 6
          and h[6:7] == [CONTROL_POISON], f'{pl} {raw}')
    check('M3 mb2: the six cells, poisoned, read 0 (kernel_start zeroed them)',
          h[:6] == [0] * 6, raw)
    check('M4 mb2: VBE-STATUS 0 and every VBE word 0 (GOP framebuffer is not VBE)',
          q[:8] == [0] * 8, q)
    check('M5 mb2: console answers 5', '5 ok' in five, five)
finally:
    shutil.rmtree(work, ignore_errors=True)
    shutil.rmtree(SOCKDIR, ignore_errors=True)

print(f'\nPassed: {PASS}/{TOTAL}')
sys.exit(0 if PASS == TOTAL and FAIL == 0 else 1)
