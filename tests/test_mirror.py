#!/usr/bin/env python3
"""MIRROR gate (docs/TASK_MIRROR_FIX.md): MIRROR writes only where it may,
says so when a write fails, and its image reads back on both paths.

Scratch copies only.  The shipped writers are installed on them:
  ATA path  floppy + IDE copies of the combined image, `(BLK-WRITE-ATA)`
            and `(BLK-READ-ATA)` installed (the boot default writer
            refuses everything).  The IDE copy is the block medium, so
            a MIRROR over the code store overwrites packed source here.
  HP path   memdisk + the combined image, an HP-549 disk (tests/
            g6_fixture.py + FORTHOS partition at LBA 34-582) on AHCI,
            `AHCI-INIT AHCI-RW`.  Needs AHCI (a paid vocabulary): in a
            clone without forth/dict/ahci.fth these cases are SKIPPED,
            and a skip is never counted as a pass.

Cases (the task doc's red table):
  M1  `900 MIRROR`, ATA writer: 900 lies inside a vocabulary's blocks.
      Refused, naming that vocabulary (looked up in catalog_layout, so
      the case survives layout moves); disk and DEPTH unchanged.
  M2  HP path, `100 MIRROR`: block 100 is code store AND inside the
      FORTHOS partition, and the image runs over the settings,
      telemetry and MIRROR reservations. The refusal names every
      overlap: the vocabulary at block 100, each reserved range (from
      write-catalog) and the partition's LBA range; disk unchanged.
  M3  ATA path, a fixture writer that passes through to
      `(BLK-WRITE-ATA)` but refuses block 221 (inside the 216 image):
      `MIRROR FAILED: 1 of <m> blocks not written`, no "saved"; every
      other dictionary block on disk (compared with M4's image, written
      next with nothing compiled between).
  M4  MIRROR-BLK is 216; `MIRROR-BLK MIRROR`, `MIRROR?` true and
      MIRROR-INFO's HERE equal to the header on disk, both paths (the HP
      path can only read it back through the persistent reader).
  M5  ATA path: `: MIRTEST 4242 ;`, MIRROR, reboot on the same disks,
      LOOKINGGLASS: MIRTEST answers 4242.
  M6  host: write-catalog reserves 216-535 for MIRROR (MIRROR_RESERVED,
      MIRROR_BLK), no vocabulary lies in it, it ends at or below the HP
      write ceiling, and mirror.fth's MIRROR-BLK and its settings and
      telemetry ranges agree with write-catalog's.

Explicit block numbers (900, 100, 216) are used for the writes so the
cases run on today's MIRROR as well; M4 checks MIRROR-BLK separately.
Predictions are written before each run, in the evidence directory the
task doc names, not here.
"""
import hashlib
import os
import re
import shutil
import struct
import subprocess
import sys
import time
from importlib.machinery import SourceFileLoader

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qemu_pid  # noqa: E402
import serial as ser  # noqa: E402

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4467
COMBINED = sys.argv[2] if len(sys.argv) > 2 else 'build/combined.img'
ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
D = os.path.join('build', 'test-mirror.d')
os.makedirs(D, exist_ok=True)
ASM = os.path.join(ROOT, 'src', 'kernel', 'forth.asm')
MIRROR_FTH = os.path.join(ROOT, 'forth', 'dict', 'mirror.fth')
WRITE_CATALOG = os.path.join(ROOT, 'tools', 'write-catalog.py')
AHCI_FTH = os.path.join(ROOT, 'forth', 'dict', 'ahci.fth')

src = open(ASM).read()
_m = re.search(r'^KERNEL_PADDED_SIZE\s+equ\s+0x([0-9A-Fa-f]+)', src, re.M)
_b = re.search(r'^BOOT_SECTOR_SIZE\s+equ\s+(\d+)', src, re.M)
if not (_m and _b):
    print('cannot derive the block offset from forth.asm', flush=True)
    sys.exit(2)
HEADER = int(_b.group(1)) + int(_m.group(1), 16)   # bytes before block 0
LBA0 = HEADER // 512                                 # LBA of block 0
BSIZE = 1024
MAGIC = struct.pack('<I', 0x464F5254)               # MIR-MAGIC in memory order
P6 = (34, 582)                                       # HP FORTHOS partition
REFUSED_BLK = 221

failures, skips = [], []
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


def skip(label, why):
    skips.append(label)
    print(f'[SKIPPED] {label} ({why})', flush=True)


for p in (COMBINED, ASM, MIRROR_FTH, WRITE_CATALOG, os.path.abspath(__file__)):
    print(f'input sha256 {hashlib.sha256(open(p, "rb").read()).hexdigest()}  {p}',
          flush=True)
if os.path.exists(AHCI_FTH):
    print(f'input sha256 {hashlib.sha256(open(AHCI_FTH, "rb").read()).hexdigest()}'
          f'  {AHCI_FTH}', flush=True)


def blocks(path, first, n):
    with open(path, 'rb') as f:
        f.seek(HEADER + first * BSIZE)
        return f.read(n * BSIZE)


def lbas(path, first, n):
    with open(path, 'rb') as f:
        f.seek(first * 512)
        return f.read(n * 512)


def disk_digest(path):
    """sha256 of LBA 0-65535 and the last 2048 sectors.  The fixture is
    a sparse ~1 TB file: every LBA a block can reach (block 0 is LBA
    225; the guard's ceiling is LBA 2048) and both GPT copies are
    inside these two ranges."""
    h = hashlib.sha256()
    size = os.path.getsize(path)
    with open(path, 'rb') as f:
        h.update(f.read(65536 * 512))
        f.seek(size - 2048 * 512)
        h.update(f.read())
    return h.hexdigest()


def nums(body, base=10):
    body = body.replace('ok', ' ')
    return [int(t, base) for t in re.findall(r'-?[0-9A-Fa-f]+', body)]


class Guest:
    def __init__(self, args, role):
        self.pf = qemu_pid.pidfile(role)
        err = os.path.join(D, f'{role}.err')
        self.proc = subprocess.Popen(
            ['qemu-system-i386'] + args +
            ['-serial', f'tcp:127.0.0.1:{PORT},server=on,wait=off',
             '-display', 'none', '-pidfile', self.pf],
            stdout=subprocess.DEVNULL, stderr=open(err, 'w'))
        qemu_pid.wait_started(self.proc, self.pf, PORT, role, err)
        self.s = ser.connect_and_sync(PORT, budget=60)

    def send(self, cmd, budget=30):
        rep, how = ser.send_until_prompt(self.s, cmd, budget=budget)
        body = rep.split('\r\n', 1)[1] if '\r\n' in rep else ''
        shown = body.strip()
        if len(shown) > 1500:
            shown = shown[:700] + f'\n  ... ({len(shown)} chars) ...\n' + shown[-700:]
        print(f'>>> {cmd}\n{shown}', flush=True)
        if how != 'prompt':
            print(f'  (read ended by {how})', flush=True)
        return body

    def depth(self):
        v = nums(self.send('DECIMAL DEPTH .'))
        return v[0] if v else None

    def close(self):
        try:
            self.s.close()
        finally:
            qemu_pid.kill_pidfile(self.pf)
            time.sleep(0.5)


def load_mirror(g):
    # The file's closing `." MIRROR vocabulary loaded"` prints nothing when
    # block-loaded (observed 2026-10-11), so the control is: no error
    # signature from the load, and a MIRROR word answers afterwards.
    r = g.send('S" MIRROR" LOAD-VOCAB', 90)
    r2 = g.send('USING MIRROR DECIMAL DICT-BLKS .')
    check('C1 MIRROR loads (no error, DICT-BLKS answers)',
          '?' not in r and '?' not in r2 and len(nums(r2)) == 1, fatal=True)
    check('C2 DEPTH 0 after load', g.depth() == 0, fatal=True)


def mirror_blk(g):
    """MIRROR-BLK's value, or None if it is not defined.

    An unknown word does not end the line here: the rest still runs.
    So never put `.` after it (an empty-stack `.` underflows, Bug #35):
    ask DEPTH first and print only when the constant pushed a cell.
    """
    r = g.send('DECIMAL MIRROR-BLK DEPTH .')
    if 'MIRROR-BLK ?' in r:
        return None
    if nums(r)[-1:] != [1]:
        return None
    v = nums(g.send('.'))
    return v[0] if v else None


def info_here(body):
    m = re.search(r'HERE:\s+([0-9A-Fa-f]+)', body)
    return int(m.group(1), 16) if m else None


# ---------------------------------------------------------------- M6 (host)
wc = SourceFileLoader('wc', WRITE_CATALOG).load_module()
res = getattr(wc, 'MIRROR_RESERVED', None)
check('M6a write-catalog: MIRROR_RESERVED = 216-535, MIRROR_BLK = 216',
      res == range(216, 536) and getattr(wc, 'MIRROR_BLK', None) == 216,
      f'(MIRROR_RESERVED {res}, MIRROR_BLK {getattr(wc, "MIRROR_BLK", None)})')
lay = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'catalog_layout.py')],
                     capture_output=True, text=True, cwd=ROOT).stdout
LAYOUT = []
for line in lay.splitlines():
    p = line.split()
    if len(p) == 3 and p[1].isdigit() and p[2].isdigit():
        LAYOUT.append((p[0], int(p[1]), int(p[2])))
inside = [(n, a, b) for n, a, b in LAYOUT if a <= 535 and b >= 216]


def vocab_at(blk):
    """Name of the vocabulary whose blocks hold blk (from catalog_layout)."""
    for n, a, b in LAYOUT:
        if a <= blk <= b:
            return n
    return None


V900, V100 = vocab_at(900), vocab_at(100)
check('C0 catalog_layout places a vocabulary at block 900 and at block 100',
      V900 is not None and V100 is not None, f'(900: {V900}, 100: {V100})', fatal=True)
check('M6b no vocabulary in blocks 216-535', not inside, f'(inside: {inside[:6]})')
ceiling = getattr(wc, 'HP_WRITE_CEILING', None)
check('M6c the range ends at or below the HP write ceiling',
      res is not None and ceiling is not None and res[-1] <= ceiling,
      f'(range {res}, ceiling {ceiling})')
# Reserved data ranges block 100's image (100 .. 100+m-1) is expected to
# name, from write-catalog; m is checked on the guest, these cover 100-289
# for any dictionary of 190+ blocks and are filtered by m at M2.
RANGES = [('settings', wc.SETTINGS_RESERVED), ('telemetry', wc.TELEMETRY_RESERVED),
          ('MIRROR-reserved', getattr(wc, 'MIRROR_RESERVED', range(0)))]
mtxt = open(MIRROR_FTH).read()


def fth_const(name):
    m = re.search(rf'^\s*([0-9A-Fa-f]+)\s+CONSTANT\s+{re.escape(name)}\b', mtxt, re.M)
    return int(m.group(1), 16) if m else None


got = [(fth_const('MR-SET-LO'), fth_const('MR-SET-HI')),
       (fth_const('MR-LOG-LO'), fth_const('MR-LOG-HI'))]
wantr = [(wc.SETTINGS_RESERVED.start, wc.SETTINGS_RESERVED.stop - 1),
         (wc.TELEMETRY_RESERVED.start, wc.TELEMETRY_RESERVED.stop - 1)]
check("M6e mirror.fth's reserved ranges equal write-catalog's settings and telemetry",
      got == wantr, f'(mirror.fth {got}, write-catalog {wantr})')
mm = re.search(r'^\s*([0-9A-Fa-f]+)\s+CONSTANT\s+MIRROR-BLK\b',
               open(MIRROR_FTH).read(), re.M)
check("M6d mirror.fth's MIRROR-BLK equals write-catalog's MIRROR_BLK",
      mm is not None and int(mm.group(1), 16) == getattr(wc, 'MIRROR_BLK', None),
      f'(mirror.fth {mm.group(1) if mm else None})')

# ---------------------------------------------------------------- ATA path
FLOPPY = os.path.join(D, 'ata-floppy.img')
IDE = os.path.join(D, 'ata-ide.img')
shutil.copyfile(COMBINED, FLOPPY)
shutil.copyfile(COMBINED, IDE)
ATA_ARGS = ['-drive', f'file={FLOPPY},format=raw,if=floppy',
            '-drive', f'file={IDE},format=raw,if=ide,index=1']
g = Guest(ATA_ARGS, 'mirror-ata')
try:
    load_mirror(g)
    mb = mirror_blk(g)
    g.send("' (BLK-WRITE-ATA) BLK-WRITER! ' (BLK-READ-ATA) BLK-READER!")
    m = nums(g.send('DECIMAL DICT-BLKS 1+ .'))[0]       # blocks one image takes
    print(f'image size: {m} blocks (header + dictionary)', flush=True)

    # M1: over the code store
    before = blocks(IDE, 900, m)
    r = g.send('DECIMAL 900 MIRROR', 300)
    check(f'M1a 900 MIRROR refused, naming {V900} (the vocabulary at block 900)',
          'MIRROR REFUSED' in r and V900 in r and 'saved' not in r,
          f'(reply tail {r.strip()[-120:]!r})')
    check('M1b disk unchanged at blocks 900+', blocks(IDE, 900, m) == before)
    check('M1c DEPTH 0', g.depth() == 0)

    # M3: one refused block inside the image
    g.send(f': FIXW DUP {REFUSED_BLK} = IF 2DROP 1 ELSE (BLK-WRITE-ATA) THEN ;')
    g.send("' FIXW BLK-WRITER!")
    m3 = nums(g.send('DECIMAL DICT-BLKS 1+ .'))[0]
    # MIR-BUF (MIRROR's 1 KB staging buffer) lives in the dictionary and
    # holds the header, tick count included: its image blocks differ
    # between any two MIRRORs.  Image block i holds 0x30000 + (i-1)*1024.
    mbuf = nums(g.send('DECIMAL MIR-BUF .'))[0]
    # MIRROR's own state cells change during a MIRROR (MR-BAD counts the
    # refused write), so they differ between two images too.  Their
    # addresses are asked, not assumed; absent words (today's MIRROR)
    # contribute nothing.
    STATE_VARS = ('MR-FIRST', 'MR-LAST', 'MR-HIT', 'MR-PW', 'MR-PF',
                  'MR-BAD', 'MR-BAD1', 'MR-IOR', 'MC-WS', 'MC-WL')
    mutable = set(range(mbuf, mbuf + BSIZE))
    for w in STATE_VARS:
        r = g.send(f'DECIMAL {w} DEPTH .')
        if f'{w} ?' in r or nums(r)[-1:] != [1]:
            continue
        a = nums(g.send('.'))[0]
        mutable |= set(range(a, a + 4))
    pre3 = blocks(IDE, 216, m3)
    r3 = g.send('DECIMAL 216 MIRROR', 300)
    s3 = blocks(IDE, 216, m3)
    check('M3a refused block reported: MIRROR FAILED: 1 of m, no "saved"',
          f'MIRROR FAILED: 1 of {m3} blocks not written' in r3 and 'saved' not in r3,
          f'(reply tail {r3.strip()[-160:]!r})')
    named = re.findall(r'BLOCK WRITE FAIL (\d+)', r3)
    print(f'M3 kernel FAIL lines: {named}', flush=True)
    check('M3b DEPTH 0', g.depth() == 0)

    # M4 (ATA): the reserved block, read back
    check('M4a MIRROR-BLK = 216', mb == 216, f'(got {mb})')
    g.send("' (BLK-WRITE-ATA) BLK-WRITER!")
    r4 = g.send('DECIMAL 216 MIRROR', 300)
    s4 = blocks(IDE, 216, m3)
    check('M4b 216 MIRROR saved (ATA)', 'MIRROR saved to block 216' in r4,
          f'(reply tail {r4.strip()[-120:]!r})')
    check('M4c header on disk at block 216 (ATA)', s4[:4] == MAGIC,
          f'(first bytes {s4[:8].hex()})')
    r = g.send('DECIMAL 216 MIRROR? .')
    check('M4d 216 MIRROR? true (ATA)', nums(r)[-1:] == [-1], f'(got {r.strip()!r})')
    ri = g.send('DECIMAL 216 MIRROR-INFO DECIMAL')
    disk_here = struct.unpack('<I', s4[0x10:0x14])[0]
    check("M4e MIRROR-INFO's HERE = the header's HERE on disk (ATA)",
          info_here(ri) == disk_here, f'(info {info_here(ri)}, disk {disk_here:#x})')

    # M3 continued: every dictionary block but the refused one is on disk
    k = REFUSED_BLK - 216
    stray = []        # differing bytes outside MIRROR's own mutable cells
    for i in range(1, m3):
        if i == k:
            continue
        a3, a4 = s3[i * BSIZE:(i + 1) * BSIZE], s4[i * BSIZE:(i + 1) * BSIZE]
        for j in range(BSIZE):
            addr = 0x30000 + (i - 1) * BSIZE + j
            if a3[j] != a4[j] and addr not in mutable:
                stray.append((216 + i, hex(addr)))
    check('M3c every other dictionary block written (equals the M4 image '
          "outside MIRROR's own state cells)", not stray,
          f'(stray differing bytes: {stray[:8]})')
    check('M3d the refused block is untouched on disk',
          s3[k * BSIZE:(k + 1) * BSIZE] == pre3[k * BSIZE:(k + 1) * BSIZE])

    # M5 part 1: a word, then an image
    g.send(': MIRTEST 4242 ;')
    r5 = g.send('DECIMAL 216 MIRROR', 300)
    check('M5a image with MIRTEST saved', 'MIRROR saved to block 216' in r5)
finally:
    g.close()

# M5 part 2: reboot on the same disks, restore
g = Guest(ATA_ARGS, 'mirror-ata2')
try:
    load_mirror(g)
    g.send("' (BLK-READ-ATA) BLK-READER!")
    r = g.send('DECIMAL 216 LOOKINGGLASS', 120)
    check('M5b LOOKINGGLASS restored', 'LOOKINGGLASS restored' in r,
          f'(reply tail {r.strip()[-120:]!r})')
    r = g.send('DECIMAL MIRTEST .')
    check('M5c MIRTEST answers 4242 after the reboot', nums(r)[-1:] == [4242],
          f'(got {r.strip()!r})')
finally:
    g.close()

# ---------------------------------------------------------------- HP path
HP_CASES = ('M2a', 'M2b', 'M2c', 'M4f', 'M4g', 'M4h', 'M4i', 'M4j')
if not os.path.exists(AHCI_FTH):
    for c in HP_CASES:
        skip(c, 'forth/dict/ahci.fth absent: AHCI is not in this build')
else:
    import g6_fixture as g6
    IMG = os.path.join(D, 'hp-combined.img')
    DISK = os.path.join(D, 'hp549.img')
    shutil.copyfile(COMBINED, IMG)
    if os.path.exists(DISK):
        os.remove(DISK)
    g6.build(DISK)
    subprocess.run(['sgdisk', '-a', '1', '-n', f'6:{P6[0]}:{P6[1]}', '-t',
                    '6:4E011D24-9E20-45E8-BC49-85EB14C68532', '-c', '6:FORTHOS', DISK],
                   check=True, capture_output=True)
    g = Guest(['-m', '64', '-kernel', '/usr/lib/syslinux/memdisk', '-initrd', IMG,
               '-append', 'raw', '-drive', f'file={DISK},format=raw,if=none,id=sata0',
               '-device', 'ich9-ahci,id=ahci0', '-device', 'ide-hd,drive=sata0,bus=ahci0.0'],
              'mirror-hp')
    try:
        for c in ('USING AHCI', 'AHCI-INIT', 'AHCI-RW'):
            r = g.send(c)
        check('C3 AHCI-RW: guard read the partition table',
              'part guard: 1 extent(s)' in r, f'({r.strip()!r})', fatal=True)
        load_mirror(g)
        mbh = mirror_blk(g)
        mh = nums(g.send('DECIMAL DICT-BLKS 1+ .'))[0]
        RES100 = [(n, rg.start, rg.stop - 1) for n, rg in RANGES
                  if len(rg) and rg.start <= 100 + mh - 1 and rg.stop - 1 >= 100]

        before = disk_digest(DISK)
        r = g.send('DECIMAL 100 MIRROR', 300)
        want = [V100, 'partition LBA 34-582'] + [f'{n} ({a}-{b})' for n, a, b in RES100]
        miss = [w for w in want if w not in r]
        check(f'M2a 100 MIRROR refused, naming every overlap: {", ".join(want)}',
              'MIRROR REFUSED' in r and not miss and 'saved' not in r, f'(missing {miss}; reply tail {r.strip()[-260:]!r})')
        check('M2b HP disk unchanged (LBA 0-65535 and the last 2048 sectors)',
              disk_digest(DISK) == before)
        check('M2c DEPTH 0', g.depth() == 0)

        check('M4f MIRROR-BLK = 216 (HP)', mbh == 216, f'(got {mbh})')
        r = g.send('DECIMAL 216 MIRROR', 300)
        hdr = lbas(DISK, LBA0 + 2 * 216, 2)
        check('M4g 216 MIRROR saved (HP)', 'MIRROR saved to block 216' in r,
              f'(reply tail {r.strip()[-120:]!r})')
        check('M4h header on the SATA disk at block 216', hdr[:4] == MAGIC,
              f'(first bytes {hdr[:8].hex()})')
        r = g.send('DECIMAL 216 MIRROR? .')
        check('M4i 216 MIRROR? true (HP, persistent reader)', nums(r)[-1:] == [-1],
              f'(got {r.strip()!r})')
        ri = g.send('DECIMAL 216 MIRROR-INFO DECIMAL')
        disk_here = struct.unpack('<I', hdr[0x10:0x14])[0]
        check("M4j MIRROR-INFO's HERE = the header's HERE on disk (HP)",
              info_here(ri) == disk_here, f'(info {info_here(ri)}, disk {disk_here:#x})')
    finally:
        g.close()

print(f'Passed: {checks - len(failures)}/{checks}'
      + (f'  SKIPPED: {len(skips)} ({" ".join(skips)})' if skips else ''), flush=True)
sys.exit(0 if not failures else 1)
