#!/usr/bin/env python3
"""Gate for the INSTALL vocabulary's write allowlist (Piece 1).

The guarantee under test is an ALLOWLIST: SAFE-WRITE permits one
declared extent and refuses everything else, including sectors it
has never heard of.  A denylist would have to enumerate what to
avoid and would permit any partition the survey failed to see.

Two failure modes drive the design of this file:

1.  A refusal that only *prints* a refusal.  Every refuse case is
    therefore proved by a SENTINEL, not by the message: the bound
    writer records the LBA it was called with, the sentinel is set
    to a value the writer can never produce, and a refusal is only
    a pass if the sentinel survives untouched.  The message alone
    would be satisfied by a write that printed and then happened.

2.  A vector that "looks bound".  If BIND-WRITER stored a FIND flag
    (1) instead of an xt, SEC-WRITE-VEC would be nonzero, the
    "no writer bound" guard would be satisfied, INSTALL-STATUS would
    print "bound", and SAFE-WRITE would EXECUTE address 1.  So the
    bind path is proved by a real round-trip -- a known pattern is
    written through the vector and read back -- never by
    INSTALL-STATUS.

Parsing discipline follows tests/test_survey_layouts.py and
tests/test_abort.py: values are compared as exact integers and
"could not determine" is a failure, never a pass.  The kernel
prints "WORD ?" for an undefined word and then KEEPS EXECUTING the
rest of the line, so a substring match can be satisfied by
leftover stack junk.
"""
import os
import re
import socket
import sys
import time

sys.stdout.reconfigure(line_buffering=True)

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4490

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(10)
for attempt in range(20):
    try:
        s.connect(('127.0.0.1', PORT))
        break
    except (ConnectionRefusedError, OSError):
        time.sleep(0.5)
else:
    print("FAIL: connect")
    sys.exit(1)

time.sleep(2)
try:
    while True:
        s.recv(4096)
except Exception:
    pass


def send(cmd, wait=1.0):
    s.sendall((cmd + '\r').encode())
    time.sleep(wait)
    s.settimeout(1)
    resp = b''
    while True:
        try:
            d = s.recv(4096)
            if not d:
                break
            resp += d
        except Exception:
            break
    return resp.decode('ascii', errors='replace')


def body_of(raw):
    """Drop the echoed input line.

    The echo repeats the command, so scanning the whole response
    would read the command's own characters as though the kernel
    had printed them.
    """
    return raw.split('\n', 1)[1] if '\n' in raw else raw


def val(expr, wait=1.5):
    """Evaluate expr and return its printed integer, or None."""
    raw = send(f'DECIMAL {expr} .', wait)
    body = body_of(raw)
    if '?' in body:
        return None, raw
    nums = re.findall(r'-?\d+', body)
    return (int(nums[-1]) if nums else None), raw


PASS = FAIL = 0


def check(name, ok, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {name}')
    else:
        FAIL += 1
        print(f'  FAIL: {name} -- {detail}' if detail else
              f'  FAIL: {name}')


def expect(name, expr, want):
    v, raw = val(expr)
    check(f'{name} ({expr} = {want})', v is not None and v == want,
          f'got {v!r} from {raw.strip()[-90:]!r}')


def alive():
    v, _ = val('7 6 *')
    return v == 42


SENTINEL = -999999
PATTERN = 305419896          # 0x12345678
BASE = 2048
LEN = 64


def arm():
    """Reset the witness so a stale success cannot read as fresh."""
    send(f'DECIMAL {SENTINEL} W-LBA ! {SENTINEL} W-CNT ! '
         f'{SENTINEL} W-VAL !', 1.2)


def refused(name, expr, phrase):
    """A refusal is a pass only if the writer never ran."""
    arm()
    r = send(f'DECIMAL {expr}', 2.0)
    b = body_of(r)
    check(f'{name}: prints a refusal', phrase in b,
          repr(b.strip()[-90:]))
    expect(f'{name}: writer never ran', 'W-LBA @', SENTINEL)
    expect(f'{name}: stack emptied', 'DEPTH', 0)


# ---------------------------------------------------------------
print("\nTest 1: INSTALL loads and is usable")
# USING is only ALSO -- it never loads anything.  The vocabulary
# has to come off the catalog first, and LOAD-VOCAB takes a
# string: ( addr len -- ), not a parsed name.
send('ONLY FORTH DEFINITIONS DECIMAL', 0.8)
r = send('S" INSTALL" LOAD-VOCAB', 10.0)
check('LOAD-VOCAB INSTALL succeeds', '?' not in body_of(r),
      repr(body_of(r).strip()[-120:]))
check('interpreter alive after LOAD-VOCAB', alive())
r = send('USING INSTALL', 2.0)
check('USING INSTALL succeeds', '?' not in body_of(r),
      repr(body_of(r).strip()[-120:]))
check('interpreter alive after load', alive())
expect('load left the stack clean', 'DEPTH', 0)
# Bug #33 sentinel: FS-SLOT must be -1 at load time. Nothing
# before this line touches FS-SLOT, so this is a live probe of
# the load-time init, not a stale leftover.
expect('FS-SLOT = -1 at load (Bug #33 sentinel)', 'FS-SLOT @', -1)

# ---------------------------------------------------------------
print("\nTest 2: no raw absolute writer is nameable in INSTALL")
# The confinement claim: the only route to the disk from inside
# this vocabulary is the vector.  Two legs:
#
#   WORDS scan  -- corroboration only.  Serial line-wrap can split
#                  a name across a column boundary, so a wrapped
#                  AHCI-WRITE would tokenize as two fragments and
#                  false-PASS the absence check.
#   DEF? (FIND) -- authoritative.  find_ walks the live search
#                  order, which is what nameability means.
#
# If the two legs ever disagree, believe FIND.
#
# The WORDS capture runs BEFORE the test defines anything of its
# own: defining a word at the prompt re-threads VAR_LATEST through
# the FORTH chain and changes WORDS output (known cosmetic
# duplicate behavior), so the scan must describe the shipped
# vocabulary, not the test's residue.
w = send('WORDS', 8.0)
words_seen = set(re.findall(r'[!-~]+', w))
for present in ('SAFE-WRITE', 'GPT-WRITE', 'ADD-PARTITION',
                'ADD-BOOT-ENTRY'):
    check(f'WORDS lists {present}', present in words_seen)
check('WORDS does not list AHCI-WRITE (corroboration)',
      'AHCI-WRITE' not in words_seen)

# DEF? MUST be a colon definition.  Typed interactively,
# `WORD X FIND` never tests X: the outer interpreter fetches each
# token via word_, so the token FIND overwrites word_buffer (which
# find_ reads, taking no stack input) before FIND executes -- the
# lookup is always for the literal name "FIND", found or not.
# Compiled WORD/FIND run back-to-back with no interpreter fetch in
# between, so word_buffer survives.  Same reason BIND-WRITER works.
send(': DEF? WORD FIND NIP ; ', 1.5)
for raw_writer in ('AHCI-WRITE', 'ATA-WRITE-SECTOR', 'SECTOR-WRITE',
                   'LBA-WRITE', 'RAW-WRITE'):
    expect(f'{raw_writer} not nameable', f'DEF? {raw_writer}', 0)
# ...and the guard itself IS nameable, so the check above is not
# just measuring a broken DEF?.
v, raw = val('DEF? SAFE-WRITE')
check('DEF? resolves SAFE-WRITE (control)', v is not None and v != 0,
      f'got {v!r} from {raw.strip()[-90:]!r}')
# Second control, opposite direction: a name that has never existed
# must give 0 too.  The found-control catches a DEF? stuck at 0;
# this catches one stuck nonzero (the word_buffer clobber presented
# exactly as identical nonzero for found and not-found alike).
expect('DEF? nonsense word gives 0 (probe sanity)',
       'DEF? ZZZ-NEVER-DEFINED', 0)
# The probes leave the stack clean only if FIND's contract held on
# every path; residue here means the contract drifted.
expect('stack clean after nameability probes', 'DEPTH', 0)

# ---------------------------------------------------------------
print("\nTest 3: refuses by default -- unconfigured and unbound")
# Nothing declared, nothing bound.  This is the free tier's
# resting state and it must not write.
send('INSTALL DEFINITIONS', 1.0)
send('VARIABLE W-LBA  VARIABLE W-CNT  VARIABLE W-VAL', 1.5)
r = send(f'DECIMAL {SENTINEL} W-LBA !', 1.2)
expect('witness armed', 'W-LBA @', SENTINEL)
expect('OWN-BASE defaults to 0', 'OWN-BASE @', 0)
expect('OWN-LEN defaults to 0', 'OWN-LEN @', 0)
expect('SEC-WRITE-VEC defaults to unbound', 'SEC-WRITE-VEC @', 0)
expect('OWN-EXTENT? false for LBA 0', '0 OWN-EXTENT?', 0)
expect('OWN-EXTENT? false for a plausible LBA',
       f'{BASE} OWN-EXTENT?', 0)
refused('unconfigured SAFE-WRITE',
        f'IO-BUF {BASE} SAFE-WRITE', 'outside extent')

# ---------------------------------------------------------------
print("\nTest 4: extent declared, writer still unbound")
# The second guard, reached only once the first one passes.  A
# declared extent must not by itself make the installer able to
# write.
send(f'DECIMAL {BASE} OWN-BASE !  {LEN} OWN-LEN !', 1.2)
expect('OWN-BASE set', 'OWN-BASE @', BASE)
expect('in-extent LBA now allowed by OWN-EXTENT?',
       f'{BASE} OWN-EXTENT? 0=', 0)
refused('unbound SAFE-WRITE',
        f'IO-BUF {BASE} SAFE-WRITE', 'no writer bound')

# ---------------------------------------------------------------
print("\nTest 5: BIND-WRITER stores an xt, not a FIND flag")
# TW is the stand-in for AHCI-WRITE and takes its exact stack
# effect: ( lba count buf -- flag ).  It records all three so the
# round-trip can prove the arguments arrived in the right order,
# not merely that something ran.
# No ( ) stack comment in anything sent over serial: interactive
# "(" is read_key-until-")" (forth.asm:2391), but the whole line is
# already buffered in TIB, so it blocks on input that will never
# come and wedges the VM.  Safe in block source, fatal when typed.
# TW's effect is ( lba count buf -- flag ), AHCI-WRITE's exactly.
send(': TW @ W-VAL !  W-CNT !  W-LBA !  0 ; ', 1.5)
v, raw = val('DEF? TW')
tw_xt = v
check('TW is nameable', tw_xt is not None and tw_xt != 0,
      f'got {v!r} from {raw.strip()[-90:]!r}')
send('BIND-WRITER TW', 1.5)
expect('BIND-WRITER stored the xt of TW, not 1 or -1',
       'SEC-WRITE-VEC @', tw_xt if tw_xt else -1)

# ---------------------------------------------------------------
print("\nTest 6: round-trip through the vector")
# The only check that distinguishes a vector holding AHCI-WRITE
# from a vector holding 1: write a known pattern and read it back
# out the other side.
arm()
send(f'DECIMAL {PATTERN} IO-BUF !', 1.2)
r = send(f'DECIMAL IO-BUF {BASE + 2} SAFE-WRITE', 2.0)
b = body_of(r)
# "no refusal printed" is satisfied by an empty response, which is
# what a wedged VM returns.  Require the prompt back as proof the
# line actually ran to completion.
check('in-extent SAFE-WRITE completes without refusing',
      'ok' in b and 'refuse' not in b and 'failed' not in b,
      repr(b.strip()[-90:]))
expect('writer received the LBA', 'W-LBA @', BASE + 2)
expect('writer received count 1', 'W-CNT @', 1)
expect('pattern round-tripped through the vector',
       'W-VAL @', PATTERN)
expect('SAFE-WRITE consumed both arguments', 'DEPTH', 0)
check('interpreter alive after a permitted write', alive())

# ---------------------------------------------------------------
print("\nTest 7: extent boundaries")
# Off-by-one at either edge is the difference between writing
# inside the extent and writing the host's first sector.
expect('first LBA of extent allowed',
       f'{BASE} OWN-EXTENT?', -1)
expect('last LBA of extent allowed',
       f'{BASE + LEN - 1} OWN-EXTENT?', -1)
expect('one below base refused',
       f'{BASE - 1} OWN-EXTENT?', 0)
expect('one past end refused',
       f'{BASE + LEN} OWN-EXTENT?', 0)
expect('LBA 0 refused', '0 OWN-EXTENT?', 0)
refused('below base', f'IO-BUF {BASE - 1} SAFE-WRITE',
        'outside extent')
refused('past end', f'IO-BUF {BASE + LEN} SAFE-WRITE',
        'outside extent')
refused('LBA 0 -- the host boot sector',
        'IO-BUF 0 SAFE-WRITE', 'outside extent')

# ---------------------------------------------------------------
print("\nTest 8: bit-31 LBA refused, not wrapped")
# No U< in this kernel, so every compare is signed.  An LBA at or
# past 0x80000000 reads as negative; it must be refused rather
# than subtracting into the extent's range.
send('HEX', 0.8)
raw = send('80000000 OWN-EXTENT? . DECIMAL', 1.5)
nums = re.findall(r'-?\d+', body_of(raw))
check('OWN-EXTENT? refuses 0x80000000',
      bool(nums) and int(nums[-1]) == 0,
      repr(body_of(raw).strip()[-90:]))
arm()
r = send('HEX IO-BUF 80000000 SAFE-WRITE DECIMAL', 2.0)
check('SAFE-WRITE refuses 0x80000000',
      'outside extent' in body_of(r),
      repr(body_of(r).strip()[-90:]))
expect('writer never ran for 0x80000000', 'W-LBA @', SENTINEL)
expect('stack emptied', 'DEPTH', 0)

# ---------------------------------------------------------------
print("\nTest 9: a failing write is not a successful one")
# AHCI-WRITE reports failure in a flag.  Dropping that flag would
# turn every failed write into a silent success.
# ( lba count buf -- flag ), drops buf and count, records the
# LBA, and reports failure.  No ( ) comment: see Test 5.
send(': TWF DROP DROP W-LBA !  1 ; ', 1.5)
send('BIND-WRITER TWF', 1.5)
arm()
r = send(f'DECIMAL IO-BUF {BASE + 2} SAFE-WRITE', 2.0)
b = body_of(r)
check('failing writer aborts with a message', 'write failed' in b,
      repr(b.strip()[-90:]))
expect('the failing writer really did run', 'W-LBA @', BASE + 2)
expect('abort emptied the stack', 'DEPTH', 0)
check('interpreter alive after a failed write', alive())

# ---------------------------------------------------------------
print("\nTest 10: BIND-WRITER on an absent name is not an error")
# The free tier reaches this line with no AHCI-WRITE to bind.  It
# must leave the vector as it found it and must not error.
send('BIND-WRITER TW', 1.5)
v_before, _ = val('SEC-WRITE-VEC @')
r = send('BIND-WRITER ZZ-NO-SUCH-WRITER', 1.5)
check('absent name does not print an error',
      '?' not in body_of(r), repr(body_of(r).strip()[-90:]))
expect('vector unchanged by a failed bind',
       'SEC-WRITE-VEC @', v_before if v_before else -1)
expect('failed bind left the stack clean', 'DEPTH', 0)
check('interpreter alive after a failed bind', alive())

# ---------------------------------------------------------------
# FREE-EXTENT tests
#
# The survey contract (PART-ENT, PART-END, MAP-TRUSTED?, etc.)
# is populated manually here — no AHCI disk is attached in this
# harness.  A fake reader returns success with a zeroed buffer,
# simulating empty sectors.  The placement logic is exercised by
# authored partition layouts; the read-back verification is
# exercised by controlling the buffer contents.
# ---------------------------------------------------------------

# Set up both SURVEYOR and INSTALL in the search order.
# SURVEYOR is embedded.  Order matters: ALSO SURVEYOR first,
# then USING INSTALL puts INSTALL on top without evicting
# SURVEYOR.  Do NOT use INSTALL DEFINITIONS here — DOVOC
# replaces the top entry, which would evict SURVEYOR.
send('ALSO SURVEYOR', 1.0)
send('USING INSTALL', 1.0)

# Create a zeroed 512-byte buffer and a fake reader.
# TR: ( lba count -- flag ) always succeeds, does nothing.
send('CREATE TR-BUF 512 ALLOT', 1.0)
send('TR-BUF 512 0 FILL', 0.5)
send(': TR 2DROP 0 ;', 1.0)

# Helper to populate one PART-TBL entry.
# PE! ( start end idx -- )
# Stride is 16 bytes per entry.  Layout:
#   +0: start LBA  +4: GUID  +8: type  +9: bad?  +C: end LBA
send(': PE! PART-ENT >R R@ 12 + ! R> ! ;', 1.0)

# Bind reader for all FREE-EXTENT tests.
send("' TR SEC-READ-VEC !", 0.5)
send('TR-BUF RD-BUF-ADDR !', 0.5)

# ---------------------------------------------------------------
print("\nTest 11: FREE-EXTENT refuses when MAP-TRUSTED? is false")
send('0 MAP-OK !  0 PART-N !', 0.3)
expect('MAP-TRUSTED? is false', 'MAP-TRUSTED?', 0)
expect('FREE-EXTENT refuses (untrusted map)',
       '100 FREE-EXTENT', 0)
expect('OWN-BASE unchanged', 'OWN-BASE @', BASE)
check('alive after untrusted map', alive())

# ---------------------------------------------------------------
print("\nTest 12: FREE-EXTENT refuses with no reader bound")
send('-1 MAP-OK !  0 SEC-READ-VEC !  0 PART-N !', 0.3)
send('0 OWN-BASE !  0 OWN-LEN !', 0.3)
expect('FREE-EXTENT refuses (no reader)',
       '100 FREE-EXTENT', 0)
expect('OWN-BASE unchanged (no reader)', 'OWN-BASE @', 0)
check('alive after no reader', alive())

# ---------------------------------------------------------------
print("\nTest 13: FREE-EXTENT finds gap in empty map")
# No partitions, all space is free.
send("' TR SEC-READ-VEC !  TR-BUF RD-BUF-ADDR !", 0.5)
send('TR-BUF 512 0 FILL', 0.3)
send('-1 MAP-OK !  0 PART-N !', 0.3)
send('0 OWN-BASE !  0 OWN-LEN !', 0.3)
expect('FREE-EXTENT succeeds (empty map)',
       '100 FREE-EXTENT', -1)
# MIN-LBA = 34 (after GPT header + entry sectors)
expect('OWN-BASE = MIN-LBA (34)', 'OWN-BASE @', 34)
expect('OWN-LEN = 100', 'OWN-LEN @', 100)
check('alive after empty map', alive())

# ---------------------------------------------------------------
print("\nTest 14: FREE-EXTENT finds gap between partitions")
# P0: 2048-10239   P1: 20480-28671
# Pre-P0 gap: 34-2047 = 2014 sectors (too small for 2100)
# Inter-partition gap: 10240-20479 = 10240 sectors (fits 2100)
send('0 OWN-BASE !  0 OWN-LEN !', 0.3)
send('-1 MAP-OK !  2 PART-N !', 0.3)
send('2048 10239 0 PE!', 0.5)
send('20480 28671 1 PE!', 0.5)
send('0 0 PART-ENT 9 + C!  0 1 PART-ENT 9 + C!', 0.3)
send('TR-BUF 512 0 FILL', 0.3)
expect('FREE-EXTENT succeeds (gap between)',
       '2100 FREE-EXTENT', -1)
# Should land right after P0: LBA 10240
expect('OWN-BASE = 10240 (after P0)',
       'OWN-BASE @', 10240)
expect('OWN-LEN = 2100', 'OWN-LEN @', 2100)
check('alive after gap find', alive())

# ---------------------------------------------------------------
print("\nTest 15: FREE-EXTENT lands in pre-P0 gap when small")
# Same layout, but request fits in the pre-P0 gap.
send('0 OWN-BASE !  0 OWN-LEN !', 0.3)
send('TR-BUF 512 0 FILL', 0.3)
expect('FREE-EXTENT succeeds (pre-P0 gap)',
       '100 FREE-EXTENT', -1)
# Should land at MIN-LBA = 34
expect('OWN-BASE = 34 (pre-P0 gap)', 'OWN-BASE @', 34)
expect('OWN-LEN = 100', 'OWN-LEN @', 100)
check('alive after pre-P0 gap', alive())

# ---------------------------------------------------------------
print("\nTest 16: FREE-EXTENT refuses when no gap fits")
# One huge partition fills MIN-LBA to near horizon.
send('0 OWN-BASE !  0 OWN-LEN !  1 PART-N !', 0.3)
# Start at 34, end at 2147483646 (LBA-HORIZON - 1)
send('34 2147483646 0 PE!', 0.5)
send('0 0 PART-ENT 9 + C!', 0.3)
expect('FREE-EXTENT refuses (no room)',
       '100 FREE-EXTENT', 0)
expect('OWN-BASE unchanged (no room)', 'OWN-BASE @', 0)
check('alive after no room', alive())

# ---------------------------------------------------------------
print("\nTest 17: FREE-EXTENT refuses non-empty readback")
# Empty map (all free), but buffer has non-zero data.
send('0 OWN-BASE !  0 OWN-LEN !', 0.3)
send('-1 MAP-OK !  0 PART-N !', 0.3)
# Put non-zero data in the read buffer.
send('305419896 TR-BUF !', 0.5)
expect('FREE-EXTENT refuses (non-empty)',
       '10 FREE-EXTENT', 0)
expect('OWN-BASE unchanged (non-empty)',
       'OWN-BASE @', 0)
check('alive after non-empty readback', alive())

# ---------------------------------------------------------------
print("\nTest 18: FREE-EXTENT refuses zero or negative request")
send('0 OWN-BASE !  0 OWN-LEN !', 0.3)
send('-1 MAP-OK !  0 PART-N !', 0.3)
send('TR-BUF 512 0 FILL', 0.3)
expect('FREE-EXTENT refuses 0 sectors',
       '0 FREE-EXTENT', 0)
expect('FREE-EXTENT refuses -1 sectors',
       '-1 FREE-EXTENT', 0)
expect('OWN-BASE unchanged', 'OWN-BASE @', 0)
check('alive after zero/negative', alive())

# ---------------------------------------------------------------
# FREE-SLOT tests
#
# FREE-SLOT scans the raw GPT entry array for the first slot whose
# 128 bytes are all zero.  No AHCI disk is attached here, so the
# entry array is synthesised by a fake reader that decides what
# each sector contains from the LBA it was asked for.
#
# TRS ( lba count -- flag ) zero-fills the buffer, then marks as
# used every slot whose GLOBAL index is below TS-USED.  Slot g
# lives in sector 2 + g/4, so the sector at LBA n holds global
# slots (n-2)*4 .. (n-2)*4+3.  Setting TS-USED to k therefore
# authors "the first k slots are taken" across sector boundaries
# without the test having to know which sector that lands in.
#
# TS-ERRLBA makes one chosen sector report a read error, so the
# mid-scan error path is exercised on a layout that would
# otherwise have succeeded -- a refusal that could also be
# explained by "no free slot" would prove nothing.
# ---------------------------------------------------------------

send('DECIMAL', 0.5)
send('VARIABLE TS-USED  VARIABLE TS-ERRLBA', 1.0)
send('-1 TS-ERRLBA !  0 TS-USED !', 0.5)
send(': TRS DROP TS-ERRLBA @ OVER = IF DROP 1 EXIT THEN', 1.0)
send('  TR-BUF 512 0 FILL  2 - 4 *', 1.0)
send('  4 0 DO DUP I + TS-USED @ < IF', 1.0)
send('    -1 TR-BUF I 128 * + ! THEN LOOP DROP 0 ;', 1.5)
check('TRS defined without error', alive())

SLOT_SENTINEL = -777777


def arm_slot():
    send(f'DECIMAL {SLOT_SENTINEL} FS-SLOT !', 0.8)


# ---------------------------------------------------------------
print("\nTest 19: slot geometry is exact")
# Slot g lives at LBA 2 + g/4, byte offset (g mod 4) * 128.  Both
# edges of every sector are checked, plus slot 127 -- the last
# slot must land on LBA 33, the last sector of the entry array.
# An off-by-one here writes a partition entry into the first
# sector of the host's data.
expect('SLOT-LBA 0', '0 SLOT-LBA', 2)
expect('SLOT-LBA 3 still sector 2', '3 SLOT-LBA', 2)
expect('SLOT-LBA 4 crosses to sector 3', '4 SLOT-LBA', 3)
expect('SLOT-LBA 127 is the last sector', '127 SLOT-LBA', 33)
expect('SLOT-OFF 0', '0 SLOT-OFF', 0)
expect('SLOT-OFF 1', '1 SLOT-OFF', 128)
expect('SLOT-OFF 3 is the last entry in a sector',
       '3 SLOT-OFF', 384)
expect('SLOT-OFF 4 wraps to 0', '4 SLOT-OFF', 0)
expect('SLOT-OFF 127', '127 SLOT-OFF', 384)
# The last entry ends exactly at the end of a 512-byte sector.
expect('last entry ends at the sector boundary',
       '127 SLOT-OFF 128 +', 512)

# ---------------------------------------------------------------
print("\nTest 20: SLOT-FREE? tests all 128 bytes, not just the GUID")
# This is the asymmetry against the survey, which decides an entry
# is empty from the first 8 bytes of the type GUID alone.  That is
# fine for deciding what to DISPLAY; it is not fine for deciding
# what to OVERWRITE.  A tool that cleared the type GUID but left a
# unique GUID or a name behind must still read as occupied.
send('TR-BUF RD-BUF-ADDR !', 0.5)
send('TR-BUF 512 0 FILL', 0.5)
expect('zeroed slot 0 is free', '0 SLOT-FREE?', -1)
expect('zeroed slot 3 is free', '3 SLOT-FREE?', -1)
send('DECIMAL 1 TR-BUF !', 0.5)
expect('first byte set makes slot 0 occupied', '0 SLOT-FREE?', 0)
send('TR-BUF 512 0 FILL', 0.5)
send('DECIMAL 1 TR-BUF 124 + !', 0.5)
expect('LAST dword set makes slot 0 occupied',
       '0 SLOT-FREE?', 0)
expect('the neighbouring slot is untouched', '1 SLOT-FREE?', -1)
send('TR-BUF 512 0 FILL', 0.5)
send('DECIMAL 1 TR-BUF 128 + !', 0.5)
expect('slot 1 occupied does not leak into slot 0',
       '0 SLOT-FREE?', -1)
expect('slot 1 reads occupied', '1 SLOT-FREE?', 0)
check('alive after SLOT-FREE? probes', alive())

# ---------------------------------------------------------------
print("\nTest 21: FREE-SLOT refuses with no reader bound")
send('0 SEC-READ-VEC !  TR-BUF RD-BUF-ADDR !', 0.5)
arm_slot()
expect('FREE-SLOT refuses (no reader)', 'FREE-SLOT', 0)
expect('FS-SLOT untouched (no reader)', 'FS-SLOT @',
       SLOT_SENTINEL)
expect('stack clean (no reader)', 'DEPTH', 0)
check('alive after no reader', alive())

# ---------------------------------------------------------------
print("\nTest 22: FREE-SLOT refuses with no buffer set")
send("' TRS SEC-READ-VEC !  0 RD-BUF-ADDR !", 0.5)
arm_slot()
expect('FREE-SLOT refuses (null buffer)', 'FREE-SLOT', 0)
expect('FS-SLOT untouched (null buffer)', 'FS-SLOT @',
       SLOT_SENTINEL)
check('alive after null buffer', alive())

# ---------------------------------------------------------------
print("\nTest 23: empty entry array yields slot 0")
# On a legitimately empty disk (no partitions, trusted survey)
# the consistency gate must NOT fire: occupied=0 AND PART-N=0
# is consistent, so slot 0 is claimable.
send("' TRS SEC-READ-VEC !  TR-BUF RD-BUF-ADDR !", 0.5)
send('DECIMAL -1 TS-ERRLBA !  0 TS-USED !', 0.5)
send('-1 MAP-OK !  0 PART-N !', 0.5)
arm_slot()
expect('FREE-SLOT succeeds (empty array)', 'FREE-SLOT', -1)
expect('FS-SLOT = 0', 'FS-SLOT @', 0)
expect('stack clean (empty array)', 'DEPTH', 0)
check('alive after empty array', alive())

# ---------------------------------------------------------------
print("\nTest 24: first N occupied yields slot N")
# 2 stays inside the first sector; 4 is the first slot of the
# SECOND sector, so it only comes out right if the scan re-reads
# on the sector boundary; 5 lands mid-sector after that boundary;
# 127 is the last slot on the last sector.
send('-1 MAP-OK !', 0.3)
for used, want in ((1, 1), (2, 2), (4, 4), (5, 5), (127, 127)):
    send(f'DECIMAL {used} TS-USED !  {used} PART-N !', 0.5)
    arm_slot()
    expect(f'{used} occupied -> FREE-SLOT succeeds',
           'FREE-SLOT', -1)
    expect(f'{used} occupied -> FS-SLOT = {want}',
           'FS-SLOT @', want)
check('alive after occupied-prefix scans', alive())

# ---------------------------------------------------------------
print("\nTest 25: a full entry array refuses")
# All 128 slots taken.  Refusing is the only safe answer: there is
# no slot to claim and nothing may be overwritten to make one.
send('DECIMAL 128 TS-USED !  128 PART-N !  -1 MAP-OK !', 0.5)
arm_slot()
expect('FREE-SLOT refuses (array full)', 'FREE-SLOT', 0)
expect('FS-SLOT untouched (array full)', 'FS-SLOT @',
       SLOT_SENTINEL)
expect('stack clean (array full)', 'DEPTH', 0)
check('alive after full array', alive())

# ---------------------------------------------------------------
print("\nTest 26: a mid-scan read error refuses")
# TS-USED 8 alone would return slot 8 (first slot of LBA 4).  The
# error is injected on exactly that sector, so a refusal here can
# only be the read-error path -- it cannot be explained away as
# "no free slot".  Without this framing the test would pass on a
# FREE-SLOT that ignored the reader's flag entirely.
send('DECIMAL 8 TS-USED !  8 PART-N !  -1 MAP-OK !', 0.5)
send('DECIMAL -1 TS-ERRLBA !', 0.5)
arm_slot()
expect('control: no error -> slot 8', 'FREE-SLOT', -1)
expect('control: FS-SLOT = 8', 'FS-SLOT @', 8)
send('DECIMAL 4 TS-ERRLBA !', 0.5)
arm_slot()
expect('read error at LBA 4 -> refuses', 'FREE-SLOT', 0)
expect('FS-SLOT untouched (read error)', 'FS-SLOT @',
       SLOT_SENTINEL)
expect('stack clean (read error)', 'DEPTH', 0)
check('alive after mid-scan read error', alive())
# An error on the very first sector must refuse too.
send('DECIMAL 0 TS-USED !  0 PART-N !  2 TS-ERRLBA !', 0.5)
arm_slot()
expect('read error at LBA 2 -> refuses', 'FREE-SLOT', 0)
expect('FS-SLOT untouched (first-sector error)', 'FS-SLOT @',
       SLOT_SENTINEL)
send('DECIMAL -1 TS-ERRLBA !', 0.5)
check('alive after first-sector read error', alive())

# ---------------------------------------------------------------
print("\nTest 27: GPT-CRC32 known-answer vector")
# CBF43926 has bit 31 set, so it is compared rather than printed:
# a signed `.` would render it negative.  This vector drives the
# register through high-bit-set states, which is what catches a
# sign-extending shift.
send('HEX', 0.5)
send(': GCRC-KAT S" 123456789" GPT-CRC32 CBF43926 =', 1.0)
send('  IF ." KAT-OK" ELSE ." KAT-FAIL" THEN ;', 1.0)
r = send('GCRC-KAT', 2.0)
check('GPT-CRC32("123456789") = CBF43926',
      'KAT-OK' in body_of(r), repr(body_of(r).strip()[-90:]))
# Empty input must not wedge: 0 0 DO runs once under this kernel,
# so GPT-CRC32 guards len<1.  The assertion is wrapped in a colon
# def and invoked by a name that does NOT contain the expected
# string -- sending the `." EMPTY-OK"` line directly would put the
# answer in the command echo and pass against a wedged VM.
send(': GCRC-EMPTY HERE 0 GPT-CRC32 0 =', 1.0)
send('  IF ." EMPTY-OK" ELSE ." EMPTY-BAD" THEN ;', 1.0)
r = send('GCRC-EMPTY', 2.0)
check('GPT-CRC32 of empty input is 0',
      'EMPTY-OK' in body_of(r), repr(body_of(r).strip()[-90:]))
send('DECIMAL', 0.5)
check('alive after CRC probes', alive())

# ---------------------------------------------------------------
# GPT-ARM / GPT-PERMIT? / GPT-WRITE tests
#
# TRH ( lba count -- flag ) synthesises a primary GPT header in
# the buffer when LBA 1 is requested.  Every field the arm path
# reads is a variable, so each guard can be driven independently.
#
# The fixture sets AlternateLBA (+0x20) and FirstUsableLBA (+0x28)
# to DELIBERATELY DIFFERENT values.  Those two fields are eight
# bytes apart and an earlier draft of GPT-ARM read the wrong one:
# 0x28 is FirstUsableLBA, not AlternateLBA.  On a tight GPT that
# refuses harmlessly (34-32 < 34), but on a 1 MB-aligned disk it
# ARMS, with GW-BHDR and GW-BENT pointing into the first
# partition's live data -- a "backup header" written over a host
# filesystem.  A fixture that left the two fields equal, or
# populated only one, could not tell the two reads apart.  Same
# de-aliasing discipline as the read-error control in Test 26.
# ---------------------------------------------------------------

send('DECIMAL', 0.5)
send('VARIABLE TH-SIGLO  VARIABLE TH-SIGHI', 1.0)
send('VARIABLE TH-ALTLO  VARIABLE TH-ALTHI', 1.0)
send('VARIABLE TH-FUSE', 1.0)
send(': TRH DROP TS-ERRLBA @ OVER = IF DROP 1 EXIT THEN', 1.0)
send('  1 = IF TR-BUF 512 0 FILL', 1.0)
send('    TH-SIGLO @ TR-BUF !  TH-SIGHI @ TR-BUF 4 + !', 1.0)
send('    TH-ALTLO @ TR-BUF 32 + !', 1.0)
send('    TH-ALTHI @ TR-BUF 36 + !', 1.0)
send('    TH-FUSE @ TR-BUF 40 + ! THEN  0 ;', 1.5)
check('TRH defined without error', alive())

# A valid header by default; individual tests spoil one field.
ALT = 1048575          # a real disk-end LBA (512 MB image)
FUSE = 2048            # the decoy at +0x28, 1 MB-aligned
SLOT = 5               # -> GW-ENT 3, backup offset +1


def good_header():
    send('HEX 20494645 TH-SIGLO !  54524150 TH-SIGHI ! DECIMAL',
         1.0)
    send(f'DECIMAL {ALT} TH-ALTLO !  0 TH-ALTHI !', 0.6)
    send(f'DECIMAL {FUSE} TH-FUSE !  -1 TS-ERRLBA !', 0.6)
    send(f'DECIMAL {SLOT} FS-SLOT !', 0.5)
    send("' TRH SEC-READ-VEC !  TR-BUF RD-BUF-ADDR !", 0.6)


# ---------------------------------------------------------------
print("\nTest 28: GPT-ARM refuses on every precondition")
good_header()
send('0 SEC-READ-VEC !', 0.4)
expect('refuses with no reader', 'GPT-ARM', 0)
expect('permit disarmed (no reader)', 'GW-ARMED @', 0)
good_header()
send('0 RD-BUF-ADDR !', 0.4)
expect('refuses with no buffer', 'GPT-ARM', 0)
good_header()
send('DECIMAL -1 FS-SLOT !', 0.4)
expect('refuses negative FS-SLOT', 'GPT-ARM', 0)
good_header()
send('DECIMAL 128 FS-SLOT !', 0.4)
expect('refuses FS-SLOT past the last slot', 'GPT-ARM', 0)
good_header()
send('DECIMAL 0 TH-SIGLO !', 0.4)
expect('refuses a bad signature', 'GPT-ARM', 0)
good_header()
send('DECIMAL 1 TS-ERRLBA !', 0.4)
expect('refuses a header read error', 'GPT-ARM', 0)
expect('permit disarmed after every refusal', 'GW-ARMED @', 0)
expect('GW-BHDR left zero, not half-populated', 'GW-BHDR @', 0)
expect('GW-ENT left zero', 'GW-ENT @', 0)
check('alive after arm refusals', alive())

# ---------------------------------------------------------------
print("\nTest 29: GPT-ARM reads AlternateLBA (+0x20), not "
      "FirstUsableLBA (+0x28)")
# The de-aliasing test.  ALT and FUSE differ, so reading the wrong
# offset yields 2048 instead of 1048575 -- a wrong, catchable
# value rather than a coincidentally-right one.
good_header()
expect('GPT-ARM succeeds on a valid header', 'GPT-ARM', -1)
expect('permit is armed', 'GW-ARMED @', -1)
expect('GW-BHDR = AlternateLBA, NOT FirstUsableLBA',
       'GW-BHDR @', ALT)
# Stated separately so the failure message names the confusion:
# had GPT-ARM read +0x28, this would be FUSE.
expect('GW-BHDR is not the +0x28 decoy value',
       f'GW-BHDR @ {FUSE} =', 0)
expect('GW-HDR = 1', 'GW-HDR @', 1)
expect('GW-ENT = SLOT-LBA of the chosen slot',
       'GW-ENT @', 2 + SLOT // 4)
expect('GW-BENT mirrors GW-ENT at the disk end',
       'GW-BENT @', ALT - 32 + SLOT // 4)
# All four must be distinct, or the permit is smaller than it
# claims and one of the four writes has nowhere to go.
expect('GW-HDR distinct from GW-ENT',
       'GW-HDR @ GW-ENT @ =', 0)
expect('GW-ENT distinct from GW-BENT',
       'GW-ENT @ GW-BENT @ =', 0)
expect('GW-BENT distinct from GW-BHDR',
       'GW-BENT @ GW-BHDR @ =', 0)
expect('GW-HDR distinct from GW-BHDR',
       'GW-HDR @ GW-BHDR @ =', 0)
check('alive after a successful arm', alive())

# ---------------------------------------------------------------
print("\nTest 30: the horizon bites at claim time")
# The backup header is at the disk's last LBA, so this is where a
# disk too large for signed compares must be refused -- once,
# before anything is written.
good_header()
send('DECIMAL 1 TH-ALTHI !', 0.4)
expect('refuses AlternateLBA with a nonzero high cell',
       'GPT-ARM', 0)
expect('disarmed (high cell)', 'GW-ARMED @', 0)
good_header()
send('HEX 80000000 TH-ALTLO ! DECIMAL', 0.6)
expect('refuses AlternateLBA past the horizon (bit 31)',
       'GPT-ARM', 0)
expect('disarmed (bit 31)', 'GW-ARMED @', 0)
good_header()
send('DECIMAL 60 TH-ALTLO !', 0.4)
expect('refuses when the backup array would overlap the primary',
       'GPT-ARM', 0)
# Control: one sector further out and the same layout arms, so
# the refusal above is the overlap check and not something else.
good_header()
send('DECIMAL 66 TH-ALTLO !', 0.4)
expect('control: 66 puts the backup array base at MIN-LBA',
       'GPT-ARM', -1)
expect('control: GW-BENT = base 34 + our slot sector',
       'GW-BENT @', 34 + SLOT // 4)
check('alive after horizon checks', alive())

# ---------------------------------------------------------------
print("\nTest 31: GPT-PERMIT? admits exactly four LBAs")
good_header()
expect('re-arm for permit tests', 'GPT-ARM', -1)
expect('permits the primary header', '1 GPT-PERMIT?', -1)
expect('permits our entry sector',
       f'{2 + SLOT // 4} GPT-PERMIT?', -1)
expect('permits the backup entry sector',
       f'{ALT - 32 + SLOT // 4} GPT-PERMIT?', -1)
expect('permits the backup header', f'{ALT} GPT-PERMIT?', -1)
# LBA 0 is not in the set -- refused by absence, not by a check.
expect('REFUSES LBA 0, the protective MBR', '0 GPT-PERMIT?', 0)
# Other entry sectors belong to the host's other 127 slots.
expect('refuses entry sector 2 (another slot)',
       '2 GPT-PERMIT?', 0)
expect('refuses entry sector 33 (another slot)',
       '33 GPT-PERMIT?', 0)
expect('refuses MIN-LBA', '34 GPT-PERMIT?', 0)
# Neighbours of every permitted LBA, both sides.
for lba, why in ((0, 'below the header'),
                 (2 + SLOT // 4 - 1, 'below our entry sector'),
                 (2 + SLOT // 4 + 1, 'above our entry sector'),
                 (ALT - 32 + SLOT // 4 - 1, 'below backup entry'),
                 (ALT - 32 + SLOT // 4 + 1, 'above backup entry'),
                 (ALT - 1, 'below the backup header'),
                 (ALT + 1, 'above the backup header')):
    expect(f'refuses {lba} ({why})', f'{lba} GPT-PERMIT?', 0)
# Unarmed refuses everything, including what it just permitted.
send('GW-DISARM', 0.5)
expect('unarmed refuses the primary header', '1 GPT-PERMIT?', 0)
expect('unarmed refuses the backup header',
       f'{ALT} GPT-PERMIT?', 0)
expect('unarmed refuses LBA 0', '0 GPT-PERMIT?', 0)
expect('unarmed permit leaves the stack clean', 'DEPTH', 0)
check('alive after permit membership', alive())

# ---------------------------------------------------------------
print("\nTest 32: GPT-WRITE honours the permit")
# Same sentinel discipline as SAFE-WRITE: a refusal counts only if
# the writer never ran.
send('BIND-WRITER TW', 1.2)
arm()
r = send('DECIMAL IO-BUF 1 GPT-WRITE', 2.0)
check('unarmed GPT-WRITE refuses', 'not a GPT sector' in body_of(r),
      repr(body_of(r).strip()[-90:]))
expect('unarmed: writer never ran', 'W-LBA @', SENTINEL)
good_header()
expect('arm for write tests', 'GPT-ARM', -1)
send('BIND-WRITER TW', 1.2)
arm()
r = send('DECIMAL IO-BUF 0 GPT-WRITE', 2.0)
check('GPT-WRITE refuses LBA 0', 'not a GPT sector' in body_of(r),
      repr(body_of(r).strip()[-90:]))
expect('LBA 0: writer never ran', 'W-LBA @', SENTINEL)
expect('LBA 0: stack emptied', 'DEPTH', 0)
arm()
r = send('DECIMAL IO-BUF 2 GPT-WRITE', 2.0)
check("GPT-WRITE refuses another slot's entry sector",
      'not a GPT sector' in body_of(r),
      repr(body_of(r).strip()[-90:]))
expect('other sector: writer never ran', 'W-LBA @', SENTINEL)
# The permitted writes must actually reach the writer.
for lba, name in ((1, 'primary header'),
                  (2 + SLOT // 4, 'our entry sector'),
                  (ALT - 32 + SLOT // 4, 'backup entry sector'),
                  (ALT, 'backup header')):
    arm()
    send(f'DECIMAL {PATTERN} IO-BUF !', 0.8)
    r = send(f'DECIMAL IO-BUF {lba} GPT-WRITE', 2.0)
    b = body_of(r)
    check(f'GPT-WRITE permits the {name}',
          'ok' in b and 'refuse' not in b and 'failed' not in b,
          repr(b.strip()[-90:]))
    expect(f'{name}: writer received LBA {lba}', 'W-LBA @', lba)
    expect(f'{name}: count 1', 'W-CNT @', 1)
    expect(f'{name}: buffer round-tripped', 'W-VAL @', PATTERN)
# A failing writer must not read as a successful GPT write.
send('BIND-WRITER TWF', 1.2)
arm()
r = send('DECIMAL IO-BUF 1 GPT-WRITE', 2.0)
check('a failing GPT write aborts', 'GPT write failed' in body_of(r),
      repr(body_of(r).strip()[-90:]))
expect('the failing writer really ran', 'W-LBA @', 1)
expect('abort emptied the stack', 'DEPTH', 0)
check('alive after GPT-WRITE tests', alive())

# ---------------------------------------------------------------
# Streaming CRC split-boundary test
# ---------------------------------------------------------------
print("\nTest 33: streaming CRC split-boundary")
# CRC-BEGIN, CRC-CHUNK "12345", CRC-CHUNK "6789", CRC-END must
# equal CBF43926. A single-chunk pass can't tell you the
# accumulator survives a call boundary; a split one can.
send('HEX', 0.5)
send(': GCRC-SPLIT CRC-BEGIN', 1.0)
send('  S" 12345" CRC-CHUNK', 1.0)
send('  S" 6789" CRC-CHUNK CRC-END', 1.0)
send('  CBF43926 = IF ." SPLIT-OK"', 1.0)
send('  ELSE ." SPLIT-BAD" THEN ;', 1.0)
r = send('GCRC-SPLIT', 2.0)
check('streaming CRC split-boundary = CBF43926',
      'SPLIT-OK' in body_of(r),
      repr(body_of(r).strip()[-90:]))
send('DECIMAL', 0.5)
check('alive after split-boundary CRC', alive())

# ---------------------------------------------------------------
# ADD-PARTITION tests
#
# The fixture simulates a GPT disk with a write cache: the fake
# writer stores written sectors, and the fake reader returns them
# on subsequent reads. This makes the readback verification path
# exercise real round-trip I/O, not a no-op.
#
# The entry sector at GW-ENT is pre-populated with 3 occupied
# slots and 1 free slot (our slot). After ADD-PARTITION, the
# byte-identical gate checks:
#   (a) the 3 neighbours are unchanged
#   (b) our slot contains the entry we provided
#   (c) the backup entry sector is byte-identical to the primary
#   (d) both headers have correct CRCs
# ---------------------------------------------------------------

# Use the same ALT/SLOT from the GPT-ARM tests.
# ALT = 1048575, SLOT = 5 -> entry sector LBA 3 (slot 5 / 4 = 1,
# + GPT-ARR-LBA 2 = 3), backup entry at ALT - 32 + 1 = 1048544.
# Slot offset within sector = (5 mod 4) * 128 = 128.

# IMPORTANT: Forth word definitions must be sent as multi-line
# fragments to stay under the serial buffer limit. Each send()
# must be a syntactically complete fragment or a continuation
# that the interpreter can process.

send('DECIMAL', 0.5)
send('ALSO SURVEYOR', 0.5)
send('USING INSTALL', 1.0)
send('INSTALL DEFINITIONS', 1.0)

# Write cache: 6 slots x (4-byte LBA + 512-byte sector) = 3096
# bytes. Enough for the 4 GPT-WRITE LBAs plus 2 SAFE-WRITE.
WC_SLOTS = 6
WC_STRIDE = 516   # 4 + 512

send(f'VARIABLE WC-N', 0.5)
send(f'CREATE WC-TBL {WC_SLOTS * WC_STRIDE} ALLOT', 1.0)
send(f'WC-TBL {WC_SLOTS * WC_STRIDE} 0 FILL', 1.0)
send(f'0 WC-N !', 0.3)

# WC-FIND ( lba -- addr | 0 )
# Search write cache for a stored sector.
send(': WC-FIND', 0.5)
send(f'  WC-N @ 0> IF', 0.5)
send(f'    WC-N @ 0 DO', 0.5)
send(f'      WC-TBL I {WC_STRIDE} * +', 0.5)
send('      DUP @ ROT DUP ROT = IF', 0.5)
send('        DROP 4 + UNLOOP EXIT', 0.5)
send('      THEN SWAP DROP', 0.5)
send('    LOOP', 0.3)
send('  THEN DROP 0 ;', 0.5)
check('WC-FIND defined', alive())

# WC-STORE ( buf lba -- )
# Store a sector in the write cache. If the LBA already exists,
# overwrite; otherwise append.
send(': WC-STORE DUP WC-FIND DUP IF', 1.0)
send('    SWAP DROP 512 CMOVE', 0.5)
send('  ELSE DROP', 0.3)
send(f'    WC-N @ {WC_SLOTS} >= IF', 0.5)
send('      2DROP EXIT THEN', 0.3)
send(f'    WC-TBL WC-N @ {WC_STRIDE} * +', 0.5)
send('    OVER OVER ! 4 +', 0.5)
send('    ROT SWAP 512 CMOVE DROP', 0.5)
send('    WC-N @ 1+ WC-N ! THEN ;', 0.5)
check('WC-STORE defined', alive())

# Fake writer TWA: ( lba count buf -- flag )
# AHCI-WRITE signature. Stores to write cache.
send(': TWA SWAP DROP OVER WC-STORE', 1.0)
send('  W-LBA ! 0 ;', 0.5)
check('TWA defined', alive())

# Variables for the header fixture.
send('VARIABLE THA-SIGLO VARIABLE THA-SIGHI', 1.0)
send('VARIABLE THA-ALTLO VARIABLE THA-ALTHI', 1.0)
send('VARIABLE THA-HSIZ', 1.0)
send('VARIABLE THA-EPLBA', 1.0)
# Flag to control backup array divergence for decision #4 test.
send('VARIABLE THA-DIVERGE', 1.0)
send('0 THA-DIVERGE !', 0.3)
# Divergence pattern constant — must be defined OUTSIDE colon
# definitions because HEX/DECIMAL are runtime, not IMMEDIATE.
# Inside a colon def, `HEX DEADBEEF` compiles a call to HEX
# and then tries to parse DEADBEEF in the current (decimal) BASE
# → "WORD ?" → STATE corruption → wedge.
send('HEX DEADBEEF CONSTANT DIVERGE-PAT DECIMAL', 1.0)

# Slot patterns for pre-populating the entry sector.
# Slots 4, 6, 7 occupied; slot 5 free (our slot).
# Each occupied slot gets a distinct nonzero pattern.
SLOT_IN_SEC = 5 % 4   # = 1, byte offset 128

# TRA: fake reader for ADD-PARTITION tests.
# Serves:
#   LBA 1 -> primary header (from THA-* variables)
#   LBA ALT -> backup header (MyLBA/AlternateLBA swapped)
#   LBA 2-33 -> entry array (slot sector pre-populated)
#   LBA (ALT-32)..(ALT-1) -> backup entry array
#     (if THA-DIVERGE, backup entry sectors differ)
#   Anything in write cache -> cached content
#   Everything else -> zeroed
#
# Reader signature: ( lba count -- flag )
# Reads into RD-BUF-ADDR.
# We build it in pieces to stay under serial buffer limits.

# First: helper to populate a GPT header in the buffer.
# FILL-HDR ( my-lba alt-lba ep-lba -- )
send(': FILL-HDR', 0.5)
send('  RD-BUF-ADDR @ 512 0 FILL', 0.5)
send('  THA-SIGLO @ RD-BUF-ADDR @ !', 0.5)
send('  THA-SIGHI @ RD-BUF-ADDR @ 4 + !', 0.5)
send('  THA-HSIZ @ RD-BUF-ADDR @ 12 + !', 0.5)
send('  RD-BUF-ADDR @ 24 + !', 0.5)    # MyLBA
send('  RD-BUF-ADDR @ 32 + !', 0.5)    # AlternateLBA
send('  RD-BUF-ADDR @ 72 + ! ;', 0.5)  # PartitionEntryLBA
check('FILL-HDR defined', alive())

# Helper to populate entry sector with 3 occupied slots.
# FILL-ENTS ( -- ) fills RD-BUF-ADDR with entry patterns.
# Slot 0 (offset 0): pattern A1A1A1A1
# Slot 1 (offset 128): all zero (our slot = slot 5 global)
# Slot 2 (offset 256): pattern C3C3C3C3
# Slot 3 (offset 384): pattern D4D4D4D4
#
# Pattern constants MUST be defined outside the colon def:
# HEX/DECIMAL are runtime, not IMMEDIATE, so hex literals
# inside a colon def are parsed in whatever compile-time
# BASE is current (decimal) and fail. Same trap as
# DIVERGE-PAT and bug #20 (PS2-MOUSE).
send('HEX A1A1A1A1 CONSTANT PAT-A DECIMAL', 1.0)
send('HEX C3C3C3C3 CONSTANT PAT-C DECIMAL', 1.0)
send('HEX D4D4D4D4 CONSTANT PAT-D DECIMAL', 1.0)
send(': FILL-ENTS RD-BUF-ADDR @ 512 0 FILL', 1.0)
send('  RD-BUF-ADDR @ 128 0 DO', 0.5)
send('    PAT-A OVER I + ! 4', 0.5)
send('  +LOOP DROP', 0.3)
send('  RD-BUF-ADDR @ 256 + 128 0 DO', 0.5)
send('    PAT-C OVER I + ! 4', 0.5)
send('  +LOOP DROP', 0.3)
send('  RD-BUF-ADDR @ 384 + 128 0 DO', 0.5)
send('    PAT-D OVER I + ! 4', 0.5)
send('  +LOOP DROP ;', 0.5)
check('FILL-ENTS defined', alive())
expect('stack clean after FILL-ENTS', 'DEPTH', 0)

# Now the main reader: TRA ( lba count -- flag )
# Check write cache first, then authored defaults.
send(': TRA DROP', 0.5)
# Check write cache
send('  DUP WC-FIND DUP IF', 0.5)
send('    RD-BUF-ADDR @ 512 CMOVE DROP', 0.5)
send('    0 EXIT THEN DROP', 0.5)
# LBA 1 = primary header
send('  DUP 1 = IF DROP', 0.5)
send(f'    1 {ALT} 2 FILL-HDR 0 EXIT THEN', 0.8)
# LBA ALT = backup header
send(f'  DUP {ALT} = IF DROP', 0.8)
send(f'    {ALT} 1 {ALT - 32} FILL-HDR', 0.8)
send('    0 EXIT THEN', 0.3)
# LBA 3 = our entry sector (slot 5 is in LBA 3)
send('  DUP 3 = IF DROP', 0.5)
send('    FILL-ENTS 0 EXIT THEN', 0.5)
# LBA ALT-32+1 = backup entry sector for slot 5
# Always serves FILL-ENTS (same as primary LBA 3).
# This is GW-BENT — ADD-PARTITION writes it, so
# divergence injected here would be masked by the
# write cache.
send(f'  DUP {ALT - 32 + 1} = IF DROP', 0.8)
send('    FILL-ENTS 0 EXIT THEN', 0.5)
# LBA ALT-32+2 = backup sector for LBA 4.
# Primary LBA 4 is zeroed. Under THA-DIVERGE,
# this returns nonzero — a genuine mismatch on
# a sector ADD-PARTITION never writes, which is
# exactly the case decision #4 exists for.
send(f'  DUP {ALT - 32 + 2} = IF DROP', 0.8)
send('    THA-DIVERGE @ IF', 0.5)
send('      RD-BUF-ADDR @ 512 0 FILL', 0.5)
send('      DIVERGE-PAT', 0.5)
send('      RD-BUF-ADDR @ ! ', 0.5)
send('    ELSE', 0.3)
send('      RD-BUF-ADDR @ 512 0 FILL', 0.5)
send('    THEN 0 EXIT THEN', 0.3)
# All other entry sectors (2-33 and backup): zeroed
send('  DROP RD-BUF-ADDR @ 512 0 FILL', 0.5)
send('  0 ;', 0.3)
check('TRA defined', alive())

# ---- Set up the fixture ----
send('HEX 20494645 THA-SIGLO !', 0.5)
send('54524150 THA-SIGHI ! DECIMAL', 0.5)
send(f'{ALT} THA-ALTLO !  0 THA-ALTHI !', 0.5)
send('92 THA-HSIZ !', 0.3)
send('2 THA-EPLBA !', 0.3)
send(f'{SLOT} FS-SLOT !', 0.3)
send("' TRA SEC-READ-VEC !", 0.5)
send('TR-BUF RD-BUF-ADDR !', 0.5)
send("' TWA SEC-WRITE-VEC !", 0.5)
send('0 WC-N !', 0.3)

# Arm the permit
send('GW-DISARM', 0.3)
expect('arm for ADD-PARTITION', 'GPT-ARM', -1)
check('alive after fixture setup', alive())

# Create the 128-byte entry to add.
# Type GUID: all 0x11, Unique GUID: all 0x22,
# Start LBA: 2048, End LBA: 4095, Attrs: 0, Name: "TEST"
send('CREATE TEST-ENT 128 ALLOT', 1.0)
send('TEST-ENT 128 0 FILL', 0.5)
# Type GUID (16 bytes at +0).
# Define hex values as constants outside any BASE
# dependency — offsets are decimal, values are hex.
send('HEX 11111111 CONSTANT TGUID DECIMAL', 1.0)
send('HEX 22222222 CONSTANT UGUID DECIMAL', 1.0)
send('TGUID TEST-ENT !', 0.5)
send('TGUID TEST-ENT 4 + !', 0.5)
send('TGUID TEST-ENT 8 + !', 0.5)
send('TGUID TEST-ENT 12 + !', 0.5)
# Unique GUID (16 bytes at +16)
send('UGUID TEST-ENT 16 + !', 0.5)
send('UGUID TEST-ENT 20 + !', 0.5)
send('UGUID TEST-ENT 24 + !', 0.5)
send('UGUID TEST-ENT 28 + !', 0.5)
# Start LBA at +32 (8 bytes, low cell only)
send('2048 TEST-ENT 32 + !', 0.5)
send('0 TEST-ENT 36 + !', 0.3)
# End LBA at +40
send('4095 TEST-ENT 40 + !', 0.5)
send('0 TEST-ENT 44 + !', 0.3)
# Name at +56: "T" "E" "S" "T" in UTF-16LE.
# ASCII codes are <128, safe in decimal.
send('84 TEST-ENT 56 + C!', 0.5)
send('69 TEST-ENT 58 + C!', 0.5)
send('83 TEST-ENT 60 + C!', 0.5)
send('84 TEST-ENT 62 + C!', 0.5)
check('TEST-ENT populated', alive())

# ---------------------------------------------------------------
print("\nTest 34: ADD-PARTITION refuses when unarmed")
send('GW-DISARM', 0.3)
send(f'0 WC-N !  {SENTINEL} W-LBA !', 0.5)
expect('refuses unarmed',
       'TEST-ENT ADD-PARTITION', 0)
expect('writer never ran (unarmed)', 'W-LBA @', SENTINEL)
expect('stack clean (unarmed)', 'DEPTH', 0)
check('alive after unarmed refuse', alive())

# ---------------------------------------------------------------
print("\nTest 35: ADD-PARTITION refuses with null entry")
# Re-arm
send("' TRA SEC-READ-VEC !", 0.5)
send("' TWA SEC-WRITE-VEC !", 0.5)
send('TR-BUF RD-BUF-ADDR !', 0.3)
send(f'{SLOT} FS-SLOT !', 0.3)
send('0 WC-N !', 0.3)
expect('re-arm', 'GPT-ARM', -1)
send(f'{SENTINEL} W-LBA !', 0.3)
expect('refuses null entry', '0 ADD-PARTITION', 0)
expect('writer never ran (null)', 'W-LBA @', SENTINEL)
check('alive after null entry', alive())

# ---------------------------------------------------------------
print("\nTest 36: ADD-PARTITION succeeds end-to-end")
# Fresh arm and clean write cache.
send("' TRA SEC-READ-VEC !", 0.5)
send("' TWA SEC-WRITE-VEC !", 0.5)
send('TR-BUF RD-BUF-ADDR !', 0.3)
send(f'{SLOT} FS-SLOT !', 0.3)
send('0 THA-DIVERGE !', 0.3)
send('0 WC-N !', 0.3)
expect('re-arm for e2e', 'GPT-ARM', -1)
expect('stack clean before ADD-PARTITION', 'DEPTH', 0)
r = send('TEST-ENT ADD-PARTITION .', 15.0)
body = body_of(r)
nums = re.findall(r'-?\d+', body)
result = int(nums[-1]) if nums else None
check('ADD-PARTITION returns nonzero (success)',
      result is not None and result != 0,
      f'got {result!r} from {body.strip()[-120:]!r}')
expect('stack clean after ADD-PARTITION', 'DEPTH', 0)
check('alive after ADD-PARTITION', alive())

# ---------------------------------------------------------------
print("\nTest 37: entry sector written correctly")
# Read back the primary entry sector and verify:
# (a) our slot has the TEST-ENT content
# (b) neighbours are unchanged

# Read our slot's type GUID from the written sector.
# Our slot is at offset 128 in the sector (slot 1 within sec).
# The write cache has the sector at GW-ENT (LBA 3).
# We can read it back via the reader.
send(f'3 1 SEC-READ-VEC @ EXECUTE DROP', 1.5)
# Check our entry's type GUID (first 4 bytes of slot 1).
# 0x11111111 and 0x22222222 are positive in signed 32-bit.
expect('slot type GUID[0] correct',
       'RD-BUF-ADDR @ 128 + @', 0x11111111)
expect('slot unique GUID[0] correct',
       'RD-BUF-ADDR @ 144 + @', 0x22222222)
expect('slot start LBA correct',
       'RD-BUF-ADDR @ 160 + @', 2048)
expect('slot end LBA correct',
       'RD-BUF-ADDR @ 168 + @', 4095)
# Neighbours: kernel . prints signed, so bit-31-set patterns
# appear negative. Convert to signed 32-bit for comparison.
# 0xA1A1A1A1 = -1583242847, 0xC3C3C3C3 = -1010580541,
# 0xD4D4D4D4 = -724249388.
expect('neighbour slot 0 intact',
       'RD-BUF-ADDR @ @', -1583242847)
expect('neighbour slot 0 last dword intact',
       'RD-BUF-ADDR @ 124 + @', -1583242847)
# Slot 2 (offset 256)
expect('neighbour slot 2 intact',
       'RD-BUF-ADDR @ 256 + @', -1010580541)
# Slot 3 (offset 384)
expect('neighbour slot 3 intact',
       'RD-BUF-ADDR @ 384 + @', -724249388)
check('alive after entry verify', alive())

# ---------------------------------------------------------------
print("\nTest 38: backup entry sector is byte-identical")
# Read backup entry sector and compare to primary.
# First read primary into IO-BUF for comparison.
send(f'3 1 SEC-READ-VEC @ EXECUTE DROP', 1.5)
send('RD-BUF-ADDR @ IO-BUF 512 CMOVE', 0.8)
# Now read backup
send(f'{ALT - 32 + 1} 1', 1.0)
send('SEC-READ-VEC @ EXECUTE DROP', 1.5)
# Compare all 512 bytes
send(': CMP-SECS 512 0 DO', 0.5)
send('    RD-BUF-ADDR @ I + @', 0.5)
send('    IO-BUF I + @ = 0= IF', 0.5)
send('      0 UNLOOP EXIT THEN', 0.5)
send('  4 +LOOP -1 ;', 0.5)
r = send('CMP-SECS .', 2.0)
body = body_of(r)
nums = re.findall(r'-?\d+', body)
result = int(nums[-1]) if nums else None
check('backup entry sector byte-identical to primary',
      result is not None and result != 0,
      f'got {result!r}')
check('alive after backup compare', alive())

# ---------------------------------------------------------------
print("\nTest 39: header CRCs valid by readback")
# Read back primary header, verify its CRC.
send(': CHK-HDR 1 SEC-READ-VEC @ EXECUTE', 0.5)
send('  IF 0 EXIT THEN', 0.3)
send('  RD-BUF-ADDR @ 12 + @', 0.5)
send('  DUP 92 < IF DROP 0 EXIT THEN', 0.5)
send('  DUP 512 > IF DROP 0 EXIT THEN', 0.5)
send('  RD-BUF-ADDR @ 16 + @ SWAP', 0.5)
send('  0 RD-BUF-ADDR @ 16 + !', 0.5)
send('  RD-BUF-ADDR @ SWAP CRC-BEGIN', 0.5)
send('  CRC-CHUNK CRC-END = ;', 0.5)
check('CHK-HDR defined', alive())

r = send('1 CHK-HDR .', 2.0)
body = body_of(r)
nums = re.findall(r'-?\d+', body)
result = int(nums[-1]) if nums else None
check('primary header CRC valid',
      result is not None and result != 0,
      f'got {result!r}')

r = send(f'{ALT} CHK-HDR .', 2.0)
body = body_of(r)
nums = re.findall(r'-?\d+', body)
result = int(nums[-1]) if nums else None
check('backup header CRC valid',
      result is not None and result != 0,
      f'got {result!r}')
check('alive after header CRC checks', alive())

# ---------------------------------------------------------------
print("\nTest 40: ADD-PARTITION refuses diverged backup array")
# Decision #4: if the backup entry array differs from the
# primary, refuse rather than write a backup header whose CRC
# claims content the backup array doesn't have.
send("' TRA SEC-READ-VEC !", 0.5)
send("' TWA SEC-WRITE-VEC !", 0.5)
send('TR-BUF RD-BUF-ADDR !', 0.3)
send(f'{SLOT} FS-SLOT !', 0.3)
send('-1 THA-DIVERGE !', 0.3)
send('0 WC-N !', 0.3)
expect('re-arm for diverged test', 'GPT-ARM', -1)
r = send('TEST-ENT ADD-PARTITION .', 15.0)
body = body_of(r)
nums = re.findall(r'-?\d+', body)
result = int(nums[-1]) if nums else None
check('ADD-PARTITION refuses diverged backup',
      result is not None and result == 0,
      f'got {result!r} from {body.strip()[-120:]!r}')
send('0 THA-DIVERGE !', 0.3)
check('alive after diverged test', alive())

# ---------------------------------------------------------------
print("\nTest 41: ADD-PARTITION refuses bad HeaderSize")
# HeaderSize out of bounds must refuse. The guard reads +0x0C
# and refuses < 92 or > 512.
send("' TRA SEC-READ-VEC !", 0.5)
send("' TWA SEC-WRITE-VEC !", 0.5)
send('TR-BUF RD-BUF-ADDR !', 0.3)
send(f'{SLOT} FS-SLOT !', 0.3)
send('0 THA-DIVERGE !', 0.3)
send('0 WC-N !', 0.3)
# Set HeaderSize to 0 (below minimum)
send('0 THA-HSIZ !', 0.3)
expect('re-arm (bad hsiz)', 'GPT-ARM', -1)
r = send('TEST-ENT ADD-PARTITION .', 15.0)
body = body_of(r)
nums = re.findall(r'-?\d+', body)
result = int(nums[-1]) if nums else None
check('refuses HeaderSize 0',
      result is not None and result == 0,
      f'got {result!r}')
# Restore and try 1024 (above maximum)
send('0 WC-N !', 0.3)
send('1024 THA-HSIZ !', 0.3)
expect('re-arm (hsiz 1024)', 'GPT-ARM', -1)
r = send('TEST-ENT ADD-PARTITION .', 15.0)
body = body_of(r)
nums = re.findall(r'-?\d+', body)
result = int(nums[-1]) if nums else None
check('refuses HeaderSize 1024',
      result is not None and result == 0,
      f'got {result!r}')
# Restore valid HeaderSize
send('92 THA-HSIZ !', 0.3)
check('alive after HeaderSize tests', alive())

# ---------------------------------------------------------------
# Task 4 (ADD-BOOT-ENTRY) step 0: controller-ready probe and the
# G1 baseline/compare pair, red-first.
#
# MEM-BASE is install.fth's load-time snapshot of the bootloader's
# MEMDISK_BASE cell -- a ForthOS-owned variable.  Tests poke the
# snapshot, never the live kernel cell at 0x28098, so the block
# subsystem is untouched no matter what these tests do.  Saved on
# entry, restored at the end.
# ---------------------------------------------------------------

# Fixture: L0-IMG is the fake disk's LBA 0 -- realistic protective
# MBR shape: zeros, one nonzero interior byte, 55 AA at 510/511.
send('CREATE L0-IMG 512 ALLOT', 1.0)
send('L0-IMG 512 0 FILL', 0.5)
send('238 L0-IMG 440 + C!', 0.3)
send('85 L0-IMG 510 + C!  170 L0-IMG 511 + C!', 0.5)
# GRD: good reader -- flag=0, serves L0-IMG.
send(': GRD 2DROP L0-IMG TR-BUF 512 CMOVE 0 ;', 1.0)
# BRD: the fail-open hazard -- flag=1 AND an all-zero buffer,
# exactly what the uninitialized AHCI controller did on iron.
send(': BRD 2DROP TR-BUF 512 0 FILL 1 ;', 1.0)
# NCMP: a deliberately BROKEN comparator that ignores the flag
# discipline -- raw buffer compare, used to prove G1-R0 bites.
send(': NCMP 512 0 DO TR-BUF I + C@ LBA0-SAVE I + C@', 0.5)
send('  = 0= IF 0 UNLOOP EXIT THEN LOOP -1 ;', 1.0)
send('VARIABLE MS-SAVE', 0.5)
send('MEM-BASE @ MS-SAVE !', 0.3)

# ---------------------------------------------------------------
print("\nTest 42: ABE-READY? control-then-one-variable")
# Control: everything present -> ready.
send("' GRD SEC-READ-VEC !  TR-BUF RD-BUF-ADDR !", 0.5)
send('4096 MEM-BASE !', 0.3)
expect('control: probe passes', 'ABE-READY?', -1)
# One variable at a time.
send('0 SEC-READ-VEC !', 0.3)
expect('refuses: reader unbound', 'ABE-READY?', 0)
send("' GRD SEC-READ-VEC !  0 RD-BUF-ADDR !", 0.5)
expect('refuses: no buffer', 'ABE-READY?', 0)
send('TR-BUF RD-BUF-ADDR !  0 MEM-BASE !', 0.5)
expect('refuses: no memdisk source', 'ABE-READY?', 0)
send('4096 MEM-BASE !', 0.3)
send("' BRD SEC-READ-VEC !", 0.3)
expect('refuses: read flag=1', 'ABE-READY?', 0)
expect('stack clean after probe matrix', 'DEPTH', 0)
check('alive after probe matrix', alive())

# ---------------------------------------------------------------
print("\nTest 43: G1-R0 -- fail-open double-zero must error")
# Both the baseline read and the after read return flag=1 with a
# zero buffer.  The gate must ERROR (0), never report identical.
send("' BRD SEC-READ-VEC !  4096 MEM-BASE !", 0.5)
expect('capture refuses on flag=1', 'LBA0-BASELINE', 0)
expect('no trusted baseline stored', 'LBA0-OK? @', 0)
expect('compare refuses, not identical', 'LBA0-SAME?', 0)
# Red proof that the test bites: simulate a broken gate that
# stored the untrusted zero buffer anyway.  The raw compare then
# reports identical (zero==zero) -- the false pass G1-R0 exists
# to prevent.  The real gate still refuses on the same state.
send('TR-BUF LBA0-SAVE 512 CMOVE', 0.5)
expect('broken gate WOULD pass (red)', 'NCMP', -1)
expect('real gate still refuses', 'LBA0-SAME?', 0)
# Control pair: with a good read the same capture succeeds and
# the buffer carries the signature (the iron sequence after
# AHCI-INIT).
send("' GRD SEC-READ-VEC !", 0.3)
expect('control: capture passes', 'LBA0-BASELINE', -1)
expect('control: baseline trusted', 'LBA0-OK? @', -1)
expect('control: compare identical', 'LBA0-SAME?', -1)
expect('stack clean after G1-R0', 'DEPTH', 0)
check('alive after G1-R0', alive())

# ---------------------------------------------------------------
print("\nTest 44: G1-R1 -- comparator detects one byte")
# Poke at offset 0x1C0 (448) BY INTENT: cell 112 of 128, late in
# the sector.  This doubles as full-scan proof -- a compare loop
# that ran once (or stopped early) would miss it, so red->green
# here also certifies the DO loop covers the whole sector.
expect('pre-poke: identical', 'LBA0-SAME?', -1)
send('123 L0-IMG 448 + C!', 0.3)
expect('one byte poked: MISMATCH', 'LBA0-SAME?', 0)
send('0 L0-IMG 448 + C!', 0.3)
expect('restored: identical again', 'LBA0-SAME?', -1)
expect('stack clean after G1-R1', 'DEPTH', 0)
check('alive after G1-R1', alive())

# ---------------------------------------------------------------
print("\nTest 45: G1-R2 -- captured baseline is real, not zero")
expect('baseline byte 510 is 0x55', 'LBA0-SAVE 510 + C@', 85)
expect('baseline byte 511 is 0xAA', 'LBA0-SAVE 511 + C@', 170)
expect('baseline interior nonzero', 'LBA0-SAVE 440 + C@', 238)

expect('stack clean after G1-R2', 'DEPTH', 0)

# Restore the snapshot to its load-time value.
send('MS-SAVE @ MEM-BASE !', 0.3)
expect('MEM-BASE restored', 'MEM-BASE @ MS-SAVE @ =', -1)
check('alive after step-0 suite', alive())

# ---------------------------------------------------------------
# Task 4 step 3: BUILD-VBR -- the Decision A bake, red-first.
# The fixture template and the gate share ONE offset constant
# (VBR-LBA-OFF, defined Forth-side): these tests never hardcode
# the byte offset, so the fixture and the future assembled
# template cannot drift from the gate without the gate noticing.
# ---------------------------------------------------------------

print("\nTest 46: G5-R3 -- the bake fired (sentinel de-alias)")
# Third leg of the drift triangle: the Forth constant must match
# the ASSEMBLED template, derived from the artifact at runtime --
# never a hardcoded offset.  The template the installer bakes is
# the VARIANT (vbr.bin), so the offset derives from it; boot.bin
# keeps its own frozen gate (Test 46b).  DAP shape: size 10 00,
# reserved 00, count (varies), dest 0x7E00, seg 0, start LBA
# dd VBR-SENTINEL (DEADBEEF, sentinel-baked), high dd 0.
with open('build/vbr.bin', 'rb') as f:
    vbrbin = f.read()
dap_re = re.compile(
    b'\x10\x00..\x00\x7e\x00\x00'
    b'\xef\xbe\xad\xde\x00\x00\x00\x00', re.DOTALL)
dap_hits = [m.start() for m in dap_re.finditer(vbrbin)]
check('exactly one sentinel DAP in assembled vbr.bin',
      len(dap_hits) == 1, f'matches at {dap_hits}')
DAP_LBA_OFF = dap_hits[0] + 8 if dap_hits else None
if DAP_LBA_OFF is not None:
    expect('VBR-LBA-OFF matches assembled vbr.bin',
           'VBR-LBA-OFF', DAP_LBA_OFF)

# Fixture template: zeros, one code-ish byte, the sentinel in
# the DAP start-LBA field, 55 AA at 510/511.
send('CREATE VBR-FIX 512 ALLOT', 1.0)
send('VBR-FIX 512 0 FILL', 0.5)
send('235 VBR-FIX C!', 0.3)
send('VBR-SENTINEL VBR-FIX VBR-LBA-OFF + !', 0.5)
send('85 VBR-FIX 510 + C!  170 VBR-FIX 511 + C!', 0.5)
send('VBR-FIX VBR-TPL !', 0.3)
send(f'{BASE} OWN-BASE !  {LEN} OWN-LEN !', 0.5)

# Red: an UNPATCHED copy (a bake that never fired) must be
# caught.  Simulate by copying the template without baking.
send('VBR-TPL @ VBR-IMG 512 CMOVE', 0.5)
expect('unpatched image still reads the sentinel',
       'VBR-IMG VBR-LBA-OFF + @ VBR-SENTINEL =', -1)
# A broken gate that only checks "field nonzero" WOULD pass on
# the sentinel -- the false pass G5-R3 exists to prevent.
expect('broken nonzero-check WOULD pass (red)',
       'VBR-IMG VBR-LBA-OFF + @ 0= 0=', -1)
expect('real gate refuses the unpatched image', 'VBR-BAKED?', 0)

# Control: the real build.
expect('BUILD-VBR succeeds', 'BUILD-VBR', -1)
expect('baked field = OWN-BASE + KERNEL-OFFSET',
       'VBR-IMG VBR-LBA-OFF + @', BASE + 1)
expect('baked field is not the sentinel',
       'VBR-IMG VBR-LBA-OFF + @ VBR-SENTINEL =', 0)
expect('gate passes on the baked image', 'VBR-BAKED?', -1)
# The bake patches the COPY, never the template -- a template
# with a real LBA baked in would poison every later build.
expect('template still holds the sentinel',
       'VBR-FIX VBR-LBA-OFF + @ VBR-SENTINEL =', -1)

# One variable at a time: each refusal, and no refusal may
# scribble on the previously built image.
send('0 VBR-TPL !', 0.3)
expect('refuses: no template', 'BUILD-VBR', 0)
send('VBR-FIX VBR-TPL !  0 OWN-BASE !', 0.5)
expect('refuses: extent not claimed', 'BUILD-VBR', 0)
expect('refusals left the built image untouched',
       'VBR-IMG VBR-LBA-OFF + @', BASE + 1)
send(f'{BASE} OWN-BASE !', 0.3)
expect('stack clean after G5-R3', 'DEPTH', 0)
check('alive after G5-R3', alive())

# ---------------------------------------------------------------
print("\nTest 46b: proven loader frozen; loader DAPs disjoint")
# boot.bin is the iron-proven memdisk loader. Its DAP is dd 1 at
# offset 467 -- FROZEN facts about a shipped artifact, so hardcoding
# is correct here: any change to either is the alarm firing, and
# the fix is to justify touching the proven loader, not to update
# this number. Disjoint patterns (01 00 00 00 vs EF BE AD DE) are
# what let the two gates attribute a failure to the right binary.
with open('build/boot.bin', 'rb') as f:
    bootbin = f.read()
legacy_re = re.compile(
    b'\x10\x00..\x00\x7e\x00\x00'
    b'\x01\x00\x00\x00\x00\x00\x00\x00', re.DOTALL)
legacy_hits = [m.start() for m in legacy_re.finditer(bootbin)]
check('boot.bin: exactly one dd-1 DAP (proven loader intact)',
      len(legacy_hits) == 1, f'matches at {legacy_hits}')
check('boot.bin: DAP LBA still at frozen offset 467',
      bool(legacy_hits) and legacy_hits[0] + 8 == 467,
      f'moved to {legacy_hits[0] + 8 if legacy_hits else None}')
# Disjointness, both directions: a sentinel DAP appearing in
# boot.bin means someone edited the proven loader toward the
# variant; a dd-1 DAP in vbr.bin means an unbaked-template boot
# could silently read LBA 1 instead of dying loudly.
check('boot.bin: zero sentinel DAPs',
      len(dap_re.findall(bootbin)) == 0)
check('vbr.bin: zero dd-1 DAPs',
      len(legacy_re.findall(vbrbin)) == 0)

# ---------------------------------------------------------------
print("\nTest 47: G5-R4 -- built image is chainloadable (55 AA)")
expect('control: rebuild passes', 'BUILD-VBR', -1)
expect('byte 510 is 0x55', 'VBR-IMG 510 + C@', 85)
expect('byte 511 is 0xAA', 'VBR-IMG 511 + C@', 170)
expect('gate passes on the signed image', 'VBR-SIGNED?', -1)
# Red: strip the signature from the built image.
send('0 VBR-IMG 510 + C!', 0.3)
expect('unsigned image: gate refuses', 'VBR-SIGNED?', 0)
send('85 VBR-IMG 510 + C!', 0.3)
expect('restored: gate passes again', 'VBR-SIGNED?', -1)
# An unsigned TEMPLATE must refuse at build time -- a correct-
# but-unsigned VBR would otherwise surface only at iron G6.
send('0 VBR-FIX 510 + C!', 0.3)
expect('refuses: unsigned template', 'BUILD-VBR', 0)
send('85 VBR-FIX 510 + C!', 0.3)
expect('control: signed template builds again', 'BUILD-VBR', -1)
expect('stack clean after G5-R4', 'DEPTH', 0)
check('alive after G5-R4', alive())

# ---------------------------------------------------------------
# Task 4 flow steps 1-7, Landing A: step-1 size check plus the
# G2 (ESP sampled tripwire) and G3 (GPT CRC tripwire) gate pairs.
# ---------------------------------------------------------------

print("\nTest 48: step 1 -- kernel fits the claimed extent")
# Drift leg: KERNEL-SECTORS must match the built kernel image,
# derived from the artifact at runtime, never hardcoded.
ksize = os.path.getsize('build/kernel.bin')
check('kernel.bin is whole sectors', ksize % 512 == 0, f'{ksize}')
expect('KERNEL-SECTORS matches build/kernel.bin',
       'KERNEL-SECTORS', ksize // 512)
# Boundary: KERNEL-OFFSET + KERNEL-SECTORS sectors are needed.
need = ksize // 512 + 1
send(f'{need} OWN-LEN !', 0.3)
expect('exactly sufficient extent fits', 'ABE-FITS?', -1)
send(f'{need - 1} OWN-LEN !', 0.3)
expect('one sector short refuses', 'ABE-FITS?', 0)
send('0 OWN-LEN !', 0.3)
expect('unclaimed extent refuses', 'ABE-FITS?', 0)
send(f'{LEN} OWN-LEN !', 0.3)
expect('stack clean after step-1 checks', 'DEPTH', 0)
check('alive after step-1 checks', alive())

# ---------------------------------------------------------------
# Shared fixture for G2/G3: ERD ( lba n -- f ) serves ANY lba as
# a full sector of its own low byte, so every sector has
# distinct, derivable content.  E-PLBA/E-POKE overlay one byte
# of one chosen lba -- the poke knob for both tripwires.
# -1 E-PLBA = overlay off.
send('VARIABLE E-PLBA  -1 E-PLBA !', 0.5)
send('VARIABLE E-POKE', 0.3)
send(': ERD DROP', 0.5)
send('  DUP 255 AND TR-BUF 512 ROT FILL', 0.8)
send('  DUP E-PLBA @ = IF', 0.5)
send('    E-POKE @ TR-BUF C! THEN DROP 0 ;', 0.8)

# ---------------------------------------------------------------
print("\nTest 49: G2 -- ESP sampled tripwire, red-first")
send("' ERD SEC-READ-VEC !  TR-BUF RD-BUF-ADDR !", 0.5)
send('100 ESP-BASE !  64 ESP-LEN !', 0.5)
expect('control: baseline captures', 'ESP-BASELINE', -1)
expect('control: samples identical', 'ESP-SAME?', -1)
# The sample list is derived from the artifact under test.
samples = [val(f'{i} ESP-SAMPLE')[0] for i in range(4)]
check('sample 0 is the first sector', samples[0] == 100,
      f'{samples}')
check('sample 1 is the last sector', samples[1] == 163,
      f'{samples}')
check('interior samples inside the extent',
      all(s is not None and 100 < s < 163 for s in samples[2:]),
      f'{samples}')
if samples[2] is not None:
    expect('samples reproducible', '2 ESP-SAMPLE', samples[2])
    # Red: poke a SAMPLED sector -> must be caught.
    send(f'{samples[2]} E-PLBA !  77 E-POKE !', 0.5)
    expect('poked sampled sector: MISMATCH', 'ESP-SAME?', 0)
    send('-1 E-PLBA !', 0.3)
    expect('restored: identical again', 'ESP-SAME?', -1)
    # Tripwire honesty: an UNSAMPLED sector is NOT covered --
    # by design (static-assurance section: do not tighten).
    uns = next(l for l in range(101, 163) if l not in samples)
    send(f'{uns} E-PLBA !  77 E-POKE !', 0.5)
    expect('unsampled poke passes (tripwire, by design)',
           'ESP-SAME?', -1)
    send('-1 E-PLBA !', 0.3)
# G2-R0: double-zero must error, never report identical.
send("' BRD SEC-READ-VEC !", 0.3)
expect('capture refuses on flag=1', 'ESP-BASELINE', 0)
expect('no trusted baseline stored', 'ESP-OK? @', 0)
expect('compare refuses, not identical', 'ESP-SAME?', 0)
send("' ERD SEC-READ-VEC !", 0.3)
# One variable at a time.
send('0 ESP-BASE !', 0.3)
expect('refuses: ESP undeclared', 'ESP-BASELINE', 0)
send('100 ESP-BASE !  3 ESP-LEN !', 0.5)
expect('refuses: ESP too small to sample', 'ESP-BASELINE', 0)
send('64 ESP-LEN !', 0.3)
expect('re-arm baseline for later tests', 'ESP-BASELINE', -1)
expect('stack clean after G2', 'DEPTH', 0)
check('alive after G2', alive())

# ---------------------------------------------------------------
print("\nTest 50: G3 -- GPT CRC tripwire, red-first")
send("' ERD SEC-READ-VEC !  TR-BUF RD-BUF-ADDR !", 0.5)
send('-1 E-PLBA !', 0.3)
expect('control: baseline captures', 'GPT-BASELINE', -1)
expect('control: sum stable', 'GPT-SAME?', -1)
# Red: one byte in one entry sector -> caught.
send('7 E-PLBA !  99 E-POKE !', 0.5)
expect('poked entry sector: MISMATCH', 'GPT-SAME?', 0)
send('-1 E-PLBA !', 0.3)
expect('restored: identical again', 'GPT-SAME?', -1)
# The header sector (LBA 1) is inside the sum too.
send('1 E-PLBA !  99 E-POKE !', 0.5)
expect('poked header sector: MISMATCH', 'GPT-SAME?', 0)
send('-1 E-PLBA !', 0.3)
# Double-zero: flag=1 reader -> error, never identical.
send("' BRD SEC-READ-VEC !", 0.3)
expect('capture refuses on flag=1', 'GPT-BASELINE', 0)
expect('no trusted baseline stored', 'GPT-OK? @', 0)
expect('compare refuses, not identical', 'GPT-SAME?', 0)
send("' ERD SEC-READ-VEC !", 0.3)
expect('re-arm baseline', 'GPT-BASELINE', -1)
expect('stack clean after G3', 'DEPTH', 0)
check('alive after G3', alive())

# ---------------------------------------------------------------
# Task 4 flow steps 4-7, Landing B: the whole word.
# Fixture: sparse 8-slot watch list.  OWR counts every write,
# fail-injects at O-FAIL, and records watched sectors' bytes;
# ORD serves LBA 0 (L0-IMG), watched sectors (recorded bytes),
# and lba&255 fill for everything else (ESP + GPT).
# G1-FLIP corrupts LBA 0 only once O-CNT > 0: the baseline
# reads clean, the step-7 recheck reads dirty -- the serial-
# safe equivalent of a concurrent poke mid-install.
# G5-FLIP corrupts only watched (own-extent) readbacks, so a
# 0 return under it is attributable to step 6, not step 7.
# NOTE: the kernel "image" is live RAM at MEM-BASE+512 and the
# sample checks compare readback against that same source --
# self-consistent by construction.  They validate the WRITE
# PATH; image content is proven only at iron G6.
print("\nTest 51: ADD-BOOT-ENTRY whole-word matrix")
send('CREATE O-WLBA 32 ALLOT', 1.0)
send('O-WLBA 32 255 FILL', 0.5)
send('CREATE O-WBUF 4096 ALLOT', 1.0)
send('VARIABLE O-CNT   0 O-CNT !', 0.5)
send('VARIABLE O-FAIL  -1 O-FAIL !', 0.5)
send('VARIABLE G1-FLIP 0 G1-FLIP !', 0.5)
send('VARIABLE G5-FLIP 0 G5-FLIP !', 0.5)
# WL-FIND ( lba -- i -1 | 0 )
send(': WL-FIND 8 0 DO DUP O-WLBA I 4 * + @ = IF', 0.8)
send('  DROP I -1 UNLOOP EXIT THEN LOOP DROP 0 ;', 0.8)
# OWR ( lba n buf -- f )
send(': OWR 1 O-CNT +!  SWAP DROP', 0.8)
send('  OVER O-FAIL @ = IF 2DROP 1 EXIT THEN', 0.8)
send('  SWAP WL-FIND IF', 0.5)
send('    512 * O-WBUF + 512 CMOVE ELSE DROP THEN 0 ;', 1.0)
# ORD ( lba n -- f )
send(': ORD DROP', 0.5)
send('  DUP 0= IF DROP L0-IMG TR-BUF 512 CMOVE', 1.0)
send('    G1-FLIP @ O-CNT @ 0= 0= AND IF', 0.8)
send('      TR-BUF C@ 1 XOR TR-BUF C! THEN 0 EXIT THEN', 1.0)
send('  DUP WL-FIND IF', 0.5)
send('    SWAP DROP 512 * O-WBUF + TR-BUF 512 CMOVE', 1.0)
send('    G5-FLIP @ IF', 0.5)
send('      TR-BUF C@ 1 XOR TR-BUF C! THEN 0 EXIT THEN', 1.0)
send('  255 AND TR-BUF 512 ROT FILL 0 ;', 1.0)

# Bind everything; extent exactly holds VBR + kernel.
send("' ORD SEC-READ-VEC !  TR-BUF RD-BUF-ADDR !", 0.5)
send("' OWR SEC-WRITE-VEC !", 0.5)
send(f'{BASE} OWN-BASE !  225 OWN-LEN !', 0.5)
send('4096 MEM-BASE !', 0.3)
send('100 ESP-BASE !  64 ESP-LEN !', 0.5)
send('VBR-FIX VBR-TPL !', 0.5)

# The watch list is derived from the artifact: sample sectors
# come from KRN-SAMPLE, never Python arithmetic on constants.
kfirst = BASE + 1
s2 = val('2 KRN-SAMPLE')[0]
s3 = val('3 KRN-SAMPLE')[0]
last = val('1 KRN-SAMPLE')[0]
check('interior samples derivable',
      s2 is not None and s3 is not None and last is not None,
      f'{[s2, s3, last]}')
watches = [BASE, kfirst,
           kfirst + (last or 0),
           kfirst + (s2 or 0), kfirst + (s3 or 0)]
for i, lba in enumerate(watches):
    send(f'{lba} O-WLBA {i * 4} + !', 0.3)

# Row 1: control.
send('0 O-CNT !', 0.3)
v, raw = val('ADD-BOOT-ENTRY', 8.0)
check('control: whole word returns -1', v == -1,
      raw.strip()[-90:])
expect('control: 225 writes (224 kernel + VBR)', 'O-CNT @', 225)
expect('control: VBR slot has the bake',
       'O-WBUF VBR-LBA-OFF + @', kfirst)
expect('control: VBR slot signed 55', 'O-WBUF 510 + C@', 85)
expect('control: VBR slot signed AA', 'O-WBUF 511 + C@', 170)
# First kernel sector recorded = its RAM source byte.
src0 = val('MEM-BASE @ 512 + C@')[0]
if src0 is not None:
    expect('control: kernel slot matches source',
           'O-WBUF 512 + C@', src0)
expect('stack clean after control', 'DEPTH', 0)

# Row 2: step-0 refusal (one variable: reader unbound).
send('0 O-CNT !  0 SEC-READ-VEC !', 0.5)
expect('refuses: reader unbound', 'ADD-BOOT-ENTRY', 0)
expect('refusal wrote nothing', 'O-CNT @', 0)
send("' ORD SEC-READ-VEC !", 0.3)

# Row 3: step-1 refusal (one variable: extent one short).
send('224 OWN-LEN !', 0.3)
expect('refuses: extent too small', 'ADD-BOOT-ENTRY', 0)
expect('small extent wrote nothing', 'O-CNT @', 0)
send('225 OWN-LEN !', 0.3)
expect('refusals left OWN-BASE alone', 'OWN-BASE @', BASE)

# Row 4: mid-write fault -> ABORT, host untouched.
send('0 O-CNT !  O-WBUF 512 0 FILL', 0.5)
fail_lba = kfirst + 51
send(f'{fail_lba} O-FAIL !', 0.3)
r = send('ADD-BOOT-ENTRY', 6.0)
check('mid-write fault aborts loudly', 'write failed' in r,
      r.strip()[-90:])
check('alive after abort', alive())
expect('writes stopped at the fault', 'O-CNT @',
       fail_lba - kfirst + 1)
expect('VBR never written in this run', 'O-WBUF 510 + C@', 0)
send('-1 O-FAIL !', 0.3)
# The spec's own matrix line: G1+G2+G3 still show the host
# untouched after an aborted install.  The baselines armed at
# step 2 live in variables, so they survive the ABORT.
expect('host untouched: G1 still -1', 'LBA0-SAME?', -1)
expect('host untouched: G2 still -1', 'ESP-SAME?', -1)
expect('host untouched: G3 still -1', 'GPT-SAME?', -1)
expect('stack clean after abort row', 'DEPTH', 0)

# Row 5: G1-live -- LBA 0 changes after the writes begin.
send('0 O-CNT !  -1 G1-FLIP !', 0.5)
v, raw = val('ADD-BOOT-ENTRY', 8.0)
check('G1-live poke: returns 0', v == 0, raw.strip()[-90:])
expect('all writes had completed', 'O-CNT @', 225)
send('0 G1-FLIP !', 0.3)

# Row 6: G5-live -- own-extent readback corrupted; LBA 0,
# ESP, and GPT stay clean, so this 0 is step 6's.
send('0 O-CNT !  -1 G5-FLIP !', 0.5)
v, raw = val('ADD-BOOT-ENTRY', 8.0)
check('G5-live poke: returns 0', v == 0, raw.strip()[-90:])
send('0 G5-FLIP !', 0.3)

# Recovery: the control row passes again untouched.
send('0 O-CNT !', 0.3)
v, raw = val('ADD-BOOT-ENTRY', 8.0)
check('control again after the matrix', v == -1,
      raw.strip()[-90:])
expect('stack clean after matrix', 'DEPTH', 0)
check('alive after matrix', alive())

send('ONLY FORTH DEFINITIONS DECIMAL', 1.0)

# ---------------------------------------------------------------
print("\nTest 52: canonical GUID constants (frozen 2026-08-05)")
# Re-establish search order: ALSO SURVEYOR before USING INSTALL
# matches the convention used throughout this suite (lines 373-374,
# 950-951). ONLY FORTH above evicted INSTALL; restore it now so
# the constants are findable.
send('ALSO SURVEYOR', 0.5)
send('USING INSTALL', 1.0)
# Cells must equal the spec's frozen values. HEX is sticky over
# serial: val() prefixes DECIMAL, but the constants are compared
# as decimal integers derived from the hex cells here in Python.
FOS_TG = [0x4E011D24, 0x45E89E20, 0xEB8549BC, 0x3285C614]
FOS_UG = [0x32BA60FB, 0x4D4C4548, 0x80FB39A4, 0x312B57CE]


def s32(x):
    """Kernel prints cells signed; compare in signed space."""
    return x - 0x100000000 if x >= 0x80000000 else x


for i, v in enumerate(FOS_TG):
    expect(f'FOS-TG{i}', f'FOS-TG{i}', s32(v))
for i, v in enumerate(FOS_UG):
    expect(f'FOS-UG{i}', f'FOS-UG{i}', s32(v))
expect('stack clean after constants', 'DEPTH', 0)

# ---------------------------------------------------------------
print("\nTest 53: GUID-ABSENT? (scan discipline)")
# Fresh reader: G6R ( lba count -- flag ).
#   G-MODE 0: all entry sectors read clean (zeros), flag=0
#   G-MODE 1: LBA 33 carries FOS-UNIQ cells at offset 384
#             (slot 127 -- last entry of last sector: proves
#             comparator AND loop bounds in one test)
#   G-MODE 2: fail-open -- flag=1, buffer left ALL-ZERO (the
#             observed AHCI fail-open shape); a scanner that
#             trusts the buffer sees "no dup" and lies
send('VARIABLE G-MODE  0 G-MODE !', 0.5)
send('CREATE G6-BUF 512 ALLOT', 0.5)
send(': G6R DROP', 0.5)
send('  G6-BUF 512 0 FILL', 0.5)
send('  G-MODE @ 2 = IF DROP 1 EXIT THEN', 0.5)
send('  G-MODE @ 1 = IF 33 = IF', 0.5)
send('    FOS-UG0 G6-BUF 384 + 16 + !', 0.5)
send('    FOS-UG1 G6-BUF 384 + 20 + !', 0.5)
send('    FOS-UG2 G6-BUF 384 + 24 + !', 0.5)
send('    FOS-UG3 G6-BUF 384 + 28 + !', 0.5)
send('  THEN ELSE DROP THEN 0 ;', 0.5)
check('G6R defined', alive())
send("' G6R SEC-READ-VEC !", 0.5)
send('G6-BUF RD-BUF-ADDR !', 0.5)

expect('clean map: absent', 'GUID-ABSENT?', -1)
send('1 G-MODE !', 0.3)
expect('dup in slot 127: refuses', 'GUID-ABSENT?', 0)
send('2 G-MODE !', 0.3)
expect('fail-open read: refuses', 'GUID-ABSENT?', 0)
send('0 G-MODE !', 0.3)
send('0 SEC-READ-VEC !', 0.3)
expect('unbound reader: refuses', 'GUID-ABSENT?', 0)
send("' G6R SEC-READ-VEC !", 0.3)
expect('stack clean after scan tests', 'DEPTH', 0)

# ---------------------------------------------------------------
print("\nTest 54: MAKE-OWN-ENT composer")
# Extent source is OWN-BASE/OWN-LEN (FREE-EXTENT's post-claim
# contract). Composer-only seam: ADD-PARTITION still accepts any
# entry (deliberate operator power); uniqueness holds only via
# this composer, which the runbook uses unconditionally.
# NOTE: each expect below RE-INVOKES MAKE-OWN-ENT (full rescan +
# recompose). Keep G-MODE=0 and OWN-BASE/OWN-LEN frozen through
# this whole block, or the asserts test a different composition.
send('0 OWN-BASE !  0 OWN-LEN !', 0.5)
expect('refuses unclaimed extent', 'MAKE-OWN-ENT', 0)
send('534528 OWN-BASE !  225 OWN-LEN !', 0.5)
send('1 G-MODE !', 0.3)
expect('refuses when dup present', 'MAKE-OWN-ENT', 0)
send('0 G-MODE !', 0.3)
v, _ = val('MAKE-OWN-ENT')
check('composes on clean map (nonzero entry)',
      v is not None and v != 0, f'got {v!r}')
# Field asserts against known offsets, via the entry address.
expect('type cell 0', 'MAKE-OWN-ENT @', s32(0x4E011D24))
expect('type cell 3', 'MAKE-OWN-ENT 12 + @', s32(0x3285C614))
expect('uniq cell 0', 'MAKE-OWN-ENT 16 + @', s32(0x32BA60FB))
expect('uniq cell 3', 'MAKE-OWN-ENT 28 + @', s32(0x312B57CE))
expect('start LBA lo', 'MAKE-OWN-ENT 32 + @', 534528)
expect('start LBA hi', 'MAKE-OWN-ENT 36 + @', 0)
expect('end LBA lo', 'MAKE-OWN-ENT 40 + @', 534528 + 225 - 1)
expect('end LBA hi', 'MAKE-OWN-ENT 44 + @', 0)
# Name "FORTHOS" UTF-16LE at +56
for i, ch in enumerate('FORTHOS'):
    expect(f'name[{i}]={ch}',
           f'MAKE-OWN-ENT 56 + {2 * i} + C@', ord(ch))
expect('name terminator', 'MAKE-OWN-ENT 70 + C@', 0)
expect('attrs zero', 'MAKE-OWN-ENT 48 + @', 0)
expect('stack clean after composer', 'DEPTH', 0)

# ---------------------------------------------------------------
print("\nTest 55: GPT-ARM refuses when FS-SLOT = -1 (sentinel)")
# The sentinel value is -1, which is 0< true, so GPT-ARM's
# existing signed lower-bound check catches it without any
# guard change. Pinning this proves the sentinel works as a
# safety net for the un-run FREE-SLOT case (Bug #33).
good_header()
send('DECIMAL -1 FS-SLOT !', 0.5)
expect('GPT-ARM refuses sentinel FS-SLOT', 'GPT-ARM', 0)
expect('permit fully disarmed', 'GW-ARMED @', 0)
expect('stack clean', 'DEPTH', 0)
check('alive after sentinel GPT-ARM', alive())

# ---------------------------------------------------------------
print("\nTest 56: FREE-SLOT consistency gate")
# Sub-case (i): all-free array + survey says N>0 -> refuses.
# The TRS reader returns an all-zero buffer when TS-USED=0,
# simulating an entry array with no occupied slots. MAP-OK=true
# and PART-N=5 simulates a survey that saw 5 partitions.
# The gate must refuse: the scan saw nothing but the survey
# did, so the scan is blind.
send("' TRS SEC-READ-VEC !  TR-BUF RD-BUF-ADDR !", 0.5)
send('DECIMAL -1 TS-ERRLBA !  0 TS-USED !', 0.5)
send('-1 MAP-OK !  5 PART-N !', 0.5)
arm_slot()
expect('gate: all-free + survey N>0 -> refuses',
       'FREE-SLOT', 0)
expect('FS-SLOT untouched (gate refusal)', 'FS-SLOT @',
       SLOT_SENTINEL)
expect('stack clean (gate refusal)', 'DEPTH', 0)
check('alive after gate refusal', alive())

# Sub-case (ii): all-free array + survey genuinely empty
# (trusted, 0 partitions) -> slot 0 claimed. This is the
# legitimately-empty-disk case. Old Test 23 exercised
# this path implicitly; under the gate it still works because
# occupied=0 AND PART-N=0, so the gate does not fire.
send('-1 MAP-OK !  0 PART-N !', 0.5)
send('DECIMAL 0 TS-USED !', 0.5)
arm_slot()
expect('gate: all-free + survey empty -> succeeds',
       'FREE-SLOT', -1)
expect('FS-SLOT = 0 (empty disk)', 'FS-SLOT @', 0)
expect('stack clean (empty disk)', 'DEPTH', 0)
check('alive after empty disk', alive())

# Sub-case (iii): survey untrusted/absent -> refuses.
# MAP-OK=0 makes MAP-TRUSTED? return false.
send('0 MAP-OK !  0 PART-N !', 0.5)
send('DECIMAL 0 TS-USED !', 0.5)
arm_slot()
expect('gate: untrusted survey -> refuses',
       'FREE-SLOT', 0)
expect('FS-SLOT untouched (untrusted)', 'FS-SLOT @',
       SLOT_SENTINEL)
expect('stack clean (untrusted)', 'DEPTH', 0)
check('alive after untrusted survey refusal', alive())

print(f'\nPassed: {PASS}/{PASS + FAIL}')
s.close()
sys.exit(0 if FAIL == 0 else 1)
