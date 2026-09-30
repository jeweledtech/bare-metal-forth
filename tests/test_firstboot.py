#!/usr/bin/env python3
"""FIRSTBOOT wizard gate: docs/TASK_FORTHOS_FIRSTBOOT.md section 8
steps 1-3 (screen 1 fork + gates, screen 2 detection + offline path,
screen 4 completion).  Screens 2a (wired address) and 3 (install) are
NOT built; the checks below assert that they are named as not built,
never that they work.

firstboot.fth is public and block-loaded: nothing calls it at boot
(whether it should autostart is an open owner decision).

Two fixtures, one script (argv[4]):
  lan      -nic none + rtl8139 (driven: RTL8139 is on the stick)
           + e1000 (8086:100E, no vocabulary) + ahci
  offline  -nic none, no AHCI: PIIX IDE only.  Three of the four
           reference machines have no wired port; this is their path.

The screen is read through the QEMU monitor (pmemsave of 0xB8000)
because while the wizard loop runs, serial input belongs to KEY and
the interpreter cannot answer.

Pre-registered red (2026-09-29, written before the first run; red
tree = this worktree without forth/dict/firstboot.fth): 36 scored
checks per fixture.  Red: 1 (no placement), 2 (THRU not attempted),
3-33 (each needs a FIRSTBOOT word or a wizard screen on the VGA).
Green on red: 34 (no dirty block buffer), 35 (IDE image unchanged),
36 (DEPTH 0 at exit) -- the red path writes nothing and leaves
nothing.  Red totals 3/36 per fixture, exit 1.

First red run (lan) scored 2/36: check 34's first read was None.
Instrument defect, not a wizard finding: this interpreter runs the
rest of a line after an unknown word, so checks 10-12's bare TYPE
dumped ~33KB of low memory to serial and VGA on the red tree, and
the flood was still arriving at phase 6.  Fixed by guarding TYPE on
DEF?; prediction unchanged, red re-run.  Second red run, still
2/36, same check: the flood was not the mechanism.  Phase 5's
keystrokes reach the interpreter on the red tree, and the last one
(ESC, no CR; check 33's alive() short-circuits) prefixed check 34's
line.  Fixed by ending the partial line before phase 6.

Green attempt 1 (lan) 34/36.  Check 30 flagged rows 1 and 23: the
full-width dividers, drawn to col 79 by design -- instrument defect,
dividers now excluded.  Check 21 read 'rtl8139.fth loaded' where the
prediction said 'on this stick': a real defect.  Kernel FIND ignores
its argument (find_ searches word_buffer, the interpreter's last
parsed word, and FIND pushes xt-or-0 over the untouched c-addr), so
WZ-LOADED? answered for 'WZ-DRAW', not for the name given, and every
vocabulary read as loaded -- G-DISK's lan pass was right only because
AHCI happens to be embedded.  Check 37 added to pin it: observed red
on the FIND-based build before the fix (a chain walk from
VAR_FORTH_LATEST).  Scored total becomes 37 per fixture.

2026-09-30, owner rulings: G-BOOT is a placeholder (unimplemented,
fail-closed, prints '----'); check 17 now asserts the placeholder,
not a gate.  Check 38 added: screen 4 on the install path
(WZ-INSTALLED set) shows the approved headline AND the whole support
block, which must appear on both paths.  Scored total 38.

Instrument controls (fatal, unscored): interpreter alive; DEF? says
yes to PCI-FIND and no to a word that never existed; the monitor's
pmemsave returns 4000 bytes and sees a character written to VGA row
24 through UI-CORE's VGA-PUTC.
"""
import hashlib
import os
import re
import socket
import subprocess
import sys
import tempfile
import time

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4588
IMG = sys.argv[2] if len(sys.argv) > 2 else 'build/combined.img'
MON_PORT = int(sys.argv[3]) if len(sys.argv) > 3 else 4589
FIXTURE = sys.argv[4] if len(sys.argv) > 4 else 'lan'
IDE_IMG = sys.argv[5] if len(sys.argv) > 5 else 'build/combined-ide.img'
if FIXTURE not in ('lan', 'offline'):
    print(f'INSTRUMENT FAIL: unknown fixture {FIXTURE!r}')
    sys.exit(3)


def sha(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


print(f'input sha256 {sha(IMG)}  {IMG}')
_src = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'forth', 'dict', 'firstboot.fth')
print('input sha256 ' + (sha(_src) if os.path.exists(_src)
                         else '(absent)') + f'  {_src}')
print(f'fixture {FIXTURE}')
IDE_BEFORE = sha(IDE_IMG)

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_vocab_blocks(vocab_name):
    """Host-side catalog placement, the scan write-catalog uses
    (test_pci_bar.py's resolver, unchanged)."""
    result = subprocess.run([sys.executable, '-c', f"""
import os
import importlib.util
spec = importlib.util.spec_from_file_location('wc', os.path.join(
    '{PROJECT_DIR}', 'tools', 'write-catalog.py'))
wc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wc)
vocabs = wc.scan_vocabs(os.path.join('{PROJECT_DIR}', 'forth', 'dict'))
_nc = (len(vocabs) + wc.CATALOG_DATA_LINES - 1) // wc.CATALOG_DATA_LINES
nb = 1 + _nc
for v in vocabs:
    nb = wc.place_vocab(nb, v['blocks_needed'])
    if v['name'] == '{vocab_name}':
        print(f"{{nb}} {{nb + v['blocks_needed'] - 1}}")
        break
    nb += v['blocks_needed']
"""], capture_output=True, text=True, timeout=10)
    parts = result.stdout.split()
    return (int(parts[0]), int(parts[1])) if len(parts) == 2 else (None, None)


s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(10)
for _ in range(20):
    try:
        s.connect(('127.0.0.1', PORT))
        break
    except OSError:
        time.sleep(0.5)
else:
    print('FAIL: connect')
    sys.exit(1)
time.sleep(2)
try:
    while True:
        s.recv(4096)
except Exception:
    pass


def drain(wait):
    time.sleep(wait)
    s.settimeout(2)
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


def send(cmd, wait=1.0):
    s.sendall((cmd + '\r').encode())
    return drain(wait)


def keys(raw, wait=1.5):
    """Raw keystrokes for the wizard's KEY loop (no CR appended)."""
    s.sendall(raw.encode())
    return drain(wait)


def body_of(raw):
    return raw.split('\n', 1)[1] if '\n' in raw else raw


def val(expr, wait=1.5):
    raw = send(f'DECIMAL {expr} .', wait)
    body = body_of(raw)
    if '?' in body:
        return None, raw
    nums = re.findall(r'-?\d+', body)
    return (int(nums[-1]) if nums else None), raw


def stack(expr, wait=1.5):
    zap()
    raw = send(f'DECIMAL {expr} .S', wait)
    body = body_of(raw)
    zap()
    if '?' in body:
        return None, raw
    m = re.search(r'<([^>]*)>', body)
    return ([int(x) for x in m.group(1).split()] if m else None), raw


# ---- QEMU HMP monitor: the screen, read from outside the guest ----
_mon = None


def _mon_read_prompt():
    buf = b''
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            d = _mon.recv(4096)
        except socket.timeout:
            break
        if not d:
            break
        buf += d
        if buf.rstrip().endswith(b'(qemu)'):
            break
    return buf.decode('utf-8', errors='replace')


def mon(cmd, wait=0.5):
    global _mon
    if _mon is None:
        _mon = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _mon.settimeout(5)
        _mon.connect(('127.0.0.1', MON_PORT))
        _mon_read_prompt()
    _mon.sendall((cmd + '\n').encode())
    time.sleep(wait)
    return _mon_read_prompt()


_tmp = tempfile.mkdtemp(prefix='firstboot-vga-')


def screen():
    """25 rows of (text, attrs) from physical 0xB8000."""
    path = os.path.join(_tmp, 'vga.bin')
    if os.path.exists(path):
        os.remove(path)
    mon(f'pmemsave 0xb8000 4000 "{path}"', 0.8)
    try:
        with open(path, 'rb') as f:
            raw = f.read()
    except OSError:
        return None
    if len(raw) != 4000:
        return None
    rows = []
    for r in range(25):
        seg = raw[r * 160:(r + 1) * 160]
        rows.append((bytes(seg[0::2]).decode('latin-1'), list(seg[1::2])))
    return rows


def row_with(scr, needle):
    """Index of the first row containing NEEDLE, or None."""
    if scr is None:
        return None
    for i, (t, _) in enumerate(scr):
        if needle in t:
            return i
    return None


def row_attrs_of(scr, needle):
    """Attributes under NEEDLE's own characters (None if absent)."""
    r = row_with(scr, needle)
    if r is None:
        return None
    t, a = scr[r]
    c = t.index(needle)
    return a[c:c + len(needle)]


def is_grey(scr, needle):
    """Every non-space character of NEEDLE's row is attribute 8."""
    r = row_with(scr, needle)
    if r is None:
        return False
    t, a = scr[r]
    cells = [a[i] for i, ch in enumerate(t) if ch != ' ']
    return bool(cells) and all(x == 8 for x in cells)


def is_focused(scr, needle):
    at = row_attrs_of(scr, needle)
    return bool(at) and all(x == 0x70 for x in at)


def dump(scr):
    if scr is None:
        return '(no screen)'
    return '\n'.join(f'{i:2}|{t.rstrip()}' for i, (t, _) in enumerate(scr))


PASS = FAIL = 0
N = 0


def check(name, ok, detail=''):
    global PASS, FAIL, N
    N += 1
    if ok:
        PASS += 1
        print(f'  PASS {N:2}: {name}')
    else:
        FAIL += 1
        print(f'  FAIL {N:2}: {name}' + (f' -- {detail}' if detail else ''))
    return ok


def instrument(name, ok, detail=''):
    if not ok:
        print(f'INSTRUMENT FAIL: {name} -- {detail} -- aborting, no score')
        sys.exit(3)
    print(f'  instrument: {name}')


def alive():
    v, _ = val('7 6 *')
    return v == 42


def zap():
    send('ZAP')
    v, raw = val('ZBAD @')
    if v != 0:
        print(f'INSTRUMENT FAIL: ZAP refused (ZBAD={v}): {body_of(raw)!r}')
        sys.exit(3)


print('\n=== Phase 0: instrument controls (fatal on failure) ===')
instrument('interpreter alive', alive())
send('ONLY FORTH DEFINITIONS')
send('ALSO PCI-ENUM')
send(': DEF? WORD FIND NIP ;')
send('VARIABLE ZN')
send('VARIABLE ZBAD')
send(': ZAP 0 ZBAD !  DEPTH DUP 0< SWAP 1024 > OR '
     'IF -1 ZBAD ! EXIT THEN '
     '64 ZN !  BEGIN DEPTH 0<> ZN @ 0> AND '
     'WHILE DROP -1 ZN +! REPEAT ;')
zap()
_pos, _ = val('DEF? PCI-FIND')
_neg, _ = val('DEF? ZZZ-NEVER-DEFINED')
instrument('DEF? says yes and no', _pos not in (None, 0) and _neg == 0,
           f'PCI-FIND={_pos} ZZZ-NEVER-DEFINED={_neg}')
send('ALSO UI-CORE  90 7 0 24 VGA-PUTC  PREVIOUS')
_scr = screen()
instrument('monitor pmemsave reads the VGA (Z at row 24 col 0)',
           _scr is not None and _scr[24][0][0] == 'Z',
           dump(_scr)[-200:])

print('\n=== Phase 1: block-load FIRSTBOOT ===')
bs, be = get_vocab_blocks('FIRSTBOOT')
check('FIRSTBOOT has catalog placement', bs is not None,         # 1
      'forth/dict/firstboot.fth absent from the scan')
if bs is not None:
    print(f'  loading FIRSTBOOT ({bs}-{be} THRU)...')
    send(f'DECIMAL {bs} {be} THRU', 12)
    check('FIRSTBOOT blocks load (alive after THRU)', alive())  # 2
else:
    check('FIRSTBOOT blocks load (alive after THRU)', False,    # 2
          'no placement: THRU not attempted')
send('ONLY FORTH DEFINITIONS')
send('ALSO FIRSTBOOT')
v, _ = val('DEF? FIRSTBOOT-RUN')
check('FIRSTBOOT-RUN defined under ALSO FIRSTBOOT',              # 3
      v not in (None, 0), f'DEF? -> {v}')

print('\n=== Phase 2: pure words (storage kind, NIC vocabulary) ===')
# DECIMAL values: 8086h=32902 1022h=4130 10ECh=4332 8168h=33128
# 8139h=33081 8029h=32809 100Eh=4110
for n, (args, want, what) in enumerate([
        ('32902 6 1', 1, 'SATA/AHCI -> 1 AHCI'),                 # 4
        ('4130 8 2', 2, 'NVMe -> 2'),                             # 5
        ('32902 4 0', 3, 'Intel RAID (VMD/RST) -> 3'),            # 6
        ('4130 4 0', 5, 'non-Intel RAID -> 5 unsupported'),       # 7
        ('32902 1 128', 4, 'IDE -> 4'),                           # 8
        ('32902 6 0', 5, 'SATA not AHCI -> 5 unsupported')]):     # 9
    st, raw = stack(f'{args} WZ-STOR-KIND')
    check(f'WZ-STOR-KIND {what}', st == [want], f'{st} {body_of(raw)!r}')
# TYPE only when the word exists: this interpreter runs the rest of a
# line after an unknown word, so on the red tree a bare TYPE would dump
# 33128 bytes from address 4332 (first red run, see docstring).
_nic, _ = val('DEF? WZ-NIC-VOCAB')
for dev, want in (('33128', 'RTL8168'), ('33081', 'RTL8139'),     # 10-12
                  ('32809', 'NE2000')):
    raw = (send(f'DECIMAL 4332 {dev} WZ-NIC-VOCAB TYPE', 1.5)
           if _nic not in (None, 0) else '(WZ-NIC-VOCAB undefined)\n')
    check(f'WZ-NIC-VOCAB 10EC:{int(dev):04X} -> {want}',
          want in body_of(raw) and '?' not in body_of(raw),
          f'{body_of(raw)!r}')
st, raw = stack('32902 4110 WZ-NIC-VOCAB')
check('WZ-NIC-VOCAB 8086:100E -> 0 0 (no vocabulary)',            # 13
      st == [0, 0], f'{st} {body_of(raw)!r}')

# 37 (added after green attempt 1, see docstring): the vocabulary
# probe must answer about the NAME it is given.  Scored here, printed
# last in the numbering so 1-36 keep their registered meaning.
_n37 = stack('S" ZZZ-NEVER-DEFINED" WZ-LOADED?')[0]
_p37 = stack('S" PCI-ENUM" WZ-LOADED?')[0]

print('\n=== Phase 3: screen 1 built and rendered (no loop) ===')
send('WZ-S1 WZ-DRAW', 3)
s1 = screen()
check('title row names Try or Install',                          # 14
      row_with(s1, 'Try or Install') == 0, dump(s1))
check('Run-from-stick button present and focused',               # 15
      row_with(s1, '[Run ForthOS from this stick]') is not None
      and is_focused(s1, 'Run ForthOS from this stick'))
check('Try path says settings last until power-off',             # 16
      row_with(s1, 'until power-off') is not None)
# 17 asserts the PLACEHOLDER, not the gate: G-BOOT is unimplemented
# (needs boot-path provenance + legacy-entry offer).  It must say so
# with '----' (unmeasured), never 'pass'.
r17 = row_with(s1, 'G-BOOT   ----  not implemented')
check('G-BOOT placeholder: says not implemented, never pass',     # 17
      r17 is not None and 'pass' not in s1[r17][0])
if FIXTURE == 'lan':
    r = row_with(s1, 'G-DISK   pass  AHCI at ')
    check('G-DISK passes on the AHCI controller, with its ABAR',  # 18
          r is not None and 'ABAR ' in s1[r][0])
else:
    check('G-DISK fails, IDE only, named',                        # 18
          row_with(s1, 'G-DISK   FAIL  IDE only') is not None)
check('G-SPACE fails closed: not checked, INSTALL stack named',  # 19
      row_with(s1, 'G-SPACE  FAIL  not checked') is not None)
check('Install row greyed and says unavailable',                 # 20
      row_with(s1, 'Install ForthOS on this machine') is not None
      and 'unavailable' in s1[row_with(
          s1, 'Install ForthOS on this machine')][0]
      and is_grey(s1, 'Install ForthOS on this machine'))

print('\n=== Phase 4: screen 2 built and rendered (no loop) ===')
send('WZ-S2 WZ-DRAW', 3)
s2 = screen()
s2_up = row_with(s2, 'Network') == 0
if FIXTURE == 'lan':
    r = row_with(s2, '10EC:8139')
    check('RTL8139 row: driven button, vocab file, on stick, '    # 21
          'not grey',
          s2_up and r is not None and '[' in s2[r][0]
          and 'rtl8139.fth' in s2[r][0]
          and 'on this stick' in s2[r][0]
          and not is_grey(s2, '10EC:8139'), dump(s2))
    r = row_with(s2, '8086:100E')
    check('e1000 row: named, not yet available, greyed',           # 22
          s2_up and r is not None and 'not yet available' in s2[r][0]
          and is_grey(s2, '8086:100E'))
    want = 'network controllers: 2'
else:
    check('no controller: says none detected',                    # 21
          s2_up and row_with(s2, 'No network controllers detected')
          is not None, dump(s2))
    check('no greyed controller rows',                             # 22
          s2_up and not any(is_grey(s2, t) for t, _ in s2[2:20]
                            if t.strip()))
    want = 'network controllers: 0'
check('Continue-without-network row marked DEFAULT and focused',  # 23
      s2_up and row_with(s2, 'Continue without a network') is not None
      and 'DEFAULT' in s2[row_with(s2, 'Continue without a network')][0]
      and is_focused(s2, 'Continue without a network'))
check(f'footer counts: {want}',                                    # 24
      s2_up and row_with(s2, want) is not None)

print('\n=== Phase 5: the loop, driven by keystrokes ===')
send('FIRSTBOOT-RUN', 3)
a = screen()
check('FIRSTBOOT-RUN shows screen 1',                             # 25
      row_with(a, 'Try or Install') == 0, dump(a))
keys('\r', 3)
b = screen()
on2 = row_with(b, 'Network') == 0
check('ENTER on Run-from-stick reaches screen 2', on2, dump(b))   # 26
keys('R', 4)
c = screen()
check('R rescans: still screen 2, same controller count',         # 27
      on2 and row_with(c, 'Network') == 0
      and row_with(c, want) is not None, dump(c))
if FIXTURE == 'lan':
    keys('\t', 2)
    keys('\r', 3)
    d = screen()
    check('driven row: says address setup not built, stays',      # 28
          row_with(d, 'Network') == 0
          and row_with(d, 'not built yet') is not None
          and is_focused(d, 'Continue without a network'), dump(d))
else:
    keys('\t', 2)
    d = screen()
    check('TAB with one focusable keeps focus on Continue',        # 28
          row_with(d, 'Network') == 0
          and is_focused(d, 'Continue without a network'), dump(d))
keys('\r', 3)
e = screen()
on4 = row_with(e, 'Forth Dimension') is not None
check('ENTER on Continue reaches screen 4', on4, dump(e))         # 29
full = ['Here the dictionary is the system:',
        'docs.jeweledtech.com',
        'forever grateful.',
        'SUPPORT  patreon.com/c/JeweledTechbyJollyGenius',
        'STAR US  github.com/jeweledtech/bare-metal-forth',
        'EXTEND   jeweledtech.github.io/bare-metal-forth',
        'UBT pipeline, metacompiler)',
        'the free core leaves alone.',
        'press ENTER to drop into the interpreter']
missing = [x for x in full if row_with(e, x) is None]
wrapped = [i for i, (t, _) in enumerate(e or []) if i > 0
           and t[79] != ' ' and set(t) != {'-'} and on4]
check('screen 4 support block whole on one page, nothing at '     # 30
      'col 79', on4 and not missing and not wrapped,
      f'missing={missing} col79={wrapped}')
check('Try-path headline does not claim an installation',         # 31
      on4 and row_with(e, 'Your ForthOS session is ready.') is not None
      and row_with(e, 'installation is complete') is None)
keys('\r', 3)
check('ENTER on screen 4 returns to the interpreter',             # 32
      on4 and alive())
send('FIRSTBOOT-RUN', 3)
f = screen()
up1 = row_with(f, 'Try or Install') == 0
keys('\x1b', 3)
check('ESC on screen 1 returns to the interpreter',               # 33
      up1 and alive(), dump(f))

print('\n=== Phase 6: the Try path wrote nothing ===')
# End any partial line: on the red tree phase 5's keystrokes (ESC
# last, no CR) sit in the interpreter's line buffer.
send('', 2)
# BLK_BUF_HEADERS 0x28060 = 164000: 4 x [block# flags age]
dirty = []
for i in range(4):
    v, _ = val(f'{164000 + i * 12 + 4} @ 2 AND')
    dirty.append(v)
check('no block buffer is dirty', dirty == [0, 0, 0, 0],          # 34
      f'{dirty}')
check('IDE block image byte-identical to before the run',         # 35
      sha(IDE_IMG) == IDE_BEFORE)
v, _ = val('DEPTH')
check('DEPTH 0 at exit', v == 0, f'DEPTH={v}')                    # 36
send('1 WZ-INSTALLED ! WZ-S4 WZ-DRAW', 3)
g = screen()
send('0 WZ-INSTALLED !')
g_missing = [x for x in full if row_with(g, x) is None]
check('install path: approved headline AND the whole support '   # 38
      'block', row_with(g, 'Your ForthOS installation is complete.')
      is not None and not g_missing, f'missing={g_missing}')
check('WZ-LOADED? answers for its argument: no for a never-'   # 37
      'defined name, yes for PCI-ENUM',
      _n37 == [0] and _p37 is not None and len(_p37) == 1
      and _p37[0] != 0, f'never={_n37} PCI-ENUM={_p37}')

print(f'\nFIRSTBOOT ({FIXTURE}): {PASS}/{N} passed')
sys.exit(0 if FAIL == 0 else 1)
