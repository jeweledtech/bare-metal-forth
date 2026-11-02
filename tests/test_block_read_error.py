#!/usr/bin/env python3
"""Kernel BLOCK on a failed ATA read: an error, never the old buffer
(private TASK_KERNEL_BLOCK_READ_ERROR; public
docs/finding-kernel-block-read-error-2026-10-31.md).

BLOCK's ATA path jumped to .read_error on a failed sector read and pushed
the buffer address anyway, with no message: the caller got whatever the
buffer held before.  LOAD, --> and LIST had their own copies of the read,
which never tested the error and marked the buffer valid anyway, so a
failed read was cached as a good block.  The fix is one read routine for
all four (blk_read): "BLOCK READ FAIL <n>", ABORT's route, the buffer
valid only after a good read.

One boot, floppy + IDE scratch copies of the combined image, as
test-blk-evict.  BAD is a block past the IDE copy's end, so the drive
refuses the read (ERR); both are derived from the image and forth.asm.

  C0  (fatal control) BAD lies past the disk's end, the copy's last block
      (NBLK-1, written by this script on the copy only) holds -->, NBLK
      lies past the end, and 1 BLOCK reads block 1's first and last bytes
      as on disk: the ATA path works.
  E1  BAD BLOCK DEPTH . -- the message, and no number after it.
  E2  DEPTH . -- 0: no address left.
  E3  a definition calling BAD BLOCK stops there (7 6 * . not run).
  E4  BAD LOAD -- the message, nothing interpreted; BLK and DEPTH 0.
  E5  BAD BLOCK again -- the message again (the buffer was not kept valid).
  E7  NBLK-1 LOAD chains with --> into NBLK: the message for NBLK,
      nothing interpreted.
  E8  BAD LIST -- the message, and no listed lines.
  E6  after all of it, 1 BLOCK C@ . DEPTH . -- block 1's first byte, 0.

Before E6 the script sends two lines that are procedure, not scored
(amendment 1): ABORT and ONLY FORTH DEFINITIONS DECIMAL.
"""
import hashlib
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qemu_pid  # noqa: E402
import serial as ser  # noqa: E402

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4407
COMBINED = sys.argv[2] if len(sys.argv) > 2 else 'build/combined.img'
D = os.path.join('build', 'test-block-read-error.d')
os.makedirs(D, exist_ok=True)
FLOPPY = os.path.join(D, 'floppy.img')
IDE = os.path.join(D, 'ide.img')
ERRF = os.path.join(D, 'qemu.err')
ASM = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   '..', 'src', 'kernel', 'forth.asm')

src = open(ASM).read()


def equ(name):
    m = re.search(rf'^{name}\s+equ\s+(0x)?([0-9A-Fa-f]+)', src, re.M)
    if not m:
        print(f'cannot derive {name} from forth.asm', flush=True)
        sys.exit(2)
    return int(m.group(2), 16 if m.group(1) else 10)


BSIZE = equ('BLOCK_SIZE')
SECTOR = equ('BOOT_SECTOR_SIZE')
HEADER = SECTOR + equ('KERNEL_PADDED_SIZE')
NBLK = (os.path.getsize(COMBINED) - HEADER) // BSIZE
BAD = NBLK + 100
MSG = f'BLOCK READ FAIL {BAD}'
LAST = NBLK - 1
MSG7 = f'BLOCK READ FAIL {NBLK}'
TOTAL = 9

failures = []
checks = 0


def check(label, cond, detail='', fatal=False):
    global checks
    checks += 1
    print(f'[{"PASS" if cond else "FAIL"}] {label} {detail}', flush=True)
    if not cond:
        failures.append(label)
        if fatal:
            print('FATAL control failed -- run VOID, not red', flush=True)
            sys.exit(2)


def nums(text):
    return re.findall(r'-?\d+', text)


shutil.copyfile(COMBINED, FLOPPY)
shutil.copyfile(COMBINED, IDE)
with open(IDE, 'r+b') as f:                 # E7's chain: the copy's last block is -->
    f.seek(HEADER + LAST * BSIZE)
    f.write(b'-->'.ljust(BSIZE, b' '))
disk = open(IDE, 'rb').read()
B1 = disk[HEADER + BSIZE: HEADER + 2 * BSIZE]
for p in (COMBINED, ASM, os.path.abspath(__file__)):
    print(f'input sha256 {hashlib.sha256(open(p, "rb").read()).hexdigest()}'
          f'  {p}', flush=True)
print(f'NBLK {NBLK}, BAD {BAD} (first LBA {HEADER // SECTOR + 2 * BAD}, '
      f'disk {len(disk) // SECTOR} sectors)', flush=True)

PF = qemu_pid.pidfile('block-read-error')
proc = subprocess.Popen([
    'qemu-system-i386',
    '-drive', f'file={FLOPPY},format=raw,if=floppy',
    '-drive', f'file={IDE},format=raw,if=ide,index=1',
    '-serial', f'tcp:127.0.0.1:{PORT},server=on,wait=off',
    '-display', 'none', '-pidfile', PF,
], stdout=subprocess.DEVNULL, stderr=open(ERRF, 'w'))
qemu_pid.wait_started(proc, PF, PORT, 'block-read-error', ERRF)

try:
    s = ser.connect_and_sync(PORT, budget=60)

    def send(cmd, budget=30):
        rep, how = ser.send_until_prompt(s, cmd, budget=budget)
        body = rep.split('\r\n', 1)[1] if '\r\n' in rep else ''
        print(f'>>> {cmd}\n{body.strip()}', flush=True)
        if how != 'prompt':
            print(f'(reply ended by {how})', flush=True)
        return body

    b = send('DECIMAL 1 BLOCK DUP C@ . 1023 + C@ .')
    check(f'C0 BAD {BAD} and NBLK {NBLK} lie past the disk ({len(disk) // SECTOR} sectors), '
          f'block {LAST} on the copy holds -->, and 1 BLOCK reads block 1 as on disk '
          f'({B1[0]} {B1[-1]})',
          HEADER // SECTOR + 2 * BAD >= len(disk) // SECTOR
          and HEADER // SECTOR + 2 * NBLK >= len(disk) // SECTOR
          and disk[HEADER + LAST * BSIZE:][:4] == b'--> '
          and nums(b)[:2] == [str(B1[0]), str(B1[-1])], f'({b.strip()!r})', fatal=True)

    b = send(f'{BAD} BLOCK DEPTH .')
    check(f'E1 {BAD} BLOCK: "{MSG}", and no number after it (the line\'s DEPTH . not run)',
          MSG in b and not nums(b.replace(MSG, '')), f'({b.strip()!r})')

    b = send('DEPTH .')
    check('E2 DEPTH 0: no address left', nums(b) == ['0'], f'({b.strip()!r})')

    send(f': T-BRE {BAD} BLOCK DROP 7 6 * . ;')
    b = send('T-BRE')
    check('E3 a definition calling BLOCK stops there: the message, not 42',
          MSG in b and '42' not in b, f'({b.strip()!r})')

    b = send(f'{BAD} LOAD')
    b2 = send('BLK @ . DEPTH .')
    check('E4 LOAD: the message, nothing interpreted (no "?" line); BLK 0, DEPTH 0',
          MSG in b and ' ?' not in b and nums(b2) == ['0', '0'],
          f'({b.strip()!r}; {b2.strip()!r})')

    b = send(f'{BAD} BLOCK DROP')
    check('E5 a second BLOCK reads again: the message again', MSG in b, f'({b.strip()!r})')

    b = send(f'{LAST} LOAD')
    check(f'E7 {LAST} LOAD chains with --> into {NBLK}: "{MSG7}", nothing interpreted (no "?" line)',
          MSG7 in b and ' ?' not in b, f'({b.strip()!r})')

    b = send(f'{BAD} LIST')
    listed = re.findall(r'(?m)^\s*(?:1[0-5]|\d) ?: ', b)   # LIST: '<n>: ' (forth.asm LIST)
    check(f'E8 {BAD} LIST: the message, and no listed lines',
          MSG in b and not listed, f'({len(listed)} listed lines; {b.strip()[:120]!r})')

    # Procedure, not scored (amendment 1): whatever the lines above left (a
    # stack item, a search order or BASE from an interpreted buffer) does
    # not reach E6.
    send('ABORT')
    send('ONLY FORTH DEFINITIONS DECIMAL')
    b = send('1 BLOCK C@ . DEPTH .')
    check(f'E6 afterwards 1 BLOCK reads block 1 ({B1[0]}), DEPTH 0',
          nums(b) == [str(B1[0]), '0'], f'({b.strip()!r})')
finally:
    try:
        s.close()
    except NameError:
        pass
    qemu_pid.kill_pidfile(PF)
    proc.wait(timeout=10)

print(f'Passed: {checks - len(failures)}/{TOTAL}', flush=True)
sys.exit(0 if not failures and checks == TOTAL else 1)
