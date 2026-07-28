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
import re
import socket
import sys
import time

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

# ---------------------------------------------------------------
print("\nTest 2: no raw absolute writer is nameable in INSTALL")
# The confinement claim: the only route to the disk from inside
# this vocabulary is the vector.  Checked by name resolution in
# the live search order, before the test defines anything of its
# own, so the answer describes the shipped vocabulary.
send(': DEF? WORD FIND NIP ; ', 1.5)
for raw_writer in ('AHCI-WRITE', 'ATA-WRITE-SECTOR', 'SECTOR-WRITE',
                   'LBA-WRITE', 'RAW-WRITE'):
    expect(f'{raw_writer} not nameable', f'DEF? {raw_writer}', 0)
# ...and the guard itself IS nameable, so the check above is not
# just measuring a broken DEF?.
v, raw = val('DEF? SAFE-WRITE')
check('DEF? resolves SAFE-WRITE (control)', v is not None and v != 0,
      f'got {v!r} from {raw.strip()[-90:]!r}')

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

send('ONLY FORTH DEFINITIONS DECIMAL', 1.0)

print(f'\nPassed: {PASS}/{PASS + FAIL}')
s.close()
sys.exit(0 if FAIL == 0 else 1)
