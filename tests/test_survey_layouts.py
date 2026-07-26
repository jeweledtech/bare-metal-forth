#!/usr/bin/env python3
"""DISK-SURVEY placement gate: adversarial GPT layouts.

Each layout is authored with sgdisk to target exactly one
defect in PARTITION-MAP's GPT scanner, then booted under
QEMU with ICH9-AHCI so the survey parses a real on-disk
table.

This is deliberately NOT tests/test_disk_survey.py, which
runs with no disk attached and only asserts the vocabulary
loads and prints "AHCI not init".  These four layouts
assert what the survey actually parsed.

Layouts and the repair each one gates:

  L1  two partitions with a gap between them
      -> SCAN-GPT-SEC must capture GPT +0x28 (Last LBA);
         PART-END must exist and be exact
  L2  twelve partitions
      -> the 8-entry PART-TBL cap must be raised
  L3  a single partition in GPT slot 25 (entry LBA 8)
      -> all 128 entries must be scanned, not sectors 2-5
  L4  partition starting past 2 TiB
      -> 64-bit LBAs must not be truncated to 32 bits, and
         a map that cannot represent one must report
         MAP-TRUSTED? false

Contract asserted (post-repair):
  PART-ENT      ( idx -- addr ) existing; stride widens
  PART-END      ( idx -- lba )  last LBA of entry idx
  MAP-TRUSTED?  ( -- flag )     TRUE only if every entry on
                                the disk was captured exactly

Two rules keep this gate honest, both learned from an
earlier draft that produced false passes:

  1. Expected LBAs are never hardcoded.  sgdisk silently
     realigns requested boundaries, so every expectation is
     read back out of the GPT that was actually written --
     the same bytes the survey will parse.
  2. The kernel prints "WORD ?" for an undefined word and
     then KEEPS EXECUTING the rest of the line, so a query
     on a not-yet-implemented contract word returns leftover
     stack junk.  val() rejects the "?" marker outright and
     parses the exact printed token.  Unable to determine a
     value is a failure, never a pass.

Requires: sgdisk, qemu-system-i386, build/combined.img.
"""
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time

PORT_BASE = int(sys.argv[1]) if len(sys.argv) > 1 else 4590
PROJECT = os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))
BUILD = os.path.join(PROJECT, 'build')
COMBINED = os.path.join(BUILD, 'combined.img')

PASS = FAIL = 0


def check(name, ok, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {name}')
    else:
        FAIL += 1
        print(f'  FAIL: {name}' +
              (f' -- {detail}' if detail else ''))


def need_tool(tool):
    if shutil.which(tool) is None:
        print(f'FAIL: required tool not found: {tool}')
        sys.exit(1)


need_tool('sgdisk')
need_tool('qemu-system-i386')
if not os.path.exists(COMBINED):
    print(f'FAIL: {COMBINED} missing -- run make first')
    sys.exit(1)


# ---------------------------------------------------------
# Disk authoring, and reading back the ground truth
# ---------------------------------------------------------

SECTOR = 512
ENTRY_SIZE = 128
ENTRY_LBA = 2
ENTRY_COUNT = 128


def make_disk(tmpdir, name, size_bytes, parts):
    """parts: list of (number, first_lba, last_lba).

    Returns (path, entries) where entries is what sgdisk
    ACTUALLY wrote -- it realigns boundaries without asking.
    """
    img = os.path.join(tmpdir, name + '.img')
    # Sparse: only the GPT headers, the entry array and the
    # backup at the far end are ever written.
    with open(img, 'wb') as f:
        f.truncate(size_bytes)
    subprocess.run(['sgdisk', '-Z', img],
                   capture_output=True, check=True)
    if not parts:
        # -Z leaves no GPT at all; -o writes a valid header
        # with an all-zero entry array.  We want an empty
        # map, not a missing one.
        subprocess.run(['sgdisk', '-o', img],
                       capture_output=True, check=True)
    for num, first, last in parts:
        subprocess.run(
            ['sgdisk', '-n', f'{num}:{first}:{last}',
             '-t', f'{num}:0700', img],
            capture_output=True, check=True)
    return img, read_gpt_entries(img)


def read_gpt_entries(img):
    """Parse the primary GPT entry array off the image.

    Returns a list of dicts in slot order, one per non-empty
    entry: slot (0-based), first, last, guid4.
    """
    with open(img, 'rb') as f:
        f.seek(ENTRY_LBA * SECTOR)
        raw = f.read(ENTRY_SIZE * ENTRY_COUNT)
    out = []
    for slot in range(ENTRY_COUNT):
        e = raw[slot * ENTRY_SIZE:(slot + 1) * ENTRY_SIZE]
        if e[0:16] == b'\x00' * 16:
            continue
        guid4, = struct.unpack_from('<I', e, 0x00)
        first, = struct.unpack_from('<Q', e, 0x20)
        last, = struct.unpack_from('<Q', e, 0x28)
        out.append({'slot': slot, 'first': first,
                    'last': last, 'guid4': guid4})
    return out


# ---------------------------------------------------------
# QEMU session
# ---------------------------------------------------------

USED_PORTS = []


class Session:
    def __init__(self, disk_img, port):
        self.port = port
        # Recorded before anything can fail, so the cleanup
        # in `finally` covers every port actually touched.
        # A fixed range() here would silently miss the next
        # layout someone adds.
        USED_PORTS.append(port)
        self.combined_ide = os.path.join(
            BUILD, f'combined-ide-survey-{port}.img')
        subprocess.run(
            ['pkill', '-9', '-f', f'[q]emu.*{port}'],
            capture_output=True)
        time.sleep(1)
        shutil.copyfile(COMBINED, self.combined_ide)
        cmd = [
            'qemu-system-i386',
            '-drive',
            f'file={COMBINED},format=raw,if=floppy',
            '-drive',
            f'file={self.combined_ide},format=raw,'
            f'if=ide,index=1',
            '-drive',
            f'file={disk_img},format=raw,if=none,id=sata0',
            '-device', 'ich9-ahci,id=ahci0',
            '-device', 'ide-hd,drive=sata0,bus=ahci0.0',
            '-serial', f'tcp::{port},server=on,wait=off',
            '-display', 'none',
            '-daemonize',
        ]
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode != 0:
            raise RuntimeError(
                f'QEMU launch failed: '
                f'{r.stderr.decode()[:200]}')
        time.sleep(3)
        self.s = socket.socket(socket.AF_INET,
                               socket.SOCK_STREAM)
        self.s.settimeout(10)
        for _ in range(20):
            try:
                self.s.connect(('127.0.0.1', port))
                break
            except (ConnectionRefusedError, OSError):
                time.sleep(0.5)
        else:
            raise RuntimeError('could not connect to QEMU')
        time.sleep(2)
        try:
            while True:
                self.s.recv(4096)
        except Exception:
            pass

    def send(self, cmd, wait=2.0):
        self.s.sendall((cmd + '\r').encode())
        time.sleep(wait)
        self.s.settimeout(3)
        resp = b''
        while True:
            try:
                d = self.s.recv(8192)
                if not d:
                    break
                resp += d
            except Exception:
                break
        return resp.decode('ascii', errors='replace')

    def clear_stack(self):
        # BEGIN..WHILE..REPEAT, not DO..LOOP: this kernel's
        # LOOP uses a simplified compare, so 0 0 DO still
        # runs the body once.
        self.send('BEGIN DEPTH WHILE DROP REPEAT', 1)

    def close(self):
        try:
            self.s.close()
        except Exception:
            pass
        subprocess.run(
            ['pkill', '-9', '-f', f'[q]emu.*{self.port}'],
            capture_output=True)
        try:
            os.remove(self.combined_ide)
        except OSError:
            pass


def survey(disk_img, port):
    """Boot, init AHCI, run PARTITION-MAP.

    Returns (session, map_output) or (None, reason).
    """
    sess = Session(disk_img, port)
    sess.send('USING AHCI', 2)
    r = sess.send('AHCI-INIT', 5)
    if 'AHCI ok' not in r:
        sess.close()
        return None, f'AHCI-INIT: {r.strip()[:80]!r}'
    sess.send('USING SURVEYOR', 2)
    out = sess.send('PARTITION-MAP', 8)
    return sess, out


def val(sess, expr, wait=1.0):
    """Evaluate expr in DECIMAL; return (value|None, raw).

    None means the value could not be determined -- either an
    undefined word (the kernel's "WORD ?" marker) or nothing
    printed.  Callers must treat None as failure; it is never
    allowed to satisfy an expected value.
    """
    sess.clear_stack()
    raw = sess.send(f'DECIMAL {expr} .', wait)
    sess.send('HEX', 0.3)
    # Drop the echoed input line before looking for either
    # the "?" marker or a value.  The echo repeats the
    # expression, and Forth word names may themselves end in
    # "?" (MAP-TRUSTED?, PART-BAD?) -- scanning the whole
    # response would read the name's own "?" as the kernel's
    # undefined-word marker and reject a correct answer.
    body = raw.split('\n', 1)[1] if '\n' in raw else raw
    if '?' in body:
        return None, raw
    nums = re.findall(r'-?\d+', body)
    return (int(nums[-1]) if nums else None), raw


def expect(sess, name, expr, want):
    v, raw = val(sess, expr)
    check(f'{name} = {want}', v is not None and v == want,
          f'got {v!r} from {raw.strip()[-90:]!r}')


# ---------------------------------------------------------
# Layouts
# ---------------------------------------------------------

MB = 1024 * 1024
TRUE, FALSE = -1, 0

tmpdir = tempfile.mkdtemp(prefix='survey-layouts-')
print('DISK-SURVEY placement gate')
print('=' * 50)

try:
    # -----------------------------------------------------
    # L1: extent ends -- two partitions with a gap
    # -----------------------------------------------------
    print('\nL1: extent ends (two partitions, gap between)')
    img, ents = make_disk(
        tmpdir, 'l1', 64 * MB,
        [(1, 2048, 10239), (2, 20480, 28671)])
    check('L1 authored 2 GPT entries', len(ents) == 2,
          repr(ents))
    p1, p2 = ents[0], ents[1]
    free = p2['first'] - p1['last'] - 1
    sess, out = survey(img, PORT_BASE)
    if sess is None:
        check('L1 boots and inits AHCI', False, out)
    else:
        check('L1 boots and inits AHCI', True)
        # Harness sanity: the survey must actually parse a
        # real table here.  If this fails the gate is not
        # reaching the code under test at all.
        check('L1 finds 2 partitions',
              '2 partitions found' in out,
              repr(out.strip()[-160:]))
        expect(sess, 'L1 P1 start (captured today)',
               '0 PART-ENT @', p1['first'])
        # The repair: GPT +0x28 must be captured.
        expect(sess, 'L1 P1 end', '0 PART-END', p1['last'])
        expect(sess, 'L1 P2 end', '1 PART-END', p2['last'])
        # Free sectors between the two extents.  This is the
        # exact expression FREE-EXTENT will compute, so the
        # test and the implementation share one definition
        # and the off-by-one cannot reappear unnoticed.
        expect(sess, 'L1 free sectors between P1 and P2',
               '1 PART-ENT @ 0 PART-END - 1-', free)
        expect(sess, 'L1 MAP-TRUSTED?', 'MAP-TRUSTED?', TRUE)
        sess.close()

    # -----------------------------------------------------
    # L2: 8-entry cap -- twelve partitions
    # -----------------------------------------------------
    print('\nL2: entry cap (twelve partitions)')
    spec = [(i, 2048 + (i - 1) * 2048,
             2048 + i * 2048 - 1) for i in range(1, 13)]
    img, ents = make_disk(tmpdir, 'l2', 64 * MB, spec)
    check('L2 authored 12 GPT entries', len(ents) == 12,
          repr(len(ents)))
    sess, out = survey(img, PORT_BASE + 1)
    if sess is None:
        check('L2 boots and inits AHCI', False, out)
    else:
        check('L2 boots and inits AHCI', True)
        check('L2 finds 12 partitions',
              '12 partitions found' in out,
              repr(out.strip()[-160:]))
        expect(sess, 'L2 PART-N', 'PART-N @', len(ents))
        # The 12th partition must be addressable, not just
        # counted.
        expect(sess, 'L2 P12 start', '11 PART-ENT @',
               ents[11]['first'])
        expect(sess, 'L2 P12 end', '11 PART-END',
               ents[11]['last'])
        expect(sess, 'L2 MAP-TRUSTED?', 'MAP-TRUSTED?', TRUE)
        sess.close()

    # -----------------------------------------------------
    # L3: entries past GPT sector 5 -- slot 25
    # -----------------------------------------------------
    print('\nL3: high slot (one partition in GPT slot 25)')
    # Entry array starts at LBA 2, 4 entries per sector.
    # Partition 25 is slot index 24 -> LBA 2 + 6 = 8, past
    # the four sectors PARTITION-MAP scans today.
    img, ents = make_disk(tmpdir, 'l3', 64 * MB,
                          [(25, 2048, 10239)])
    check('L3 authored 1 GPT entry', len(ents) == 1,
          repr(ents))
    slot = ents[0]['slot'] if ents else -1
    entry_lba = ENTRY_LBA + slot // 4
    check(f'L3 entry sits in slot 24 at LBA 8 '
          f'(slot {slot}, LBA {entry_lba})',
          slot == 24 and entry_lba == 8)
    sess, out = survey(img, PORT_BASE + 2)
    if sess is None:
        check('L3 boots and inits AHCI', False, out)
    else:
        check('L3 boots and inits AHCI', True)
        check('L3 finds the slot-25 partition',
              '1 partitions found' in out,
              repr(out.strip()[-160:]))
        expect(sess, 'L3 slot-25 start', '0 PART-ENT @',
               ents[0]['first'])
        expect(sess, 'L3 slot-25 end', '0 PART-END',
               ents[0]['last'])
        expect(sess, 'L3 MAP-TRUSTED?', 'MAP-TRUSTED?', TRUE)
        sess.close()

    # -----------------------------------------------------
    # L4: 64-bit LBA -- partition past 2 TiB
    # -----------------------------------------------------
    print('\nL4: 64-bit LBA (partition past 2 TiB)')
    img, ents = make_disk(tmpdir, 'l4', 2600000000000,
                          [(1, 5000000000, 5000010239)])
    check('L4 authored 1 GPT entry', len(ents) == 1,
          repr(ents))
    start = ents[0]['first']
    # sgdisk realigns without asking, so take the truncation
    # constant from what it actually wrote.
    trunc = start & 0xFFFFFFFF
    check(f'L4 start {start} is past 2 TiB '
          f'(high dword {start >> 32})', start >> 32 != 0)
    sess, out = survey(img, PORT_BASE + 3)
    if sess is None:
        check('L4 boots and inits AHCI', False, out)
    else:
        check('L4 boots and inits AHCI', True)
        # Load-bearing contract: fail closed.  The survey
        # cannot represent this entry, so it must say so
        # rather than print a wrong address as fact.
        expect(sess, 'L4 MAP-TRUSTED?', 'MAP-TRUSTED?',
               FALSE)
        # Belt-and-suspenders, parsed EXACTLY rather than by
        # substring: a correct full-width print of
        # 0x12A05F000 ends in the truncated dword's digits,
        # so `trunc not in out` would red on a correct
        # repair.  Compare parsed integers instead.
        printed = [int(t, 16) for t in
                   re.findall(r'LBA\s+([0-9A-Fa-f]+)', out)]
        check(f'L4 prints no truncated start '
              f'({trunc:#x} for true {start:#x})',
              trunc not in printed,
              f'printed {[hex(v) for v in printed]}')
        sess.close()

    # -----------------------------------------------------
    # L4b: bit 31 set, high dword ZERO
    # -----------------------------------------------------
    print('\nL4b: signed horizon (LBA >= 0x80000000, '
          'high dword 0)')
    # This kernel has no U< , so every LBA comparison is
    # signed and an LBA with bit 31 set reads as negative.
    # The real horizon is therefore bit 31 (~1 TiB at 512 B
    # sectors), not the 32/64-bit boundary.  L4's entry has
    # a NONZERO high dword, so a detector that only checks
    # 0x24/0x2C would pass L4 while leaving the whole band
    # 0x80000000-0xFFFFFFFF unguarded.  This layout is what
    # tells the two implementations apart.
    HZ_START = 0x90000000        # high dword 0, bit 31 set
    img, ents = make_disk(
        tmpdir, 'l4b', (HZ_START + 40960) * SECTOR,
        [(1, HZ_START, HZ_START + 10239)])
    check('L4b authored 1 GPT entry', len(ents) == 1,
          repr(ents))
    hz = ents[0]['first']
    check(f'L4b start {hz:#x} has high dword 0 and bit 31 '
          f'set', hz >> 32 == 0 and hz & 0x80000000 != 0,
          f'start={hz:#x}')
    sess, out = survey(img, PORT_BASE + 5)
    if sess is None:
        check('L4b boots and inits AHCI', False, out)
    else:
        check('L4b boots and inits AHCI', True)
        expect(sess, 'L4b MAP-TRUSTED?', 'MAP-TRUSTED?',
               FALSE)
        # Unlike L4 there is no truncation here -- the low
        # dword IS the address.  The defect is that it
        # cannot be COMPARED, so the survey must not present
        # it as a usable extent.
        printed = [int(t, 16) for t in
                   re.findall(r'LBA\s+([0-9A-Fa-f]+)', out)]
        check('L4b presents no comparable address',
              hz not in printed,
              f'printed {[hex(v) for v in printed]}')
        sess.close()

    # -----------------------------------------------------
    # L5: empty map -- valid GPT, zero partitions
    # -----------------------------------------------------
    print('\nL5: empty map (valid GPT, zero partitions)')
    # Distinct from a MISSING GPT, which is a different case
    # (no header at all, not gated here).  Here the header is
    # valid and the entry array is all zeros, so the map is
    # empty and fully representable.
    img, ents = make_disk(tmpdir, 'l5', 64 * MB, [])
    check('L5 authored 0 GPT entries', len(ents) == 0,
          repr(ents))
    sess, out = survey(img, PORT_BASE + 4)
    if sess is None:
        check('L5 boots and inits AHCI', False, out)
    else:
        check('L5 boots and inits AHCI', True)
        check('L5 reports 0 partitions',
              '0 partitions found' in out,
              repr(out.strip()[-160:]))
        # The phantom: PART-N @ 0 DO runs its body once
        # under this kernel's simplified LOOP compare, so an
        # empty map prints an extent that is not there --
        # fail-open in the display layer.
        check('L5 prints no phantom partition line',
              re.search(r'P\d+\s*:', out) is None,
              repr(out.strip()[-160:]))
        expect(sess, 'L5 PART-N', 'PART-N @', 0)
        # An empty map is fully representable, so trusted.
        expect(sess, 'L5 MAP-TRUSTED?', 'MAP-TRUSTED?', TRUE)
        sess.close()

finally:
    for p in USED_PORTS:
        subprocess.run(
            ['pkill', '-9', '-f', f'[q]emu.*{p}'],
            capture_output=True)
    shutil.rmtree(tmpdir, ignore_errors=True)

print(f'\nPassed: {PASS}/{PASS + FAIL}')
sys.exit(0 if FAIL == 0 else 1)
