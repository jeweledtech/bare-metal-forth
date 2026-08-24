#!/usr/bin/env python3
"""G6 boot chain harness (spec 2026-08-05-g6-chain-design.md S3).

Order: tree identity -> fixture -> phase 1 live install (memdisk
instance over GRUB/TFTP writes the AHCI disk through the real
driver) -> host-side second authority (a)-(f) -> legs A-D.

The disk every leg chainloads is the one ADD-BOOT-ENTRY actually
wrote. Red legs poke COPIES; build/tftp and the installed image
are never hand-modified.
"""
import atexit
import hashlib
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import time
import importlib.util

sys.stdout.reconfigure(line_buffering=True)

# _SELF is captured BEFORE the os.chdir below.  Python >= 3.9
# guarantees __file__ is absolute, which would make the order
# irrelevant -- but on 3.8 a RELATIVE __file__ resolved after a
# chdir resolves against the NEW cwd, and would only HAPPEN to be
# right when invoked from ROOT.  Same "safe by accident of
# environment" shape as qemu_kill's pkill bracket, and cheaper to
# remove by ordering than to document and hope someone reads it.
_SELF = os.path.abspath(__file__)
ROOT = os.path.dirname(os.path.dirname(_SELF))
os.chdir(ROOT)
# Both HASHED and load_mod'd from these constants, so a renamed
# path cannot hash one file while loading another.
GENCFG_PY = 'tools/pxe/gen-grub-cfg.py'
FIXTURE_PY = 'tests/g6_fixture.py'
CATALOG_PY = 'tools/catalog_layout.py'
TREE = 'build/tftp'
DISK = 'build/g6-disk.img'
PRISTINE = 'build/g6-disk-pristine.img'
QEMU = 'qemu-system-i386'

PASS = FAIL = 0


def check(name, ok, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {name}')
    else:
        FAIL += 1
        print(f'  FAIL: {name}' + (f' -- {detail}' if detail else ''))


def fatal(name, ok, detail=''):
    check(name, ok, detail)
    if not ok:
        print(f'\nPassed: {PASS}/{PASS + FAIL}')
        sys.exit(1)


def load_mod(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ---- self-describing log: hash the inputs BEFORE running them ----
# Any transcript quoting "Passed: N/N" must carry proof of WHICH
# bytes produced it.  Added 2026-08-11 after the 68/68 log could
# not be tied to its source: no snapshot existed, and rebuilding
# the as-run file meant replaying an edit transcript backwards to
# undo two edits.  That worked; nobody should need the procedure.
# Same family as deploy-provenance's manifest hash -- the artifact
# states what it is, instead of relying on someone remembering
# what was on disk at the time.
#
# ALL FOUR code inputs, not just this file.  FIXTURE_PY fixes the
# disk geometry the whole run is built on and GENCFG_PY produces
# the cfg under test; both are load_mod'd at runtime, so either
# could change without moving this file's hash.  CATALOG_PY
# resolves the INSTALL block range that stage 2 THRUs -- it decides
# WHICH BLOCKS the machine loads, so a change there changes what
# ran while leaving this file byte-identical.  A line reading
# "harness sha256 ..." while the fixture had silently changed
# would OVERSTATE its coverage, which is worse than printing
# nothing, because it stops people looking.  The tftp tree is
# already covered by stage 0's manifest hash; build/*.img are
# outputs, not inputs.
#
# BEFORE the load_mod calls, not after, for two reasons.  In
# principle: the line then describes what is ABOUT TO run rather
# than what happened to run.  In practice: load_mod EXECUTES its
# target, so a fixture with a syntax error would abort the run
# with a traceback and NO provenance at all -- absent in exactly
# the failure where "which fixture version?" is the first
# question.  Same backwards shape as attaching leg C's serial
# after GRUB has already run.
_unreadable = []
for _label, _p in (('harness', _SELF),
                   ('fixture', FIXTURE_PY),
                   ('gen-grub-cfg', GENCFG_PY),
                   ('catalog-layout', CATALOG_PY)):
    try:
        with open(_p, 'rb') as _f:
            _h = hashlib.sha256(_f.read()).hexdigest()
    except OSError as _e:
        _h = '<UNREADABLE>'
        _unreadable.append(f'{_label} ({_p}): {_e}')
    # Every DECLARED input gets a line even when unreadable --
    # a silently omitted row is indistinguishable from an input
    # that was never declared.  Scrapers should match
    # `input (md5|sha256) (\S+)\s+(\S+)`, not a bare 64-hex run.
    # The alternation is not cosmetic: the tftp tree's manifest
    # below is md5 (tree-hash.sh is the push-grub provenance
    # AUTHORITY and does not change to suit a log format), so the
    # algorithm is NAMED per line rather than assumed by position.
    print(f'input sha256 {_h}  {_label}')
# The staged TFTP tree is the fourth input and the only one that
# is not a file: it is what GRUB actually fetches, and both legs'
# behaviour is a function of it.  Printed HERE, with the other
# three, rather than only at stage 0 -- a scraper that has to know
# about two different provenance formats in two different places
# will read one of them.  Stage 0 still GATES it (a manifest that
# is not 32 hex is fatal there); this line only REPORTS it, so a
# tree that does not exist yet degrades to <UNREADABLE> instead of
# failing before the harness can say what it was looking for.
try:
    _manifest = subprocess.run(
        ['bash', 'tools/pxe/tree-hash.sh', TREE],
        capture_output=True, text=True).stdout.strip() or '<UNREADABLE>'
except OSError:
    _manifest = '<UNREADABLE>'
print(f'input md5 {_manifest}  tftp-tree')
# COUNTED precondition (+1 to N), not a bare raise: an unreadable
# input must produce a parseable FAIL plus a "Passed: N/M" line.
# A traceback gives a log scraper nothing, which is
# indistinguishable from "never ran".  Counted rather than
# emitted only on failure, because an assertion that exists only
# in the red direction is invisible in the pass count -- the
# mechanism by which "prove FREE-SLOT works" coexisted with
# "nobody calls FREE-SLOT" (Bug #33).
fatal('all code inputs readable', not _unreadable,
      '; '.join(_unreadable))

# Relocated BELOW the provenance block: int() on a non-numeric
# argv[1] raises, and that must not be able to suppress the hash
# lines.  Nothing between the top of the file and here reads
# PORT or MON.
#
# NO BARE DEFAULT, deliberately.  It used to read `else 4590`,
# which was WRONG: `make test-g6` passes TEST_PORT_BASE+95 = 4595.
# A constant that claims to mirror the Makefile and does not is
# the same duplicate-that-drifts shape this suite gates against
# elsewhere, and it drifts silently because both numbers are free
# ports -- the run works, it just is not the run you configured.
# Deleting the number deletes the drift; the Makefile is the sole
# authority for the port.  fatal(), not sys.exit(), so a bare
# invocation still emits a parseable FAIL and a "Passed: N/M".
fatal('port argument supplied (invoke via `make test-g6`)',
      len(sys.argv) > 1, 'usage: test_g6_chain.py PORT')
PORT = int(sys.argv[1])
MON = PORT + 1

gencfg = load_mod('gencfg', GENCFG_PY)
g6fix = load_mod('g6fix', FIXTURE_PY)
# load_mod, not `import`, for the same reason as the other two: the
# hashed path and the loaded path are the SAME constant, so a
# rename cannot hash one file while importing another off sys.path.
catalog_layout = load_mod('catalog_layout', CATALOG_PY)

# ---- channel registry (fatal() must not strand a chardev) ----
# QEMU's socket chardevs serve ONE client at a time. A monitor or
# serial socket left attached by a fatal() exit blocks
# qemu_kill()'s graceful monitor 'quit' -- it hangs to the 5 s
# timeout and falls through to SIGKILL, the exact path the
# comment above qemu_kill warns can drop in-flight AHCI writes.
_OPEN_CHANNELS = []


def track(ch):
    if ch is not None:
        _OPEN_CHANNELS.append(ch)
    return ch


def close_ch(ch):
    """Close a tracked channel and forget it."""
    if ch is None:
        return
    if ch in _OPEN_CHANNELS:
        _OPEN_CHANNELS.remove(ch)
    try:
        ch.close()
    except Exception:
        pass


def close_channels():
    while _OPEN_CHANNELS:
        close_ch(_OPEN_CHANNELS[-1])


# ---- monitor + VGA oracle (tests/test_vbr_boot.py pattern) ----


def drain(s, out=b''):
    try:
        while True:
            d = s.recv(4096)
            if not d:
                break
            out += d
    except Exception:
        pass
    return out


def mon_cmd(cmd, wait=2):
    m = socket.socket()
    m.settimeout(5)
    m.connect(('127.0.0.1', MON))
    time.sleep(0.5)
    drain(m)
    m.sendall(cmd.encode() + b'\n')
    time.sleep(wait)
    raw = drain(m).decode('ascii', errors='replace')
    m.close()
    return raw


# One dump = 4000 bytes at 0xb8000 = 2000 cells (25x80) stored
# char,attr,char,attr...  The command string and the completion
# threshold BOTH derive from this constant so they cannot drift.
VGA_BASE = 0xb8000
VGA_DUMP_BYTES = 4000
VGA_CMD = f'xp /{VGA_DUMP_BYTES}bx {hex(VGA_BASE)}'
VGA_COLS = 80


def parse_vga_cells(raw, base=VGA_BASE):
    """THE parser for an 'xp /Nbx <base>' dump -- slow and fast
    paths both call it.  Two parsers for one screen is a drift
    generator; the fast copy had already re-implemented this one
    and dropped its echo defense.

    ECHO DEFENSE.  MEASURED 2026-08-11 against a live HMP
    monitor: the monitor echoes the typed command back CHARACTER
    BY CHARACTER with ANSI escapes, so one 'xp /4000bx 0xb8000'
    arrives as a single line carrying every progressive prefix --
    '..0xb8', '..0xb80', '..0xb800', '..0xb8000'.  A bare
    r'0x[0-9a-f]{2}' scan over the whole buffer therefore counts
    FOUR phantom bytes per echo, not one; a buffer holding two
    echoes counts EIGHT (measured: naive 4004 vs anchored 4000
    for one dump, naive 8008 vs anchored 8000 for two).  No
    constant correction is right for both, which is why the fix
    is the filter and not an off-by-N.  Only lines shaped
    '<hex-addr>: 0x.. 0x..' contribute, RHS only -- measured
    EXACTLY 4000 and 8000 in those two cases.

    DUMP ANCHORING.  The cell list RESETS on each line whose
    address == base, so a buffer still holding an earlier
    (possibly half-read) dump yields the LAST dump alone, always
    starting on a char byte.  Without it a truncated earlier dump
    contributes an odd byte count and the caller's [::2] reads
    the entire screen off the ATTRIBUTE bytes."""
    cells = []
    for line in raw.splitlines():
        addr, sep, rest = line.partition(':')
        a = addr.strip()
        if not sep or not re.fullmatch(
                r'0x0*[0-9a-f]+|[0-9a-f]+', a):
            continue
        bs = re.findall(r'0x([0-9a-f]{2})', rest)
        if not bs:
            continue
        if int(a, 16) == base:
            cells = []
        cells += bs
    return cells


def cells_to_text(cells):
    """char,attr,char,attr... -> the 2000-character screen."""
    return bytes(
        int(c, 16) for c in cells[:VGA_DUMP_BYTES][::2]
    ).decode('ascii', errors='replace')


def read_vga_text():
    """Slow-path screen sample (fresh connection per call)."""
    try:
        raw = mon_cmd(VGA_CMD, wait=2)
    except Exception as e:
        return f'<monitor unreachable: {e}>'
    return cells_to_text(parse_vga_cells(raw))


def vga_rows(text, limit=6, width=VGA_COLS):
    """Diagnostic view of a screen: the NON-EMPTY rows, in order.

    A blind text[:200] slice shows rows 0-2 of 25 and reads as
    blank padding whenever the interesting line (a GRUB echo, a
    VBR banner) lands lower down -- i.e. it is least informative
    exactly when the leg goes red.  Rows are numbered so a reader
    six months from now can tell 'row 13 of a menu' from 'row 0
    of a banner'."""
    rows = [(i, text[i * width:(i + 1) * width].strip())
            for i in range(len(text) // width)]
    hits = [f'r{i}:{t!r}' for i, t in rows if t]
    if not hits:
        return f'<blank screen, {len(text)} cells>'
    extra = len(hits) - limit
    if extra > 0:
        hits = hits[:limit] + [f'(+{extra} more non-empty rows)']
    return ' | '.join(hits)


def ser_head(raw, n=200):
    """Serial-drain evidence for the 'nothing booted' checks.

    Report the HEAD, not the tail: what identifies WHICH instance
    booted is the banner at the START of the drain.  A trailing
    slice shows the prompt every instance prints and answers
    nothing.  Length is reported too -- 'silent' and 'noisy but
    no ok' are different failures."""
    return f'len={len(raw)} head={raw[:n]!r}'


def sendkey(key):
    """SLOW key delivery -- NOT usable for GRUB entry selection.

    Costs ~11 s because mon_cmd's drain() blocks against the 5 s
    socket timeout, so it cannot land a keystroke inside GRUB's
    5 s menu window; leg A used to look green with two of these
    only because ~7.5 s / ~18.5 s happened to straddle the menu.
    Use MonFast.sendkey after poll_grub_menu_fast instead.  Kept
    (currently uncalled) for slow-path monitor work that has no
    deadline."""
    mon_cmd(f'sendkey {key}', wait=0.5)


def poll_grub_menu(timeout=40):
    """The 'GRUB came up over TFTP' assertion in every leg."""
    end = time.time() + timeout
    while time.time() < end:
        vga = read_vga_text()
        if 'ForthOS - memdisk' in vga:
            return vga
        time.sleep(2)
    return read_vga_text()


class MonitorDown(Exception):
    """The persistent monitor channel is gone (QEMU died, or the
    chardev refused the connection).

    Raised instead of letting a raw socket traceback escape: an
    uncaught traceback exits the harness with NO 'Passed: N/M'
    line and NO check record -- an undiagnosable failure rather
    than a red.  Every caller converts it to a recorded FAIL."""


class MonFast:
    """Fast, PERSISTENT monitor channel.

    MEASURED 2026-08-11: the default mon_cmd/read_vga_text pair
    costs 12.5 s per VGA sample (drain() blocks on the 5 s socket
    timeout twice, plus 2.5 s of sleeps) and a single sendkey
    costs ~11 s for the same reason.  GRUB's menu timeout is 5 s,
    so nothing built on the slow path can observe -- let alone
    act inside -- that window.  One persistent connection with
    short timeouts samples in ~0.3 s.

    PERSISTENT is load-bearing, not an optimisation: ~200 rapid
    connect/close cycles were observed killing QEMU outright, so
    reconnect-per-sample is not available as a cheap alternative.

    Used by every leg that must ACT inside GRUB's 5 s window
    (A, C, D).  Stage 2/3 and leg B keep the slow, already-proven
    helpers: unifying the CONNECTION lifecycle would change what
    those green stages observe (qemu_kill's graceful 'quit' and
    every mon_cmd assume the chardev's single client slot is
    free, and each qemu_net_boot replaces the chardev), and that
    is not provable from here.  The PARSE is unified -- see
    parse_vga_cells -- which is where the drift risk lived."""

    def __init__(self, tries=5):
        # Retry, symmetric with serial_connect(tries=5): a
        # daemonized QEMU may still be opening its chardev.
        last = None
        for _ in range(tries):
            self.s = socket.socket()
            self.s.settimeout(0.3)
            try:
                self.s.connect(('127.0.0.1', MON))
                self._eat()
                track(self)
                return
            except OSError as e:
                last = e
                try:
                    self.s.close()
                except Exception:
                    pass
                time.sleep(1)
        raise MonitorDown(
            f'monitor port {MON} refused {tries} connects: {last}')

    def _eat(self):
        try:
            while True:
                if not self.s.recv(65536):
                    break
        except Exception:
            pass

    def sendkey(self, key):
        self._eat()
        try:
            self.s.sendall(f'sendkey {key}\n'.encode())
        except OSError as e:
            raise MonitorDown(f'sendkey {key} failed: {e}')
        time.sleep(0.2)

    def vga(self, deadline=3.0):
        """Sample the screen, stopping on COMPLETION (a whole
        dump parsed) rather than on a socket timeout.

        Completion is counted from parse_vga_cells, i.e. from
        ADDRESS-ANCHORED bytes only.  Counting raw '0x..' tokens
        counts the monitor's per-character command echo too (4
        phantom tokens per echo, measured) and so stops the read
        up to 4 bytes early, leaving the tail of the dump in the
        socket as stale input for the NEXT sample.

        REPRODUCED 2026-08-11 by replaying a canned echo+dump
        through both implementations at recv-chunk granularity:
        the old form broke at 3997 anchored bytes, left 3 tokens
        (ODD) unread, and the following sample -- stale 3 plus a
        fresh dump truncated the same way -- parsed 3994 cells
        whose tail slice decoded the screen off the ATTRIBUTE
        bytes.  Whole-screen garbage, presenting as an
        inexplicable red on legs A/C/D.  A complete fresh dump is
        immune however much stale precedes it (the tail slice
        lands on it exactly), so the truncation and the parity
        shift are ONE bug, not two: fix the count and the parity
        hazard cannot arise."""
        self._eat()
        try:
            self.s.sendall(VGA_CMD.encode() + b'\n')
        except OSError as e:
            raise MonitorDown(f'vga sample failed: {e}')
        raw = ''
        cells = []
        end = time.time() + deadline
        while time.time() < end:
            try:
                d = self.s.recv(65536)
                if not d:
                    raise MonitorDown(
                        'monitor closed by peer (QEMU gone?)')
                raw += d.decode('ascii', errors='replace')
            except socket.timeout:
                pass
            except OSError as e:
                raise MonitorDown(f'vga recv failed: {e}')
            cells = parse_vga_cells(raw)
            if len(cells) >= VGA_DUMP_BYTES:
                break
        return cells_to_text(cells)

    def close(self):
        try:
            self.s.close()
        except Exception:
            pass


def monfast_or_fatal(leg):
    """A dead monitor must be a RECORDED red, not a traceback."""
    try:
        return MonFast()
    except MonitorDown as e:
        fatal(f'{leg}: monitor channel attached', False, str(e))


def poll_grub_menu_fast(mf, timeout=90):
    """Fast-path twin of poll_grub_menu: same predicate, ~0.3 s
    cadence instead of 12.5 s, so the caller can still select an
    entry inside GRUB's own 5 s window after detecting the menu.
    (Measured on leg C: detect 8.0 s, keys 9.0 s, echo 9.3 s.)"""
    menu = ''
    end = time.time() + timeout
    while time.time() < end:
        menu = mf.vga()
        if 'ForthOS - memdisk' in menu:
            return menu
    return menu


# ---- QEMU lifecycle ----

def qemu_kill():
    # Graceful monitor quit FIRST: SIGKILL on a daemonized QEMU
    # holding the raw .img open can drop in-flight AHCI writes,
    # and the stage 2->3 boundary reads that image as the second
    # authority. pkill stays as the fallback, not a replacement.
    try:
        mon_cmd('quit', wait=1)
    except Exception:
        pass
    # WHY THIS PATTERN IS CURRENTLY SAFE -- it is a property of how
    # this harness happens to be LAUNCHED, not of the pattern.
    # `pkill -f` matches whole command lines, and the [q] bracket
    # only stops the pattern matching pkill/grep itself; it does NOT
    # stop it matching the INVOKING shell, whose argv contains the
    # pattern text verbatim when a probe is run inline via `bash -c`.
    # Measured 2026-08-11 while writing the appendices in
    # docs/finding-hmp-echo-phantom-bytes-2026-08-11.md: a
    # `pkill -9 -f "[q]emu.*hmpmon"` killed the calling shell.
    # We are safe here only because every launch line
    # ("python3 tests/test_g6_chain.py 4590", and shells wrapping
    # it) contains no "qemu" substring, so `[q]emu.*PORT` cannot
    # match them -- verified 2026-08-11. Wrap this run in a script
    # whose name or path contains "qemu" and the bracket protects
    # nothing. The real fix is PID-based cleanup (no -daemonize,
    # keep the Popen, call .kill()). Left as a carried item, and the
    # earlier justification for deferring it was wrong: checked
    # 2026-08-11, -daemonize appears at exactly ONE site
    # (qemu_net_boot), so there is no "elsewhere" it is load-bearing.
    # All it buys there is that subprocess.run(check=True) returns
    # once QEMU forks and surfaces a launch failure synchronously;
    # dropping it costs a Popen plus an explicit readiness poll.
    # That is a small refactor, not a blocker -- see the carried
    # items in the task doc.
    subprocess.run(['pkill', '-9', '-f', f'[q]emu.*{PORT}'],
                   capture_output=True)
    time.sleep(1)


# A fatal() mid-run must not strand a daemonized QEMU on the
# ports -- that poisons the NEXT run as a mystery failure.
atexit.register(qemu_kill)
# Registered AFTER qemu_kill so atexit's LIFO order runs it
# FIRST: every chardev must be released before qemu_kill tries
# its graceful monitor 'quit', or the quit cannot be serviced.
atexit.register(close_channels)


def qemu_net_boot(disk, tree=TREE):
    """PXE chain: SeaBIOS iPXE ROM -> TFTP -> GRUB (spec D1)."""
    qemu_kill()
    # -daemonize chdirs QEMU to / AFTER drive open but BEFORE
    # the first TFTP request (os_setup_post), so the tftp=
    # prefix must be absolute or iPXE gets ENOENT.
    subprocess.run([
        QEMU,
        '-netdev', f'user,id=n0,tftp={os.path.abspath(tree)},'
                   'bootfile=/grub/i386-pc/core.0',
        '-device', 'e1000,netdev=n0',
        '-boot', 'n',
        '-drive', f'file={disk},format=raw,if=none,id=sata0',
        '-device', 'ich9-ahci,id=ahci0',
        '-device', 'ide-hd,drive=sata0,bus=ahci0.0',
        '-serial', f'tcp::{PORT},server=on,wait=off',
        '-monitor', f'tcp:127.0.0.1:{MON},server=on,wait=off',
        '-display', 'none', '-daemonize'], check=True)
    time.sleep(2)


def serial_connect(tries=30):
    s = socket.socket()
    s.settimeout(10)
    for _ in range(tries):
        try:
            s.connect(('127.0.0.1', PORT))
            return s
        except OSError:
            time.sleep(1)
    return None


# ---- serial driving (test_install.py conventions) ----

SER = None


def send(cmd, wait=1.0):
    SER.sendall((cmd + '\r').encode())
    time.sleep(wait)
    SER.settimeout(1)
    return drain(SER).decode('ascii', errors='replace')


def body_of(raw):
    return raw.split('\n', 1)[1] if '\n' in raw else raw


def val(expr, wait=1.5):
    raw = send(f'DECIMAL {expr} .', wait)
    body = body_of(raw)
    if '?' in body:
        return None, raw
    nums = re.findall(r'-?\d+', body)
    return (int(nums[-1]) if nums else None), raw


def expect(name, expr, want, wait=1.5):
    v, raw = val(expr, wait)
    check(f'{name} ({expr} = {want})',
          v is not None and v == want,
          f'got {v!r} from {raw.strip()[-90:]!r}')


BLOCKS_IMG = 'build/blocks.img'


def get_vocab_blocks(vocab_name):
    """Read the block range out of the CATALOG THE MACHINE READS.

    This used to re-run write-catalog.py's placement algorithm in a
    subprocess and trust that the two agreed.  It replaced that
    with a parse of the built artifact, for a reason that had
    already gone live once: the algorithm copy modelled VOCABS ONLY,
    while write-catalog now lays out `vocabs + raw payloads`, and
    the number of catalog blocks -- which every data block number
    is offset by -- is a function of the COMBINED entry count.  At
    65 entries both come to 5 blocks, so the copy is right today
    and would go wrong at 76 without touching this file.  That is
    the drift-bug family exactly: a duplicated algorithm in the
    test, correct until the original grows a term.

    Parsing the catalog removes the duplicate rather than repairing
    it.  These are the same bytes CATALOG-FIND parses in Forth, so
    a layout the harness can read is a layout the machine can read.

    The parse itself now lives in tools/catalog_layout.py, shared
    with the completeness gate and the runbook generator -- writing
    it a third time here would rebuild the duplicate this docstring
    exists to complain about.  (Provenance hashing is still
    deliberately duplicated per-suite; that is a different rule,
    and the reason is stated at the top of this file.)
    """
    return catalog_layout.vocab_blocks(vocab_name, BLOCKS_IMG)


# ================= tree identity =================
print('G6 chain harness (port %d)' % PORT)
print('=' * 50)
print('\nStage 0: tree identity (one tree, both consumers)')
fatal('staged tree exists',
      os.path.exists(f'{TREE}/grub/i386-pc/core.0'),
      "run 'make grub-net'")
fatal('staged cfg == committed grub.cfg (drift gate, live)',
      open(f'{TREE}/grub/grub.cfg').read() ==
      open('tools/pxe/grub.cfg').read())
# Reuses the value the provenance block already printed rather
# than recomputing it.  Recomputing would let the REPORTED hash
# and the GATED hash be two different measurements of a tree that
# changed in between -- the log would then attest to a tree no
# gate ever checked.  One computation, one number, two uses.
manifest = _manifest
fatal('manifest hash computed (push-grub provenance authority)',
      re.fullmatch(r'[0-9a-f]{32}', manifest) is not None,
      manifest)

# ================= fixture =================
print('\nStage 1: fixture')
g6fix.build(DISK)
# verify() returns (fails, checks_run); assert both -- an empty
# fail list with the wrong check count would mean the verifier
# short-circuited, not that the fixture is good.
g6_fails, g6_ran = g6fix.verify(DISK)
fatal('fixture self-verify', g6_fails == [] and g6_ran == 12,
      f'{g6_fails} ran={g6_ran}')
# Pristine copy: red legs and host asserts diff against this.
subprocess.run(['cp', '--sparse=always', DISK, PRISTINE],
               check=True)

# ================= phase 1: live install =================
print('\nStage 2: phase 1 -- live install (memdisk over GRUB)')
qemu_net_boot(DISK)
menu = poll_grub_menu()
fatal('GRUB menu up over TFTP', 'ForthOS - memdisk' in menu,
      vga_rows(menu))
# No sendkey: timeout falls through to entry 0 (frozen order).
# memdisk hauls ~2.2 MB then boots; allow generously.
time.sleep(25)
SER = track(serial_connect())
fatal('serial connected', SER is not None)
time.sleep(3)
drain(SER)
# Readiness poll (observed on 2026-08-06): commands sent before
# the instance settles are half-eaten, and the boot-time BASE is
# HEX until then (7 6 * prints 2A). val() prefixes DECIMAL, so
# a correct 42 here proves both liveness and a sane base. This
# is the specific per-command wait for boot, not a global bump.
v = None
for _ in range(20):
    v, raw = val('7 6 *', wait=2)
    if v == 42:
        break
    time.sleep(3)
fatal('memdisk instance alive (7 6 * = 42)', v == 42, raw[-90:])
# Discriminator: this IS a memdisk boot (nonzero), which also
# proves the probe can tell the instances apart before legs A/B
# lean on it. Probe order fixed; HEX is sticky -> DECIMAL after.
# POSITIVE probe (absence-of-'0 ok' was fail-open: a wedged
# instance, an error line, or empty output all passed). val()
# wraps as 'DECIMAL <expr> .', so the literal parses in hex and
# the flag prints in decimal; any '?' -> None -> FAIL.
v, raw = val('HEX 28098 @ 0= 0= DECIMAL')
fatal('MEMDISK-VAR nonzero on memdisk boot', v == -1, raw[-90:])

# Load INSTALL blocks (range THRU -- blocks come from the
# memdisk RAM image on this boot path). Three as-built facts
# (all observed over serial, 2026-08-06) reshape the spec's
# original AHCI-THRU + LOAD-VOCAB sequence:
#   1. AHCI and SURVEYOR are EMBEDDED in the full build
#      (Makefile EMBED_VOCABS) -- re-THRUing AHCI from blocks
#      is redundant, so only INSTALL needs a block load.
#   2. S" INSTALL" LOAD-VOCAB dies ('F ?' / 'FF ?' then wedge)
#      on this boot path -- the known LOAD-VOCAB bug; THRU of
#      the catalog range is the documented workaround.
#   3. DECIMAL must be in effect when the block range is TYPED.
#      Mechanism CONFIRMED 2026-08-20 (pre-registered experiment,
#      suspect S1; logs /tmp/thru-exp-*.log): the 2026-08-06
#      "reversed order spews meta-compiler words and reboots" was
#      never an ordering constraint. AHCI-INIT's success path
#      ends 'DECIMAL . HEX CR' (ahci.fth:499) and returns with
#      BASE=16, so a bare '575 653' typed after it misparses as
#      hex (-> 1397-1619, the TARGET-*/UI-* metacompiler blocks)
#      and THRU loads those instead: undefined-word spew, wedge.
#      With DECIMAL on the line the SAME range THRU is clean
#      AFTER AHCI-INIT and INSTALL fully loads (FS-SLOT @ = -1).
#      The 2026-08-13 falsifier (ARM-VBR-TPL's single BLOCK read
#      after init) never contradicted this: it finds its block
#      by NAME, not a typed numeral. This harness was protected
#      only by ACCIDENT -- val() prefixes every probe with
#      DECIMAL, leaving it sticky before the THRU. Red-first
#      proof 2026-08-20: HEX injected before a bare THRU took
#      the suite 29/29 -> 15/29, with 'alive after INSTALL THRU'
#      still PASSING (a liveness probe is not a content probe)
#      and every INSTALL word absent downstream. Hence the
#      explicit DECIMAL below. Typed order kept as-is (zero
#      churn before iron); ordering is RETIRED as mechanism.
#      Root fix (BASE-transparent AHCI-INIT via BASE @ ... BASE !)
#      is deferred until AFTER iron G6 -- it rebuilds
#      combined.img and invalidates deployment provenance.
a, b = get_vocab_blocks('INSTALL')
fatal('INSTALL catalog range found', a is not None)
# --8<-- RUNBOOK-3A-BEGIN
send(f'DECIMAL {a} {b} THRU', 25)
# The exemption below is measured, not assumed: the 2026-08-20
# red-first run (HEX injected before a bare THRU) took the suite
# to 15/29 and this probe STILL PASSED -- a liveness probe cannot
# detect that THRU loaded the wrong 200 blocks. Exempt because it
# is scaffolding; it is NOT evidence about the THRU's content.
check('alive after INSTALL THRU',
      val('1 2 +')[0] == 3)  # runbook-exempt: liveness only, blind to THRU content (see above)
send('USING AHCI', 2)        # embedded vocab, no THRU needed
send('AHCI-INIT', 5)
# TRIPWIRE (inverted 2026-08-23, expected RED on the DECIMAL leg
# until the ahci.fth fix lands): AHCI-INIT must be
# base-transparent. Until the fix, its success path ended
# 'DECIMAL . HEX CR' and returned with BASE=16 regardless of the
# caller's base (measured on iron 2026-08-22; the defect behind
# the 2026-08-06 INSTALL THRU incident and the OWN-LEN=549
# install slack). The previous tripwire PINNED the defect
# (asserted BASE==16) so the fix could not land silently; this
# version asserts the invariant: BASE *unchanged across* the
# word, in BOTH directions, so a regression to EITHER a blind
# HEX or a blind DECIMAL restore is caught. DO NOT weaken to a
# single direction and DO NOT delete: a word that always
# returns in the base you happened to test from passes a
# one-legged probe.
# Re-running AHCI-INIT for the legs is allocation-free: the DMA
# buffers -- CL-BUF, FIS-BUF, CT-BUF, SEC-BUF -- are load-time
# PHYS-ALLOC CONSTANTs in ahci.fth (grep the names); the
# word itself never calls PHYS-ALLOC. A second call is
# idempotent enable bits + PORT-STOP/PORT-START re-pointing the
# port at the SAME buffers -- spec-legal re-init, no leak, and
# no in-flight I/O to disturb (every command in this driver is
# synchronous; ISSUE-CMD polls completion). Verified by reading
# ahci.fth 2026-08-23, not assumed.
# The probe CANNOT go through the expect/val helpers: both
# prefix DECIMAL, overwriting the very state being measured.
# Raw sends only. Note 'BASE @ DECIMAL .' prints the entry base
# rendered in decimal and leaves BASE=10.
send('DECIMAL', 1)           # runbook-exempt: tripwire sets its own entry condition; not an operator step
send('AHCI-INIT', 5)         # runbook-exempt: transparency-probe re-run, never typed by the operator; allocation-free (see evidence above)
raw_base = send('BASE @ DECIMAL .', 2)  # runbook-exempt: interrogates BASE, which no DECIMAL-prefixed helper can measure
check('BASE unchanged across AHCI-INIT (entered DECIMAL)',
      re.findall(r'-?\d+', body_of(raw_base))[-1:] == ['10'],
      raw_base.strip()[-90:])
send('HEX', 1)               # runbook-exempt: second tripwire leg entry condition; not an operator step
send('AHCI-INIT', 5)         # runbook-exempt: transparency-probe re-run, HEX leg (same allocation-free evidence)
raw_base = send('BASE @ DECIMAL .', 2)  # runbook-exempt: interrogates BASE; leaves BASE=10 for the code below
check('BASE unchanged across AHCI-INIT (entered HEX)',
      re.findall(r'-?\d+', body_of(raw_base))[-1:] == ['16'],
      raw_base.strip()[-90:])
check('alive after AHCI-INIT',
      val('1 2 +')[0] == 3)  # runbook-exempt: liveness only; its DECIMAL prefix MASKS the BASE mutation this line sits after -- a bare probe here would have shown 2A on 2026-08-06
send('ALSO SURVEYOR', 1)     # BEFORE USING INSTALL (DOVOC trap)
send('USING INSTALL', 2)
# Close the stage with an explicit DECIMAL: AHCI-INIT left BASE=16
# and sections 3b-3d all type numerals inside that window (3c's
# ': TPL-SUM 0 512 0 DO ...' would compile a 1298-iteration loop
# under HEX; 3d's 2048 would store 8264). One restore immediately
# after the word that broke the base, instead of four per-section
# copies -- and it is what the deferred ahci.fth fix will do, so
# when the root fix lands this line becomes redundant, not wrong.
send('DECIMAL', 1)
# --8<-- RUNBOOK-3A-END
# Arm vectors: reads land at SEC-BUF, so RD-BUF-ADDR = SEC-BUF.
# NOTE: GUID-ABSENT? (called inside MAKE-OWN-ENT) reads the GPT
# entry array through SEC-READ-VEC into RD-BUF-ADDR's buffer --
# i.e. it CLOBBERS SEC-BUF. Nothing below relies on SEC-BUF
# contents surviving across MAKE-OWN-ENT (the LBA0 55AA probes
# run before it), and later gates re-read what they need. Keep
# it that way.
send("' AHCI-READ SEC-READ-VEC !", 1)
send('SEC-BUF RD-BUF-ADDR !', 1)
send('BIND-WRITER AHCI-WRITE', 1)
check('alive after arm', val('1 2 +')[0] == 3)

# ---- Arm VBR-TPL from the blocks-side template ----
# ONE typed line, because on iron there is no paste target: the
# net console is output-only (NET-DICT needs an NE2000; the HP
# board has an RTL8168). The 512 C! pokes that used to live here
# were a TEST FIXTURE standing in for a missing production
# mechanism, sitting upstream of every assertion that would have
# detected the absence -- so the harness proved the installer
# worked given a template nothing in the shipped system supplied.
# Task 12.5 built the real path (install.fth ARM-VBR-TPL, a
# catalog-addressed binary block written by write-catalog.py
# --raw) and this harness now exercises THAT, not a substitute.
#
# The fixture is gone, not disabled. It is in git history, where
# retrieving it costs a deliberate act. Parking it in a dead
# branch would have reproduced the same defect wearing a
# different hat: a substitute mechanism one flag-flip away on the
# day blocks delivery misbehaves -- the day you most need the
# harness to be testing the real path.
#
# RED-FIRST, 2026-08-13: the population was deleted BEFORE the
# replacement was built, to check that anything downstream
# actually depended on it. It did -- exit 2, Passed: 51/61, 10
# FAILs, first and nearest at BUILD-VBR's no-template gate
# (FAIL: ADD-BOOT-ENTRY -- got 0). So re-pointing these
# assertions at a blocks-delivered buffer is a real test and not
# theater. DO NOT WEAKEN THAT GATE on the theory that the host
# asserts cover it: they detect, but the gate ATTRIBUTES. Without
# line 52 that log reads as nine independent defects in nine
# subsystems instead of one cause and its echo.
VBR_TPL_BYTES = open('build/vbr.bin', 'rb').read()
fatal('vbr.bin is one sector', len(VBR_TPL_BYTES) == 512,
      str(len(VBR_TPL_BYTES)))
# Two gates, and they must stay two. ARM-VBR-TPL's flag reports
# that DELIVERY happened -- catalog hit, block mode, CMOVE done.
# It cannot report that the BYTES are right. MEASURED 2026-08-13:
# against an image with one byte of the staged block flipped,
# ARM-VBR-TPL still returned -1 while TPL-SUM moved 38891 ->
# 39000, exactly the -73 +182 the flip predicts. Collapsing these
# into one check would leave the content assertion unexecuted in
# precisely the run where content is wrong.
expect('ARM-VBR-TPL delivers template', 'ARM-VBR-TPL', -1, wait=5)
# Byte-sum against the HOST ARTIFACT is the whole-buffer oracle
# (max 512*255 = 130560, no cell overflow), then the two
# structural facts BUILD-VBR itself gates on (55AA at 510/511).
# Compared against build/vbr.bin rather than a literal: the
# number is derived from the same file the build embedded, so a
# regenerated VBR cannot leave a stale constant behind.
# DO/LOOP is compile-only in this kernel (every DO in the whole
# suite sits in a colon def -- none interpreted), so the sum loop
# must be compiled first, not typed bare.
send(': TPL-SUM 0 512 0 DO VBR-RAW I + C@ + LOOP ;', 1.0)
expect('template byte-sum matches host', 'TPL-SUM',
       sum(VBR_TPL_BYTES), wait=8)
expect('template 55AA low', 'VBR-RAW 510 + C@', 0x55)
expect('template 55AA high', 'VBR-RAW 511 + C@', 0xAA)
expect('VBR-TPL armed', 'VBR-TPL @ VBR-RAW =', -1)

# ---- Declare the ESP extent for the G2 tripwire ----
# Second runtime-arming gap (same class as the VBR-TPL push,
# found when ADD-BOOT-ENTRY refused at ESP-BASELINE on the
# first full run 2026-08-06): ESP-BASE/ESP-LEN default 0 and
# NOTHING in the word chain declares them -- test_install.py's
# Test 51 pokes them by hand (~:1619). Derive both from the
# fixture's own PARTS table (type-GUID match), not hardcoded
# numbers, so a fixture geometry change cannot silently
# desynchronize the tripwire. COROLLARY for Task 12: the iron
# runbook needs the same two pokes with the REAL ESP extent
# from the HP survey, or iron G6 refuses at the same gate.
esp = [p for p in g6fix.PARTS if p[0] == g6fix.T_ESP]
fatal('fixture has exactly one ESP', len(esp) == 1, str(len(esp)))
ESP_BASE, ESP_LAST = esp[0][2], esp[0][3]
send(f'{ESP_BASE} ESP-BASE !  '
     f'{ESP_LAST - ESP_BASE + 1} ESP-LEN !', 1)
expect('ESP-BASE declared', 'ESP-BASE @', ESP_BASE)
expect('ESP-LEN declared', 'ESP-LEN @', ESP_LAST - ESP_BASE + 1)

# --8<-- RUNBOOK-3E-BEGIN
# Flag-checked probe before trust (fail-open hazard): LBA 0 read
# must return flag 0 AND carry the fixture's 55AA.
expect('LBA0 read flag 0', '0 1 AHCI-READ', 0, wait=3)
expect('LBA0 55AA low byte', 'SEC-BUF 510 + C@', 0x55)
expect('LBA0 55AA high byte', 'SEC-BUF 511 + C@', 0xAA)

send('PARTITION-MAP', 10)
expect('survey trusted', 'MAP-TRUSTED?', -1)
expect('claim 225 sectors', '225 FREE-EXTENT', -1, wait=20)
OWN_BASE, raw = val('OWN-BASE @')
# Keep this check exactly this loose. The fixture has TWO free
# gaps >= 225 sectors: the tail gap after P5 AND the front gap
# at LBA 34-2047, so OWN-BASE could legitimately come back as
# something small like 34. Do NOT tighten to > 534527 unless
# FREE-EXTENT's MIN-LBA policy provably excludes the front gap.
fatal('OWN-BASE probed', OWN_BASE is not None and OWN_BASE > 33,
      raw[-90:])
print(f'  OWN-BASE = {OWN_BASE}')
expect('OWN-LEN = 225', 'OWN-LEN @', 225)

# The claim step Bug #33 was made of: FREE-SLOT is the only
# setter of FS-SLOT (load-time -1), and GPT-ARM refuses an
# unset slot. Slot 5 = first empty on the HP-mirror fixture
# (slots 0-4 occupied, 0 = ESP).
expect('slot claimed', 'FREE-SLOT', -1, wait=10)
expect('FS-SLOT = 5 (first empty; ESP survives)', 'FS-SLOT @', 5)

expect('GPT-ARM', 'GPT-ARM', -1, wait=5)
# Split for attribution: if the composer refuses it returns 0,
# and a combined 'MAKE-OWN-ENT ADD-PARTITION' would feed that 0
# to ADD-PARTITION as an entry address -- undiagnosable. The
# entry address rides the data stack across serial lines, so
# probe the flag copy and leave the entry in place.
expect('MAKE-OWN-ENT composed (nonzero entry)',
       'MAKE-OWN-ENT DUP 0= 0=', -1, wait=10)
expect('ADD-PARTITION', 'ADD-PARTITION', -1, wait=30)
expect('ADD-BOOT-ENTRY', 'ADD-BOOT-ENTRY', -1, wait=60)
expect('stack clean after install', 'DEPTH', 0)
# --8<-- RUNBOOK-3E-END
close_ch(SER)
qemu_kill()

# ================= host-side second authority =================
print('\nStage 3: host asserts (independent of the word gates)')
FTH = 'forth/dict/install.fth'
UG_CELLS = gencfg.scan_install_fth(FTH)
TG_RE = re.compile(r'^([0-9A-F]{8}) CONSTANT FOS-TG([0-3])\s*$')
tg = {}
with open(FTH) as f:
    for line in f:
        m = TG_RE.match(line.rstrip('\n'))
        if m:
            tg[int(m.group(2))] = int(m.group(1), 16)
TG_CELLS = [tg[i] for i in range(4)]
UG_BYTES = b''.join(c.to_bytes(4, 'little') for c in UG_CELLS)
TG_BYTES = b''.join(c.to_bytes(4, 'little') for c in TG_CELLS)

SEC = 512


def rd(f, lba, n=1):
    f.seek(lba * SEC)
    return f.read(n * SEC)


with open(DISK, 'rb') as f, open(PRISTINE, 'rb') as p:
    # (a) LBA 0 untouched
    check('(a) LBA 0 byte-identical to fixture',
          rd(f, 0) == rd(p, 0))
    # (b) entries unchanged except exactly our one slot
    cur, pre = rd(f, 2, 32), rd(p, 2, 32)
    changed = [i for i in range(128)
               if cur[i * 128:(i + 1) * 128] !=
               pre[i * 128:(i + 1) * 128]]
    check('(b) exactly one GPT slot changed', len(changed) == 1,
          f'changed slots: {changed}')
    slot = changed[0] if len(changed) == 1 else -1
    # The changed slot MUST have been empty (all-zero) in the
    # pristine image.  Without this, assert (b) is fail-open:
    # "one slot changed" passes equally whether we claimed a free
    # slot or overwrote an occupied one (e.g. the ESP at slot 0).
    pristine_ent = pre[slot * 128:(slot + 1) * 128]
    check('(b) changed slot was empty in pristine',
          pristine_ent == bytes(128),
          f'slot {slot} pristine type: {pristine_ent[:16].hex()}')
    # (c) backup entry array == primary
    check('(c) backup array == primary',
          rd(f, g6fix.TOTAL - 33, 32) == cur)
    # (f) our slot carries the canonical GUIDs (same scan the
    # generator uses closes composer->disk->grub.cfg through one
    # authority)
    ent = cur[slot * 128:(slot + 1) * 128]
    check('(f) type GUID field', ent[0:16] == TG_BYTES)
    check('(f) unique GUID field', ent[16:32] == UG_BYTES)
    check('(f) slot start == OWN-BASE',
          struct.unpack('<Q', ent[32:40])[0] == OWN_BASE)
    check('(f) slot end == OWN-BASE+224',
          struct.unpack('<Q', ent[40:48])[0] == OWN_BASE + 224)
    # (d) VBR at OWN-BASE: template bytes + bake, 55AA
    vbr_tpl = open('build/vbr.bin', 'rb').read()
    dap_re = re.compile(
        b'\x10\x00..\x00\x7e\x00\x00'
        b'\xef\xbe\xad\xde\x00\x00\x00\x00', re.DOTALL)
    hits = [m.start() for m in dap_re.finditer(vbr_tpl)]
    # FATAL, not check: if the sentinel DAP pattern matched more
    # than once, LBA_OFF = hits[0] + 8 is a GUESS, and every
    # later use of it (assert (d) here, leg D's poke 200 lines
    # down) is built on that guess -- surfacing as a mystery
    # 'no DISK ERR'. Fail closed where the ambiguity is.
    fatal('(d) vbr.bin sentinel unique', len(hits) == 1, str(hits))
    LBA_OFF = hits[0] + 8
    disk_vbr = rd(f, OWN_BASE)
    check('(d) 55AA at 510', disk_vbr[510:512] == b'\x55\xaa')
    check('(d) baked OWN-BASE+1 at VBR-LBA-OFF',
          struct.unpack('<I',
                        disk_vbr[LBA_OFF:LBA_OFF + 4])[0] ==
          OWN_BASE + 1)
    baked = bytearray(vbr_tpl)
    baked[LBA_OFF:LBA_OFF + 4] = struct.pack('<I', OWN_BASE + 1)
    check('(d) VBR == template except the bake',
          disk_vbr == bytes(baked))
    # (e) kernel sectors byte-equal build/kernel.bin -- the full
    # content proof the word's step 6 deferred to G6
    kern = open('build/kernel.bin', 'rb').read()
    check('(e) kernel is 224 sectors exactly',
          len(kern) == 224 * SEC, str(len(kern)))
    check('(e) kernel bytes on disk == build/kernel.bin',
          rd(f, OWN_BASE + 1, 224) == kern)

# ================= phase 2: the four-leg matrix =================
# Legs A/B prove BOTH menu entries boot the right instance from
# the SAME installed disk; C/D are the loud-failure legs.

print('\nStage 4: leg A -- entry 1 chainloads the installed'
      ' instance')
qemu_net_boot(DISK)
# DETERMINISTIC selection.  This WAS two blind sendkeys, green
# only by accident: mon_cmd's drain() blocks on the 5 s socket
# timeout, so the keys landed at ~7.5 s and ~18.5 s and happened
# to straddle GRUB's 5 s menu window.  Nothing enforced that, and
# it is no longer only leg A's problem -- legs C and D gate three
# checks on legA_ok below, so a timing slip here turns them red
# for reasons unrelated to what they test.  Any change to monitor
# speed (e.g. the now-shared VGA parse) moves those blind keys.
# Detect the menu, THEN select inside its own window: the shape
# legs B/C/D already use.
mf = monfast_or_fatal('leg A')
try:
    menu = poll_grub_menu_fast(mf)
    fatal('leg A: GRUB menu up over TFTP',
          'ForthOS - memdisk' in menu, vga_rows(menu))
    mf.sendkey('down')       # entry 1 = chainload installed
    mf.sendkey('ret')
except MonitorDown as e:
    fatal('leg A: monitor channel alive', False, str(e))
close_ch(mf)
# Chainload path: GRUB -> our VBR at OWN-BASE -> kernel.
time.sleep(30)
SER = track(serial_connect())
fatal('leg A: serial connected', SER is not None)
time.sleep(3)
drain(SER)
# Readiness poll (same pattern as stage 2): the chainloaded
# kernel may still be initialising; retry until it responds.
v = None
for _ in range(20):
    v, raw = val('2 3 +', wait=2)
    if v == 5:
        break
    time.sleep(3)
check('leg A: installed instance alive (2 3 + = 5)', v == 5,
      raw[-90:])
# LOAD-BEARING BEYOND LEG A.  Legs C and D gate three checks on
# this flag (two in C, one in D).  It is the de-aliasing device
# that makes a green NEGATIVE result impossible to manufacture
# from a totally broken boot path: leg C/D proving "nothing
# booted" means nothing unless something is known to boot on the
# same harness, port and disk.  Consequence: leg A's entry
# selection above must be deterministic, not timing luck --
# see the comment there.
legA_ok = v == 5
# Discriminator: chainload boot has NO memdisk hook, so the
# MEMDISK_BASE cell reads 0. POSITIVE form (stage 2's lesson:
# regex on raw output is fail-open); val() wraps as
# 'DECIMAL <expr> .' so the literal parses in hex and 0 prints
# in decimal; '?' -> None -> FAIL.
expect('leg A: discriminator 0 (chainload, no memdisk)',
       'HEX 28098 @ DECIMAL', 0)
close_ch(SER)
qemu_kill()

print('\nStage 5: leg B -- timeout falls through to memdisk')
qemu_net_boot(DISK)
menu = poll_grub_menu()
fatal('leg B: GRUB menu up over TFTP',
      'ForthOS - memdisk' in menu, vga_rows(menu))
# NO sendkey: the 5 s timeout must select entry 0 on its own --
# this is the daily-driver guarantee (frozen entry order).
time.sleep(25)
SER = track(serial_connect())
fatal('leg B: serial connected', SER is not None)
time.sleep(3)
drain(SER)
v, raw = val('2 3 +')
check('leg B: memdisk instance alive (2 3 + = 5)', v == 5,
      raw[-90:])
# POSITIVE flag form (mirror of stage 2): 0= 0= collapses any
# nonzero cell to -1, so a wedged instance, an error line, or
# empty output cannot fake a pass the way absence-of-'0 ok' did.
v, raw = val('HEX 28098 @ 0= 0= DECIMAL')
check('leg B: discriminator nonzero (memdisk boot)', v == -1,
      raw[-90:])
close_ch(SER)
qemu_kill()

print('\nStage 6: leg C -- wrong GUID: search fails loudly')
# Rationale shift (post-713c24f): the chainload entry no longer
# uses GRUB's `search` -- grub-pc 2.12 has NO --part-uuid search
# mode at all -- so the entry loads biosdisk/part_gpt/probe/
# regexp and loops (hd*,gpt*) calling `probe --part-uuid`,
# chainloading only inside a found-guard.  The original leg-C
# tell was GRUB's own 'no such device', which could only be
# emitted by search machinery that actually ran.  The tell is now
# OUR echo, which fires on ANY no-match -- including a probe loop
# that is broken end to end (biosdisk absent, (hd*,gpt*) empty,
# probe erroring on every partition).  Un-gated, leg C would go
# green having proved nothing about the GUID comparison.
# De-alias exactly as leg D does: leg A green (SAME cfg template,
# SAME probe loop, canonical GUID) proves the loop enumerates
# disks and matches.  Leg C green GIVEN leg A green is what
# isolates the GUID comparison as the thing that rejected the
# wrong value.  Hence both leg-C checks carry `legA_ok`.
SCRATCH = 'build/tftp-legc'
subprocess.run(['rm', '-rf', SCRATCH], check=True)
subprocess.run(['cp', '-r', TREE, SCRATCH], check=True)
subprocess.run([
    'python3', 'tools/pxe/gen-grub-cfg.py',
    '--override-guid',
    '00000000-0000-0000-0000-000000000000',
    '-o', f'{SCRATCH}/grub/grub.cfg'], check=True)
# Positive proof the red cfg is the one that will be served: the
# canonical GUID must be GONE and the all-zeros GUID present.
# Without this, a failed generator run leaves the GOOD cfg in the
# scratch tree and leg C tests nothing.
legc_cfg = open(f'{SCRATCH}/grub/grub.cfg').read()
good_cfg = open(f'{TREE}/grub/grub.cfg').read()
fatal('leg C: scratch cfg carries the all-zeros GUID',
      '00000000-0000-0000-0000-000000000000' in legc_cfg and
      legc_cfg != good_cfg,
      legc_cfg[-160:])
qemu_net_boot(DISK, tree=SCRATCH)
# Serial attached BEFORE GRUB runs and HELD open for the whole
# leg. Connecting after the fact made the silence check
# fail-open: QEMU discards output emitted before a client
# attaches, so an instance that booted and printed its banner
# early read as 'silence'. (Observed doing exactly that in leg D
# on the 2026-08-11 run.)
legc_ser = track(serial_connect(tries=5))
fatal('leg C: serial attached before GRUB runs',
      legc_ser is not None)
mf = monfast_or_fatal('leg C')
# NOT blind keys. OBSERVED 2026-08-11: fast blind keys land at
# ~2 s -- before GRUB exists -- and iPXE eats them during
# netboot, so the 5 s timeout falls through to entry 0 and leg C
# silently tests the MEMDISK instance (kernel banner + 'ok' on
# serial, echo never emitted). Legs A/B/D get away with blind
# keys only because the SLOW sendkey path happens to deliver at
# ~7.5 s / ~18.5 s, straddling the menu -- an accident of the
# 5 s socket timeout, not a design. The fast sampler makes the
# honest shape affordable: wait for the menu, then select inside
# its own 5 s window (measured detect 8.0 s, keys 9.0 s, echo
# 9.3 s -- an order of magnitude of margin).
err = ''
echo_seen = False
try:
    menu = poll_grub_menu_fast(mf)
    fatal('leg C: GRUB menu up over TFTP',
          'ForthOS - memdisk' in menu, vga_rows(menu))
    mf.sendkey('down')
    mf.sendkey('ret')
    # The probe loop finds no matching GUID, so the fail-closed
    # branch echoes the distinctive text and sleeps 5 s. Poll for
    # it; do not sleep-and-hope.
    end = time.time() + 90
    while time.time() < end:
        err = mf.vga()
        if 'ForthOS: partition GUID not found' in err:
            echo_seen = True
            break
except MonitorDown as e:
    fatal('leg C: monitor channel alive', False, str(e))
close_ch(mf)
# Detail note: on a MISS `err` is the LAST sample, and by then
# GRUB has slept its 5 s and REDRAWN THE MENU -- so a bare dump
# of `err` shows a healthy menu and reads as though the leg never
# ran.  echo_seen disambiguates "never appeared" from "appeared
# and scrolled"; the rows are labelled so the redraw is obvious.
check('leg C: distinctive no-match echo visible'
      ' (gated on leg A matching)',
      legA_ok and 'ForthOS: partition GUID not found' in err,
      f'legA_ok={legA_ok} echo_seen={echo_seen} '
      f'last sample (menu redraw if echo missed): {vga_rows(err)}')
# Nothing chainloaded => the serial line carries no kernel
# output for the whole window.
legc_ser.settimeout(1)
silent = drain(legc_ser).decode('ascii', errors='replace')
close_ch(legc_ser)
# Same gate: leg A reached 'ok' on this harness/port off this
# same disk, so "no ok" here is attributable to the GUID
# mismatch and not to a harness that never delivers serial.
check('leg C: serial silent (gated on leg A seeing ok)',
      legA_ok and 'ok' not in silent,
      f'legA_ok={legA_ok} {ser_head(silent)}')
qemu_kill()

print('\nStage 7: leg D -- reverted bake dies in disk_error')
LEGD = 'build/g6-disk-legd.img'
subprocess.run(['cp', '--sparse=always', DISK, LEGD],
               check=True)
# Poke the SENTINEL back over the baked LBA -- on a COPY. The
# offsets are the ones stage 3 derived from the artifact
# (LBA_OFF from vbr.bin's sentinel DAP; OWN_BASE probed live).
SENTINEL = 0xDEADBEEF
with open(LEGD, 'r+b') as f:
    f.seek(OWN_BASE * SEC + LBA_OFF)
    f.write(struct.pack('<I', SENTINEL))
    f.flush()
    os.fsync(f.fileno())
# READBACK.  Leg D's entire product is ATTRIBUTION.  A green leg
# D says "reverting the bake kills the boot loudly".  A RED leg D
# with no readback says either "the VBR did not die" OR "we wrote
# 0xDEADBEEF into the wrong four bytes and the VBR is fine" --
# two failures with opposite fixes, indistinguishable from the
# transcript.  On iron that ambiguity costs an hour; here it
# costs ten lines.  Prove the precondition before booting on it,
# exactly as leg C proves its scratch cfg before serving it.
with open(LEGD, 'rb') as f:
    legd_vbr = rd(f, OWN_BASE)
with open(DISK, 'rb') as f:
    disk_vbr_now = rd(f, OWN_BASE)
legd_word = struct.unpack('<I', legd_vbr[LBA_OFF:LBA_OFF + 4])[0]
disk_word = struct.unpack('<I', disk_vbr_now[LBA_OFF:LBA_OFF + 4])[0]
fatal('leg D: sentinel readback at VBR-LBA-OFF',
      legd_word == SENTINEL,
      f'LBA_OFF={LBA_OFF} OWN_BASE={OWN_BASE} '
      f'legd=0x{legd_word:08X} want=0x{SENTINEL:08X}')
# ...and it landed on the COPY, not the original.  Inequality
# ALONE would also be satisfied by an installed disk corrupted
# some other way, so assert what the original must still say:
# the real baked OWN-BASE+1.  (Stage 3 asserted that too, but
# legs A and B have BOOTED off DISK since, so re-reading it here
# is a fresh fact, not a restatement.)  disk_word is already in
# hand, so this costs nothing.  Together the two fatals read:
# the copy is sentinel-bearing, the original is correctly baked,
# and they are not the same bytes.
fatal('leg D: copy differs; installed disk VBR still baked',
      legd_vbr != disk_vbr_now and disk_word == OWN_BASE + 1,
      f'legd=0x{legd_word:08X} disk=0x{disk_word:08X} '
      f'want_disk=0x{OWN_BASE + 1:08X} differ={legd_vbr != disk_vbr_now}')
qemu_net_boot(LEGD)
# Same fast menu-detect-then-select as leg C, for the same
# reason. MEASURED 2026-08-11: with the SLOW helpers a single
# sendkey costs ~11 s, so the plan's poll_grub_menu + keys shape
# delivered the keys ~22 s after the menu appeared, GRUB's 5 s
# timeout always won, and leg D silently tested the MEMDISK
# instance while still reporting a pass on its serial check
# (discriminator read 130367488, nonzero = memdisk). Detecting
# the menu at 0.3 s cadence and selecting within ~1 s removes
# the race and keeps the planned 'GRUB menu up' assertion.
legd_ser = track(serial_connect(tries=5))  # attach before GRUB
fatal('leg D: serial attached before GRUB runs',
      legd_ser is not None)
mfd = monfast_or_fatal('leg D')
try:
    menu = poll_grub_menu_fast(mfd)
    fatal('leg D: GRUB menu up', 'ForthOS - memdisk' in menu,
          vga_rows(menu))
    mfd.sendkey('down')
    mfd.sendkey('ret')
except MonitorDown as e:
    fatal('leg D: monitor channel alive', False, str(e))
time.sleep(30)
# disk_error ends in cli/hlt: the screen is stable, read it via
# the monitor (crash forensics -- the ruled-legal use).
# Both strings below are transcribed from tests/test_vbr_boot.py
# smoke 2 ('DISK ERR' in vga / 'BMForth VBR' in vga), which
# asserts the SAME banner on the SAME halted screen.
# Read through the SAME MonFast connection: QEMU's monitor
# chardev serves one client at a time, so calling read_vga_text()
# while mfd is still attached would contend for the socket.
try:
    vga = mfd.vga()
except MonitorDown as e:
    vga = f'<monitor down: {e}>'
close_ch(mfd)
check('leg D: DISK ERR on halted screen', 'DISK ERR' in vga,
      vga_rows(vga))
check('leg D: variant banner (right loader ran)',
      'BMForth VBR' in vga, vga_rows(vga))
# Drain the socket that has been attached since before GRUB ran,
# so silence here means nothing ever printed -- not that we
# arrived after the banner had already gone out.
legd_ser.settimeout(1)
silent = drain(legd_ser).decode('ascii', errors='replace')
close_ch(legd_ser)
# De-alias: gated on leg A having reached ok on the SAME
# harness/port, so "no ok" is attributable to the sentinel.
check('leg D: no ok (gated on leg A seeing ok)',
      legA_ok and 'ok' not in silent,
      f'legA_ok={legA_ok} {ser_head(silent)}')
qemu_kill()

print(f'\nPassed: {PASS}/{PASS + FAIL}')
sys.exit(1 if FAIL else 0)
