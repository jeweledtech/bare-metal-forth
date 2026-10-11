#!/usr/bin/env python3
"""Block-cache eviction gate: the LRU picks the least recently used slot,
and an eviction flush keeps the victim's slot index, refused or not.

Two defects in blk_find_buffer (forth.asm, Block Buffer Manager), both on
record before they were seen at run time (TASK_BLK_EVICT_FIX.md §0):
  K1  the LRU scan starts from 0xFFFFFFFF and compares signed (jge), so
      every age reads as "not older" and the victim is always slot 0.
  K2  the eviction path saves EDX but not EAX across blk_flush_one; EAX
      holds the victim index.  After a refused flush EAX is whatever the
      failure message left (0x720 once the screen has scrolled):
      BLK_BUF_CUR = 0x720, the caller's data goes to 0x1F0200, and the
      new block is never written, with no message.  After a successful
      flush EAX is the ior, 0, which K1 makes accidentally right.

One boot, floppy + IDE scratch copies of the combined image.  A fixture
writer (a colon definition through BLK-WRITER!) records every call as
(blk#, first byte of the buffer) and refuses one chosen block.  Every
block is filled with its own pattern byte PAT(b), so a write or a slot
whose byte is not its block's pattern is data in the wrong place.

  L   LRU: four clean blocks, three touched again, a fifth requested:
      the untouched slot is replaced.
  S   succeeding writer (fixture, ior 0): four dirty blocks, the first
      touched again, a fifth requested, so the eviction flush succeeds
      on a victim that is not slot 0 once the LRU works.
  R   refusing writer: sixteen blocks, each BUFFER FILL UPDATE
      SAVE-BUFFERS; the fixture refuses one that lands in slot 0.
  A   the real writer, (BLK-WRITE-ATA), on the IDE scratch copy: the S
      sequence, then SAVE-BUFFERS; the host reads the disk afterwards.

The checks assert the fixed behaviour.  Predictions for today's kernel
and for an experiment kernel with only K1 fixed are written before the
runs, in the evidence directory named by the task doc, not here.
"""
import hashlib
import os
import re
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qemu_pid  # noqa: E402
import serial as ser  # noqa: E402

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4466
COMBINED = sys.argv[2] if len(sys.argv) > 2 else 'build/combined.img'
D = os.path.join('build', 'test-blk-evict.d')
os.makedirs(D, exist_ok=True)
FLOPPY = os.path.join(D, 'floppy.img')
IDE = os.path.join(D, 'ide.img')
ERRF = os.path.join(D, 'qemu.err')
ASM = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   '..', 'src', 'kernel', 'forth.asm')

# Addresses and sizes derived from the kernel source, not typed.
src = open(ASM).read()


def equ(name, base=16):
    m = re.search(rf'^{name}\s+equ\s+(0x)?([0-9A-Fa-f]+)', src, re.M)
    if not m:
        print(f'cannot derive {name} from forth.asm', flush=True)
        sys.exit(2)
    return int(m.group(2), 16 if m.group(1) else 10)


HDRS = equ('BLK_BUF_HEADERS')
CUR = equ('BLK_BUF_CUR')
DATA = equ('BLK_BUF_DATA')
HSIZE = equ('BLK_HEADER_SIZE')
NBUF = equ('BLK_NUM_BUFFERS')
BSIZE = equ('BLOCK_SIZE')
HEADER = equ('BOOT_SECTOR_SIZE') + equ('KERNEL_PADDED_SIZE')
# Where K2 put the caller's data at run time (2026-10-11 trace:
# BLK_BUF_CUR = 0x720, the VGA blank-cell word scroll_screen leaves in AX).
STRAY = DATA + 0x720 * BSIZE
SENTINEL = 0x5AA5C33C


def PAT(b):
    return 0x30 + (b - 2000)


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


shutil.copyfile(COMBINED, FLOPPY)
shutil.copyfile(COMBINED, IDE)
IDE_BEFORE = open(IDE, 'rb').read()
for p in (COMBINED, ASM, os.path.abspath(__file__)):
    print(f'input sha256 {hashlib.sha256(open(p, "rb").read()).hexdigest()}'
          f'  {p}', flush=True)

PF = qemu_pid.pidfile('blk-evict')
proc = subprocess.Popen([
    'qemu-system-i386',
    '-drive', f'file={FLOPPY},format=raw,if=floppy',
    '-drive', f'file={IDE},format=raw,if=ide,index=1',
    '-serial', f'tcp:127.0.0.1:{PORT},server=on,wait=off',
    '-display', 'none', '-pidfile', PF,
], stdout=subprocess.DEVNULL, stderr=open(ERRF, 'w'))
qemu_pid.wait_started(proc, PF, PORT, 'blk-evict', ERRF)

try:
    s = ser.connect_and_sync(PORT, budget=60)

    def send(cmd, budget=20):
        rep, how = ser.send_until_prompt(s, cmd, budget=budget)
        body = rep.split('\r\n', 1)[1] if '\r\n' in rep else ''
        print(f'>>> {cmd}\n{body.strip()}', flush=True)
        if how != 'prompt':
            print(f'  (read ended by {how})', flush=True)
        return body

    def nums(body, base=10):
        body = body.replace('ok', ' ')
        return [int(t, base) for t in re.findall(r'-?[0-9A-Fa-f]+', body)]

    def headers():
        """[(block#, flags)] per slot, then BLK_BUF_CUR."""
        cells = ' '.join(f'{HDRS + i * HSIZE:X} @ . {HDRS + i * HSIZE + 4:X} @ .'
                         for i in range(NBUF))
        v = nums(send(f'HEX {cells} {CUR:X} @ . DECIMAL'), 16)
        v = [x - (1 << 32) if x >= 1 << 31 else x for x in v]
        return [(v[2 * i], v[2 * i + 1]) for i in range(NBUF)], v[2 * NBUF]

    def slot_bytes():
        cells = ' '.join(f'{DATA + i * BSIZE:X} C@ .' for i in range(NBUF))
        return nums(send(f'HEX {cells} DECIMAL'), 16)

    def wlog():
        v = nums(send('DECIMAL WDUMP'))
        return list(zip(v[0::2], v[1::2]))

    def fills(b):
        return f'DECIMAL {b} BUFFER {BSIZE} {PAT(b)} FILL UPDATE'

    # --- Fixture writer ---
    # No ( ) comments: typed over serial, `(` wedges the interpreter.
    # WREC ( addr blk -- )   FIXW ( addr blk -- ior )
    for line in (
        'DECIMAL VARIABLE REFUSE -1 REFUSE !',
        'VARIABLE WN 0 WN !',
        'CREATE WLOG 64 8 * ALLOT',
        ': WREC WN @ 8 * WLOG + >R R@ ! C@ R> 4 + ! 1 WN +! ;',
        ': FIXW 2DUP WREC NIP REFUSE @ = IF 1 ELSE 0 THEN ;',
        ': WDUMP WN @ DUP 0> IF 0 DO I 8 * WLOG + DUP @ . 4 + @ . LOOP ELSE DROP THEN ;',
    ):
        send(line)
    check('C1 fixture defined, DEPTH 0', nums(send('DEPTH .')) == [0], fatal=True)
    r = nums(send('DECIMAL 2099 BUFFER 2099 FIXW . 2099 REFUSE ! 2099 BUFFER 2099 FIXW . -1 REFUSE !'))
    check('C2 fixture: ior 0 when not refused, 1 when refused', r == [0, 1],
          f'(got {r})', fatal=True)
    send('0 WN ! EMPTY-BUFFERS')

    # --- L: LRU ---
    for b in (2000, 2001, 2002, 2003, 2000, 2001, 2003, 2004):
        send(f'DECIMAL {b} BLOCK DROP')
    h, cur = headers()
    blocks = [b for b, _ in h]
    check('L1 LRU: the untouched slot (2002) is replaced by 2004',
          blocks == [2000, 2001, 2004, 2003], f'(slots {blocks})')

    # --- S: eviction whose flush succeeds (fixture writer, ior 0) ---
    send("' FIXW BLK-WRITER! EMPTY-BUFFERS 0 WN !")
    for b in (2005, 2006, 2007, 2008):
        send(fills(b))
    send('DECIMAL 2005 BLOCK DROP')
    send(fills(2009))
    h, cur = headers()
    sb = slot_bytes()
    ev = wlog()
    check('S1 BLK_BUF_CUR in 0-3 after a successful eviction', 0 <= cur < NBUF,
          f'(got {cur:#x})')
    bad = [(i, b, sb[i]) for i, (b, f) in enumerate(h) if f & 1 and sb[i] != PAT(b)]
    check("S2 every valid slot holds its own block's bytes", not bad,
          f'(slot, block, byte) wrong: {bad}')
    check('S3 the eviction wrote one block, with its own bytes',
          len(ev) == 1 and ev[0][1] == PAT(ev[0][0]), f'(writes {ev})')
    send('SAVE-BUFFERS')
    ws = wlog()
    want = sorted((b, PAT(b)) for b in range(2005, 2010))
    check('S4 after SAVE-BUFFERS, 2005-2009 each written once with its own bytes',
          sorted(ws) == want, f'(writes {ws})')

    # --- R: refusing writer ---
    send(f'EMPTY-BUFFERS 0 WN ! DECIMAL 2014 REFUSE ! HEX {SENTINEL:X} {STRAY:X} ! DECIMAL')
    curs, sents, fails = [], [], []
    for b in range(2010, 2026):
        body = send(fills(b) + ' SAVE-BUFFERS')
        fails += [int(x) for x in re.findall(r'BLOCK WRITE FAIL (\d+)', body)]
        v = nums(send(f'HEX {CUR:X} @ . {STRAY:X} @ . DECIMAL'), 16)
        curs.append(v[0])
        sents.append(v[1])
    ws = wlog()
    check('R1 BLK_BUF_CUR in 0-3 after every step',
          all(0 <= c < NBUF for c in curs), f'(got {[hex(c) for c in curs]})')
    check(f'R2 sentinel at {STRAY:#x} unchanged after every step',
          all(x == SENTINEL for x in sents),
          f'(got {sorted(set(hex(x) for x in sents))})')
    got = {}
    for b, byte in ws:
        got.setdefault(b, []).append(byte)
    others = {b: got.get(b, []) for b in range(2010, 2026) if b != 2014}
    bad = {b: v for b, v in others.items() if v != [PAT(b)]}
    check('R3 every block but 2014 reaches the writer exactly once, own bytes',
          not bad, f'(wrong: {bad})')
    # 2014 lands in slot 0 and stays dirty: refused by the SAVE-BUFFERS of
    # its own step and of the three steps that fill slots 1-3, then once
    # more when 2018 evicts it (slot 0 is then least recently used): 5.
    check('R4 2014 refused 5 times, named 5 times, nothing else named',
          got.get(2014) == [PAT(2014)] * 5 and fails == [2014] * 5,
          f'(writer saw 2014 {len(got.get(2014, []))}x; FAIL lines {fails})')
    check('R5 DEPTH 0', nums(send('DEPTH .')) == [0])

    # --- A: the real ATA writer, eviction that succeeds ---
    send("' (BLK-WRITE-ATA) BLK-WRITER! EMPTY-BUFFERS")
    for b in (2030, 2031, 2032, 2033):
        send(fills(b))
    send('DECIMAL 2030 BLOCK DROP')
    send(fills(2034))
    h, cur = headers()
    sb = slot_bytes()
    check('A1 BLK_BUF_CUR in 0-3 after an ATA eviction', 0 <= cur < NBUF,
          f'(got {cur:#x})')
    bad = [(i, b, sb[i]) for i, (b, f) in enumerate(h) if f & 1 and sb[i] != PAT(b)]
    check("A2 every valid slot holds its own block's bytes", not bad,
          f'(slot, block, byte) wrong: {bad}')
    send('SAVE-BUFFERS')
    check('E1 DEPTH 0 at the end', nums(send('DEPTH .')) == [0])
    s.close()
finally:
    qemu_pid.kill_pidfile(PF)

time.sleep(0.5)
after = open(IDE, 'rb').read()
bad = []
for b in range(2030, 2035):
    blk = after[HEADER + b * BSIZE:HEADER + (b + 1) * BSIZE]
    if blk != bytes([PAT(b)]) * BSIZE:
        bad.append((b, sorted(set(blk))[:4]))
check('A3 on disk, blocks 2030-2034 each hold their own bytes', not bad,
      f'(wrong: {bad})')
lo, hi = HEADER + 2030 * BSIZE, HEADER + 2035 * BSIZE
check('A4 the rest of the IDE copy is unchanged',
      after[:lo] == IDE_BEFORE[:lo] and after[hi:] == IDE_BEFORE[hi:])

print(f'Passed: {checks - len(failures)}/{checks}', flush=True)
sys.exit(0 if not failures else 1)
