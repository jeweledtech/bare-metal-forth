#!/usr/bin/env python3
"""VBR variant boot smoke.

Positive: vbr.bin with 1 baked at the derived DAP LBA offset,
concatenated with kernel.bin, boots to a live `ok` prompt under
SeaBIOS EDD (hard-disk boot, not floppy -- the variant is a
chainload/HDD loader and AH=42h needs a hard drive number).
Reaching `ok` proves the chunked 224-sector EDD read succeeded;
there is no other way to get there.

Negative (the loud-fail proof): the UNBAKED template, sentinel
still in place, must die in disk_error and never reach a prompt.

Channel note: the VBR's banner and 'DISK ERR' go out via int 0x10
(VGA text), NOT the 16550 -- serial only carries kernel output.
The HP has no physical UART and the net console is kernel-driven,
so the VBR is screen-only on iron BY DESIGN; operator-visible
loudness of DISK ERR on a real screen is verified at iron G6.
Here we read the VGA text buffer (0xB8000) through the QEMU
monitor instead: disk_error ends in cli/hlt, so on the negative
leg nothing overwrites the screen and the text is stable. The
positive leg's kernel repaints VGA, so banner assertions are only
made on the halted negative leg.
"""
import hashlib
import os
import re
import socket
import subprocess
import sys
import time

# ---- self-describing log: hash the inputs BEFORE running them ----
# Any transcript quoting "Passed: N/N" must carry proof of WHICH
# bytes produced it; see tests/test_g6_chain.py for the long-form
# rationale.  Duplicated rather than factored into a shared helper
# on purpose: a suite's provenance must not depend on another file
# being importable, or the one failure mode it exists to survive
# (wrong/missing code) is the one that suppresses it.
#
# The BINARIES are declared inputs here, not just this file.  For
# most suites build/* is output; for this one vbr.bin IS the code
# under test -- a boot sector -- and kernel.bin/bmforth.img carry
# the A/B claim asserted a few lines below ("proven layout with
# only the loader swapped").  A log naming only the harness would
# be silent about every byte that actually ran on the CPU.
_prov_unreadable = []
for _label, _p in (('harness', os.path.abspath(__file__)),
                   ('vbr.bin', 'build/vbr.bin'),
                   ('kernel.bin', 'build/kernel.bin'),
                   ('bmforth.img', 'build/bmforth.img')):
    try:
        with open(_p, 'rb') as _f:
            _h = hashlib.sha256(_f.read()).hexdigest()
    except OSError as _e:
        _h = '<UNREADABLE>'
        _prov_unreadable.append(f'{_label} ({_p}): {_e}')
    print(f'input sha256 {_h}  {_label}')

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4508
MON_PORT = PORT + 1

with open('build/vbr.bin', 'rb') as f:
    vbr = bytearray(f.read())
with open('build/kernel.bin', 'rb') as f:
    kernel = f.read()

# The A/B claim ("proven layout with only the loader swapped") holds
# only if this kernel.bin IS the kernel the proven image boots.
# bmforth.img = boot.bin + kernel.bin by construction; assert it so a
# half-rebuilt tree cannot smoke-test a stale kernel.
with open('build/bmforth.img', 'rb') as f:
    proven = f.read()
if proven[512:512 + len(kernel)] != kernel:
    print('FAIL: kernel.bin is not the kernel inside bmforth.img '
          '(stale build?)')
    sys.exit(1)

# Derive the DAP LBA offset from the artifact (same pattern as
# test_install.py Test 46 -- never hardcoded).
dap_re = re.compile(
    b'\x10\x00..\x00\x7e\x00\x00'
    b'\xef\xbe\xad\xde\x00\x00\x00\x00', re.DOTALL)
hits = [m.start() for m in dap_re.finditer(bytes(vbr))]
if len(hits) != 1:
    print(f'FAIL: sentinel DAP hits = {hits}')
    sys.exit(1)
LBA_OFF = hits[0] + 8

PASS = FAIL = 0


def check(name, ok, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {name}')
    else:
        FAIL += 1
        print(f'  FAIL: {name}' + (f' -- {detail}' if detail else ''))


# COUNTED (+1 to N), not a bare raise.  Declared at the top,
# ASSERTED here, because check() does not exist until now -- an
# unreadable input must produce a parseable FAIL plus a
# "Passed: N/M" line.  A traceback gives a scraper nothing, which
# is indistinguishable from "never ran".  (The opens above would
# raise first today; this stays so that adding a declared input
# which is NOT opened cannot go unchecked.)
check('all declared inputs readable', not _prov_unreadable,
      '; '.join(_prov_unreadable))


def drain(s, out):
    try:
        while True:
            d = s.recv(4096)
            if not d:
                break
            out += d
    except Exception:
        pass
    return out


def read_vga_text():
    """Dump the full 25-row VGA text screen via the QEMU monitor.

    Full screen, not just the top rows: SeaBIOS's banner and boot
    messages occupy the top, and the VBR's int 0x10 teletype
    output continues at whatever row the firmware left the cursor
    on -- observed several rows down, after 'Booting from Hard
    Disk...'.

    Crash-forensics use only (ruling: monitor is not a state
    oracle for live runs). Parse is address-anchored per line:
    HMP over TCP echoes the command (which itself contains
    '0xb8000' -- a spurious 0x.. match that would flip the
    char/attr parity of a naive [::2]), so only lines shaped
    '<hex-addr>: 0x.. 0x..' contribute, and only their RHS.
    Cells are char,attr pairs; text is every second byte.
    """
    try:
        m = socket.socket()
        m.settimeout(5)
        m.connect(('127.0.0.1', MON_PORT))
        time.sleep(0.5)
        drain(m, b'')                      # eat the (qemu) banner
        m.sendall(b'xp /4000bx 0xb8000\n')   # 25 rows x 80 cells x 2
        time.sleep(2)
        raw = drain(m, b'').decode('ascii', errors='replace')
        m.close()
    except Exception as e:
        return f'<monitor unreachable: {e}>'
    cells = []
    for line in raw.splitlines():
        addr, sep, rest = line.partition(':')
        if not sep or not re.fullmatch(
                r'0x0*[0-9a-f]+|[0-9a-f]+', addr.strip()):
            continue
        cells += re.findall(r'0x([0-9a-f]{2})', rest)
    return bytes(int(c, 16) for c in cells[::2]).decode(
        'ascii', errors='replace')


def boot_capture(image, seconds, want_vga=False):
    """Boot image as hd; return (serial_output, vga_text)."""
    subprocess.run(['pkill', '-9', '-f', f'[q]emu.*{PORT}'],
                   capture_output=True)
    time.sleep(1)
    subprocess.run(
        ['qemu-system-i386', '-drive',
         f'file={image},format=raw',
         '-serial', f'tcp::{PORT},server=on,wait=off',
         '-monitor', f'tcp:127.0.0.1:{MON_PORT},server=on,wait=off',
         '-display', 'none', '-daemonize'], check=True)
    time.sleep(2)
    s = socket.socket()
    s.settimeout(10)
    for _ in range(20):
        try:
            s.connect(('127.0.0.1', PORT))
            break
        except OSError:
            time.sleep(0.5)
    else:
        return '', ''
    time.sleep(seconds)
    s.settimeout(1)
    out = drain(s, b'')
    # Prompt liveness: only meaningful for the positive leg.
    try:
        s.sendall(b'7 6 * .\r')
        time.sleep(1.5)
        out = drain(s, out)
    except Exception:
        pass
    s.close()
    vga = read_vga_text() if want_vga else ''
    subprocess.run(['pkill', '-9', '-f', f'[q]emu.*{PORT}'],
                   capture_output=True)
    return out.decode('ascii', errors='replace'), vga


print('\nVBR smoke 1: baked variant boots the kernel')
baked = bytearray(vbr)
baked[LBA_OFF:LBA_OFF + 4] = (1).to_bytes(4, 'little')
with open('build/vbr-smoke.img', 'wb') as f:
    f.write(bytes(baked) + kernel)
out, _ = boot_capture('build/vbr-smoke.img', 8)
check('kernel reached ok prompt', 'ok' in out, out[-160:])
check('interpreter alive (7 6 * = 42)', '42' in out, out[-160:])
smoke1_saw_ok = 'ok' in out

print('\nVBR smoke 2: UNBAKED template dies loudly (sentinel)')
with open('build/vbr-unbaked.img', 'wb') as f:
    f.write(bytes(vbr) + kernel)
out, vga = boot_capture('build/vbr-unbaked.img', 6, want_vga=True)
check('DISK ERR on VGA (halted screen, via monitor)',
      'DISK ERR' in vga, vga[:200])
check('variant banner on VGA (right loader ran)',
      'BMForth VBR' in vga, vga[:200])
# De-alias: same harness, same port, only the baked LBA differs.
# Gating on smoke 1 makes "no ok" attributable to the sentinel,
# not to a wedged QEMU that never delivers serial at all.
check('unbaked never reaches ok (gated on smoke 1 seeing ok)',
      smoke1_saw_ok and 'ok' not in out, out[-160:])

# Standard summary format: the suite lineage headline is the sum of
# 'Passed: X/Y' lines, so this suite must print one to be counted.
print(f'\nPassed: {PASS}/{PASS + FAIL}')
sys.exit(1 if FAIL else 0)
