#!/usr/bin/env python3
"""Block-cache reload gate: a cache HIT must not corrupt a neighbour.

Bug #34 (found 2026-09-05, HP iron second-THRU spew): LOAD's
.have_data path stamps `mov byte [edi + BLOCK_SIZE], 0` on EVERY
load, hit or miss (forth.asm, label LOAD; also `-->`).  For buffer
slots 0..2 that address is byte 0 of the NEXT slot's cached data --
the NUL guard at BLK_BUF_GUARD covers slot 3 only.  The neighbour's
header stays VALID, so the next request for that block hits cache
and the parser terminates at byte 0: the block reloads as a silent
no-op.  On the HP this skipped the vocab-preamble block of a THRU
reload and produced 14 unresolved-word errors (see
docs/ mechanism report; probes /tmp/thru2_*.log 2026-09-05).

This suite stages its OWN four blocks (1900-1903, past the ~1740
catalog ceiling) into scratch copies of the combined image, so it
does not depend on desk-staged demo content, and establishes a cold
cache with EMPTY-BUFFERS so slot assignment is the free-scan order
0,1,2,3 -- NOT the LRU path.  The gate therefore stays valid after
the (held) LRU fix lands: it exercises only the stamp.

PRE-REGISTERED (written before the red run):
  R1  after EMPTY-BUFFERS + loads 1900..1903, slot-3 byte 0 == '1'
      (0x31, first byte of block 1903's text).  Holds red AND green:
      on the miss path the disk fill overwrites the stamp.
  R2  `1902 LOAD` (cache hit) leaves slot-3 byte 0 == '1'.
      RED today: the hit stamps it to 0.  GREEN after the fix.
  R3  `1903 LOAD` after that increments BCOUNT (2 total loads).
      RED today: 1 (silent no-op).  GREEN: 2.
  R4  DEPTH == 0 and no error signatures anywhere: the staged
      blocks are balanced, and a load must not eat stack.
  R5/R6 are CHARACTERIZATION pins, not regression tests: they pass
  on BOTH the pre-fix and fixed kernels (verified on the stashed
  pre-fix tree, 2026-09-06 red run).  They pin word_'s existing
  behavior verbatim so the bound fix -- and any future refactor
  near .end_word -- provably changes nothing on these paths.  Do
  not read them as proving the Bug #34 fix; R2/R3 do that.
  R5  (characterization pin, >31-char path) a 40-char token parses
      as EXACTLY two error signatures: the 31-char truncation
      chars[0:31] ('AAAAAAAAAABBBBBBBBBBCCCCCCCCCCZ') and the tail
      chars[30:40] ('ZYXWVUTSRQ') -- the shared 'Z' IS the
      max-length quirk (.end_word's dec esi backs onto the last
      STORED char, so the tail re-parse starts one char early).
      Pins the explicit `jmp .end_word` restored after the new
      .word_at_bound label silently captured this fall-through;
      that defect was caught by review, not by any test.
  R6  (characterization pin, tight-bound direction) a token whose
      LAST char sits at block byte 1023 with no trailing whitespace
      errors as its FULL name ('ZZZENDBYTE').  R1 already catches a
      bound one byte LOOSE (slot-2 byte 1024 IS slot-3 byte 0);
      this catches one byte TIGHT ('ZZZENDBYT' -- a quiet one-char
      truncation that types ? and lets the load continue wrong).
Controls (fatal): ZZZNEVERWAS error-signature control; found-word
control; R1 doubles as an instrument control (if R1 fails the
staging or slot model is wrong and R2/R3 are void, not red).
"""
import hashlib
import os
import re
import shutil
import socket
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kernel_constants import BLOCK_SIZE, BLK_BUF_DATA, BLK_NUM_BUFFERS

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4470
COMBINED = sys.argv[2] if len(sys.argv) > 2 else 'build/combined.img'
BUILD = os.path.dirname(COMBINED) or 'build'
SCRATCH = os.path.join(BUILD, 'test-blkreload.img')
SCRATCH_IDE = os.path.join(BUILD, 'test-blkreload-ide.img')
ASM = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   '..', 'src', 'kernel', 'forth.asm')

ERR_RE = re.compile(r'(\S+) \? \r')
SLOT3_BYTE0 = BLK_BUF_DATA + 3 * BLOCK_SIZE   # 0x28E00 today, derived

failures = []
checks = 0


def check(label, cond, detail='', fatal=False):
    global checks
    checks += 1
    tag = 'PASS' if cond else 'FAIL'
    print(f'[{tag}] {label} {detail}', flush=True)
    if not cond:
        failures.append(label)
        if fatal:
            print('FATAL control failed -- run VOID, not red', flush=True)
            sys.exit(2)


def block_text(lines):
    """16 x 64 space-padded, no CR/LF (word_ treats CR/LF as
    end-of-line and would end the block early)."""
    out = b''
    for i in range(16):
        line = lines[i] if i < len(lines) else ''
        assert len(line) <= 64 and '\r' not in line and '\n' not in line
        out += line.encode('ascii').ljust(64)
    assert len(out) == BLOCK_SIZE
    return out


LONGWORD = 'AAAAAAAAAABBBBBBBBBBCCCCCCCCCC' + 'ZYXWVUTSRQ'   # 40 chars
assert len(LONGWORD) == 40 and LONGWORD[30] == 'Z'
R5_EXPECT = {LONGWORD[:31]: 1, LONGWORD[30:]: 1}   # derived, not typed

BLOCKS = {
    1900: block_text(['( BUG34 BLOCK A )']),
    1901: block_text(['( BUG34 BLOCK B )']),
    1902: block_text(['( BUG34 BLOCK C )']),
    1903: block_text(['1 BCOUNT +!']),     # byte 0 = '1' = 0x31
    1904: block_text(['( BUG34 LONGWORD ) ' + LONGWORD]),
    # Line 15 exactly 64 chars, token flush right: its last char is
    # block byte 1023.  ljust in block_text is a no-op on it.
    1905: block_text(['( BUG34 TAILBYTE )'] + [''] * 14
                     + ['ZZZENDBYTE'.rjust(64)]),
}
assert BLOCKS[1903][0:1] == b'1'
assert BLOCKS[1905][1023:1024] == b'E'   # the byte under test

# Staging offset derived from the kernel source, not asserted:
# combined image = boot sector + padded kernel, blocks follow.
src = open(ASM).read()
kps = re.search(r'^KERNEL_PADDED_SIZE\s+equ\s+0x([0-9A-Fa-f]+)', src, re.M)
bss = re.search(r'^BOOT_SECTOR_SIZE\s+equ\s+(\d+)', src, re.M)
if not (kps and bss):
    print('cannot derive staging offset from forth.asm', flush=True)
    sys.exit(2)
HEADER = int(bss.group(1)) + int(kps.group(1), 16)

# --- Stage scratch images ---
shutil.copyfile(COMBINED, SCRATCH)
with open(SCRATCH, 'r+b') as f:
    for blk, data in sorted(BLOCKS.items()):
        f.seek(HEADER + blk * BLOCK_SIZE)
        f.write(data)
shutil.copyfile(SCRATCH, SCRATCH_IDE)

for path in (SCRATCH, SCRATCH_IDE):
    with open(path, 'rb') as f:
        print(f'input sha256 {hashlib.sha256(f.read()).hexdigest()}  {path}',
              flush=True)


def drain(s, cap=60, quiet=3):
    resp = b''
    start = last = time.time()
    s.settimeout(0.5)
    while time.time() - start < cap:
        try:
            d = s.recv(4096)
            if d:
                resp += d
                last = time.time()
                continue
        except socket.timeout:
            pass
        if time.time() - last >= quiet:
            break
    return resp.decode('ascii', errors='replace')


proc = subprocess.Popen([
    'qemu-system-i386',
    '-drive', f'file={SCRATCH},format=raw,if=floppy',
    '-drive', f'file={SCRATCH_IDE},format=raw,if=ide,index=1',
    '-serial', f'tcp::{PORT},server=on,wait=off',
    '-display', 'none',
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    time.sleep(2)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(10)
    s.connect(('127.0.0.1', PORT))
    drain(s, cap=30, quiet=4)

    def send(cmd, cap=60):
        s.sendall((cmd + '\r').encode())
        raw = drain(s, cap=cap)
        print(f'>>> {cmd}')
        print(raw.strip())
        print('-' * 60, flush=True)
        return raw

    def errs(raw):
        h = {}
        for name in ERR_RE.findall(raw):
            h[name] = h.get(name, 0) + 1
        return h

    def value(raw, cmd):
        toks = re.findall(r'\b[0-9A-F]+\b', raw.replace(cmd, '', 1))
        return toks[0] if toks else None

    # Instrument controls (fatal)
    r = send('ZZZNEVERWAS')
    check('never-existed control -> exactly one signature',
          errs(r) == {'ZZZNEVERWAS': 1}, f'(got {errs(r)})', fatal=True)
    r = send('DEPTH .')
    check('found control clean', not errs(r), fatal=True)

    send('VARIABLE BCOUNT')
    send('0 BCOUNT !')
    send('EMPTY-BUFFERS')          # cold cache: free-scan slot order
    total_errs = {}
    for blk in (1900, 1901, 1902, 1903):
        r = send(f'DECIMAL {blk} LOAD')
        for k, v in errs(r).items():
            total_errs[k] = total_errs.get(k, 0) + v
    check('staged blocks load without error signatures',
          not total_errs, f'(got {total_errs})')
    r = send('BCOUNT @ .')
    check('BCOUNT == 1 after first 1903 load',
          value(r, 'BCOUNT @ .') == '1')

    cmd = f'HEX {SLOT3_BYTE0:X} C@ . DECIMAL'
    r = send(cmd)
    check("R1: slot-3 byte 0 == '1' after cold loads (instrument)",
          value(r, cmd) == '31', f'(got {value(r, cmd)})', fatal=True)

    send('1902 LOAD')              # cache HIT -- the trigger
    r = send(cmd)
    check("R2: slot-3 byte 0 still '1' after 1902 cache hit",
          value(r, cmd) == '31', f'(got {value(r, cmd)})')

    r = send('1903 LOAD')
    check('R3a: 1903 reload has no error signatures', not errs(r))
    r = send('BCOUNT @ .')
    check('R3: BCOUNT == 2 (1903 reload was effective)',
          value(r, 'BCOUNT @ .') == '2',
          f'(got {value(r, "BCOUNT @ .")})')

    r = send('DEPTH .')
    check('R4: DEPTH == 0 after all loads',
          re.search(r'\b0\b\s+ok', r) is not None and not errs(r))

    # R5: >31-char token -- 31-char truncation + one-char-early tail
    r = send('DECIMAL 1904 LOAD')
    check('R5: 40-char token -> exactly the two pinned signatures',
          errs(r) == R5_EXPECT, f'(got {errs(r)}, want {R5_EXPECT})')

    # R6: meaningful char at byte 1023, no trailing whitespace
    r = send('DECIMAL 1905 LOAD')
    check("R6: byte-1023 token errors under its FULL name",
          errs(r) == {'ZZZENDBYTE': 1}, f'(got {errs(r)})')

    r = send('DEPTH .')
    check('R5/R6 leave DEPTH == 0',
          re.search(r'\b0\b\s+ok', r) is not None and not errs(r))
    s.close()
finally:
    proc.kill()
    proc.wait()

print('=' * 60)
print(f'Passed: {checks - len(failures)}/{checks}')
if failures:
    print(f'FAILURES: {len(failures)}')
    for f in failures:
        print(f'  - {f}')
    sys.exit(1)
print('ALL PASS')
