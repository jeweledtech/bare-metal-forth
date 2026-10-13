#!/usr/bin/env python3
"""HAL per-machine bindings (docs/TASK_HAL_MACHINE.md): HAL-MATCH binds
from SMBIOS type 1, on the combined image booted by BIOS (SeaBIOS), QEMU
told what to report.  The test entries are typed at the prompt as the
doc writes them; nothing here is a real machine.

  python3 tests/test_hal_match.py <port> [image]

  M0 / N0 (each boot): HAL-MATCH block-loads; every entry line accepted.
  Boot 1, -smbios type=1,manufacturer=ForthGate,product=MatchTest; entries
  ForthGate / MatchTest (FB-BASE -> TM-BASE, FB-FLUSH -> TM-FLUSH) and
  ForthGate / OtherBox (FB-BASE -> TM-OTHER, the newest):
  M1  MATCH-BIND prints `Machine: ForthGate / MatchTest`, then exactly
      `' TM-BASE BIND FB-BASE`, the entry's note `Note: FB-FLUSH here
      only counts` (MATCH-NOTE: printed, binds nothing) and `' TM-FLUSH
      BIND FB-FLUSH`, in written order, and nothing about TM-OTHER.
  M2  HAL-LIST: FB-BASE and FB-FLUSH bound to TM-BASE's and TM-FLUSH's
      XTs; FB-BASE returns TM-SCR; FB-FLUSH runs TM-FLUSH (2 calls counted).
  M3  BLK-READ and BLK-WRITE: the same HAL-LIST lines as before the match.
  M4  `BINDS SPACE TM-BASE` is refused, naming SPACE; MATCH-LIST shows both
      entries with their bindings and note unchanged (OtherBox: one).
  M5  direct words: ! @ C! C@ on a variable; INB of the PIC mask (0x21)
      equals its value before the match.
  M6  DEPTH 0.
  Boot 2, product=NoMatch, the same entries:
  N1  MATCH-BIND prints `No machine entry for ForthGate / NoMatch: the
      defaults stay`, and no BIND line.
  N2  HAL-LIST after = HAL-LIST before, every line; FB-BASE = B8000.
  N3  DEPTH 0.
"""
import atexit, hashlib, os, re, shutil, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import qemu_pid          # noqa: E402
import serial as ser     # noqa: E402

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4405
B = os.path.join(ROOT, 'build')
D = os.path.join(B, 'test-hal-match.d')
os.makedirs(D, exist_ok=True)
COMBINED = sys.argv[2] if len(sys.argv) > 2 else os.path.join(B, 'combined.img')
SRC = os.path.join(ROOT, 'forth', 'dict', 'hal-match.fth')
failures, checks = [], 0


def check(label, cond, detail=''):
    global checks
    checks += 1
    print(f'[{"PASS" if cond else "FAIL"}] {label} {detail}', flush=True)
    if not cond:
        failures.append(label)


for p in (COMBINED, SRC, os.path.abspath(__file__)):
    h = hashlib.sha256(open(p, 'rb').read()).hexdigest() if os.path.exists(p) else 'ABSENT'
    print(f'input sha256 {h}  {p}', flush=True)


def send(s, cmd, budget=30):
    rep, how = ser.send_until_prompt(s, cmd, budget=budget)
    body = rep.split('\r\n', 1)[1] if '\r\n' in rep else ''
    print(f'>>> {cmd}\n    {body.strip()[-240:]!r}  [{how}]', flush=True)
    return body


def nums(b):
    return re.findall(r'(-?[0-9A-F]+) ok', b)


def hal_rows(b):
    return {m.group(1): m.group(2) for m in re.finditer(r'^(\S+) -> (.+?)\s*$', b, re.M)}


def boot(product):
    F, I = os.path.join(D, 'floppy.img'), os.path.join(D, 'ide.img')
    shutil.copyfile(COMBINED, F)
    shutil.copyfile(COMBINED, I)      # the blocks: the kernel reads the IDE slave
    pf = qemu_pid.pidfile(f'hal-match-{product}')
    atexit.register(qemu_pid.kill_pidfile, pf)
    p = subprocess.Popen(['qemu-system-i386', '-drive', f'file={F},format=raw,if=floppy',
                          '-drive', f'file={I},format=raw,if=ide,index=1',
                          '-smbios', f'type=1,manufacturer=ForthGate,product={product}',
                          '-serial', f'tcp:127.0.0.1:{PORT},server=on,wait=off',
                          '-display', 'none', '-pidfile', pf],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    qemu_pid.wait_started(p, pf, PORT, f'hal-match ({product})')
    return ser.connect_and_sync(PORT, budget=60), pf, p


# The entries, typed as docs/TASK_HAL_MACHINE.md writes them.
ENTRIES = [
    'ONLY FORTH DEFINITIONS ALSO HAL ALSO HAL-MATCH HEX',
    'CREATE TM-SCR 10 ALLOT  VARIABLE TM-N  VARIABLE TM-V',
    ': TM-BASE ( -- a ) TM-SCR ;  : TM-FLUSH ( -- ) 1 TM-N +! ;  : TM-OTHER ( -- a ) 4321 ;',
    ': TM-IDS S" ForthGate" S" MatchTest" ;',
    ': TO-IDS S" ForthGate" S" OtherBox" ;',
    ': TM-NOTE S" FB-FLUSH here only counts" ;',
    'TM-IDS MATCH-ENTRY',
    'BINDS FB-BASE TM-BASE',
    'TM-NOTE MATCH-NOTE',
    'BINDS FB-FLUSH TM-FLUSH',
    'TO-IDS MATCH-ENTRY',
    'BINDS FB-BASE TM-OTHER',
    'DECIMAL',
]


def setup(s, tag):
    """Load HAL-MATCH and type the entries: scored (the vocabulary is
    what is under test), not an instrument control."""
    # control: the catalog is readable (SMBIOS is in every image); without
    # it a missing block disk reads as "HAL-MATCH absent" (2026-10-12)
    send(s, 'S" SMBIOS" LOAD-VOCAB', 90)
    if re.search(r'\S+ \?', send(s, 'ALSO SMBIOS PREVIOUS')):
        print('INSTRUMENT FAIL: SMBIOS did not load: the catalog is unreadable -- no score', flush=True)
        sys.exit(3)
    out = [send(s, 'S" HAL-MATCH" LOAD-VOCAB', 90)] + [send(s, line) for line in ENTRIES]
    bad = [l for l, b in zip(['LOAD-VOCAB'] + ENTRIES, out) if re.search(r'\S+ \?', b)]
    check(f'{tag}0 HAL-MATCH block-loads and every entry line is accepted', not bad, f'(failed: {bad})')


# ---- Boot 1: a matching machine
s, pf, p = boot('MatchTest')
try:
    setup(s, 'M')
    b = send(s, 'HEX BINDS SPACE TM-BASE DECIMAL')
    refused = 'BINDS: SPACE is not a HAL vector' in b
    bl = send(s, 'MATCH-LIST')
    want_list = ['ForthGate / OtherBox', "  ' TM-OTHER BIND FB-BASE",
                 'ForthGate / MatchTest', "  ' TM-BASE BIND FB-BASE", '  Note: FB-FLUSH here only counts',
                 "  ' TM-FLUSH BIND FB-FLUSH"]
    got_list = [l.rstrip() for l in bl.splitlines() if l.strip() and l.strip() != 'ok']
    check('M4 BINDS refuses a non-vector, naming it; MATCH-LIST shows both entries, bindings unchanged',
          refused and got_list == want_list, f'({b.strip()!r}; list {got_list})')
    before = hal_rows(send(s, 'HAL-LIST'))
    pic = nums(send(s, 'HEX 21 INB . DECIMAL'))[-1:]
    b = send(s, 'MATCH-BIND')
    lines = [l.rstrip() for l in b.splitlines() if l.strip() and l.strip() != 'ok']
    check('M1 MATCH-BIND: Machine line, then exactly the two BINDs and the note, in written order, nothing of TM-OTHER',
          lines == ['Machine: ForthGate / MatchTest', "' TM-BASE BIND FB-BASE", 'Note: FB-FLUSH here only counts',
                    "' TM-FLUSH BIND FB-FLUSH"],
          f'({lines})')
    after = hal_rows(send(s, 'HAL-LIST'))
    xts = re.findall(r'([0-9A-F]+) ', send(s, "HEX ' TM-BASE U. ' TM-FLUSH U. CR DECIMAL"))
    b = send(s, 'HEX FB-BASE TM-SCR = .  0 TM-N !  FB-FLUSH FB-FLUSH  TM-N @ . DECIMAL')
    check('M2 HAL-LIST shows FB-BASE -> TM-BASE, FB-FLUSH -> TM-FLUSH; the calls reach them',
          len(xts) >= 2 and after.get('FB-BASE') == xts[0] and after.get('FB-FLUSH') == xts[1]
          and nums(b)[-1:] == ['2'] and re.search(r'-1 2 ok', b) is not None,
          f'(HAL-LIST {after}; xts {xts}; {b.strip()!r})')
    check('M3 BLK-READ and BLK-WRITE unchanged by the match',
          all(before.get(k) is not None and before.get(k) == after.get(k) for k in ('BLK-READ', 'BLK-WRITE')),
          f'(before {before}; after {after})')
    b = send(s, 'HEX 1234 TM-V ! TM-V @ .  41 TM-V C! TM-V C@ .  21 INB . DECIMAL')
    check('M5 direct ! @ C! C@ and INB still work (PIC mask as before the match)',
          re.search(r'1234 41 ' + (pic[0] if pic else 'X') + r' ok', b) is not None, f'({b.strip()!r}; pic {pic})')
    b = send(s, 'ONLY FORTH DEFINITIONS DECIMAL DEPTH .')
    check('M6 DEPTH 0', nums(b)[-1:] == ['0'], f'({b.strip()!r})')
finally:
    s.close()
    qemu_pid.kill_pidfile(pf)
    p.wait(timeout=10)

# ---- Boot 2: a machine no entry names
s, pf, p = boot('NoMatch')
try:
    setup(s, 'N')
    before = send(s, 'HAL-LIST')
    b = send(s, 'MATCH-BIND')
    check('N1 no entry matches: said plainly, no BIND line',
          'No machine entry for ForthGate / NoMatch: the defaults stay' in b and 'BIND' not in b,
          f'({b.strip()!r})')
    after = send(s, 'HAL-LIST')
    fb = send(s, 'HEX FB-BASE . DECIMAL')
    check('N2 HAL-LIST unchanged, every line; FB-BASE = B8000',
          hal_rows(before) == hal_rows(after) and len(hal_rows(before)) >= 4 and nums(fb)[-1:] == ['B8000'],
          f'(before {hal_rows(before)}; after {hal_rows(after)}; {fb.strip()!r})')
    b = send(s, 'ONLY FORTH DEFINITIONS DECIMAL DEPTH .')
    check('N3 DEPTH 0', nums(b)[-1:] == ['0'], f'({b.strip()!r})')
finally:
    s.close()
    qemu_pid.kill_pidfile(pf)
    p.wait(timeout=10)

print(f'Passed: {checks - len(failures)}/{checks}', flush=True)
sys.exit(0 if not failures else 1)
