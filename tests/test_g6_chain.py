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

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4590
MON = PORT + 1
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
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


gencfg = load_mod('gencfg', 'tools/pxe/gen-grub-cfg.py')
g6fix = load_mod('g6fix', 'tests/g6_fixture.py')

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


def read_vga_text():
    """Address-anchored parse of xp /4000bx 0xb8000 (full 25 rows).
    HMP echoes the command (contains '0xb8000'), so only lines
    shaped '<hex-addr>: 0x.. 0x..' contribute, RHS only."""
    try:
        raw = mon_cmd('xp /4000bx 0xb8000', wait=2)
    except Exception as e:
        return f'<monitor unreachable: {e}>'
    cells = []
    for line in raw.splitlines():
        addr, sep, rest = line.partition(':')
        if not sep or not re.fullmatch(
                r'0x0*[0-9a-f]+|[0-9a-f]+', addr.strip()):
            continue
        cells += re.findall(r'0x([0-9a-f]{2})', rest)
    return bytes(int(c, 16) for c in cells[::2]).decode(
        'ascii', errors='replace')


def sendkey(key):
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
    subprocess.run(['pkill', '-9', '-f', f'[q]emu.*{PORT}'],
                   capture_output=True)
    time.sleep(1)


# A fatal() mid-run must not strand a daemonized QEMU on the
# ports -- that poisons the NEXT run as a mystery failure.
atexit.register(qemu_kill)


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


PROJECT_DIR = ROOT  # get_vocab_blocks below is a verbatim copy
# from tests/test_ahci_write.py, which names the repo root
# PROJECT_DIR; alias so the paste stays byte-identical.


def get_vocab_blocks(vocab_name):
    try:
        result = subprocess.run(
            [sys.executable, '-c', f"""
import sys, os
sys.path.insert(0, os.path.join('{PROJECT_DIR}', 'tools'))
from importlib.machinery import SourceFileLoader
wc = SourceFileLoader('wc', os.path.join(
    '{PROJECT_DIR}', 'tools', 'write-catalog.py'
)).load_module()
vocabs = wc.scan_vocabs(os.path.join(
    '{PROJECT_DIR}', 'forth', 'dict'))
_nc = (len(vocabs) + wc.CATALOG_DATA_LINES - 1) // wc.CATALOG_DATA_LINES
nb = 1 + _nc
for v in vocabs:
    nb = wc.place_vocab(nb, v['blocks_needed'])
    if v['name'] == '{vocab_name}':
        print(f"{{nb}} {{nb + v['blocks_needed'] - 1}}")
        break
    nb += v['blocks_needed']
"""],
            capture_output=True, text=True, timeout=10
        )
        if result.stdout.strip():
            parts = result.stdout.strip().split()
            return int(parts[0]), int(parts[1])
    except Exception:
        pass
    return None, None


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
manifest = subprocess.run(
    ['bash', 'tools/pxe/tree-hash.sh', TREE],
    capture_output=True, text=True).stdout.strip()
fatal('manifest hash computed (push-grub provenance authority)',
      re.fullmatch(r'[0-9a-f]{32}', manifest) is not None,
      manifest)
print(f'  tree manifest: {manifest}')

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
      menu[:200])
# No sendkey: timeout falls through to entry 0 (frozen order).
# memdisk hauls ~2.2 MB then boots; allow generously.
time.sleep(25)
SER = serial_connect()
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
#   3. The THRU must run BEFORE AHCI-INIT. OBSERVED: with the
#      order reversed, the THRU spews meta-compiler words and
#      reboots. Mechanism UNCONFIRMED -- BLK-READER! is only
#      referenced inside AHCI-RW (never called by AHCI-INIT),
#      so the earlier "init re-vectors BLOCK" explanation does
#      not hold; keep the ordering, root cause is an open item.
a, b = get_vocab_blocks('INSTALL')
fatal('INSTALL catalog range found', a is not None)
send(f'{a} {b} THRU', 25)
check('alive after INSTALL THRU', val('1 2 +')[0] == 3)
send('USING AHCI', 2)        # embedded vocab, no THRU needed
send('AHCI-INIT', 5)
check('alive after AHCI-INIT', val('1 2 +')[0] == 3)
send('ALSO SURVEYOR', 1)     # BEFORE USING INSTALL (DOVOC trap)
send('USING INSTALL', 2)
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

# ---- Populate VBR-TPL with the REAL template ----
# BLOCKING gap closed here: ADD-BOOT-ENTRY's step 3 builds the
# VBR from VBR-TPL, and NOTHING populates it at runtime -- the
# as-built record's open item ("VBR-TPL runtime delivery;
# today only the test fixture populates it"). Without this
# push the live install would fail at host assert (d) -- far
# from the actual cause -- or refuse at BUILD-VBR's no-template
# gate. Mechanism transcribed from Test 51's fixture pattern
# (test_install.py ~:1488: CREATE buf ALLOT, C! pokes,
# `buf VBR-TPL !`), just with build/vbr.bin's real 512 bytes.
# COROLLARY (lands in Task 12): the iron runbook's install
# step needs this IDENTICAL push over the net console, or iron
# G6 dies at the same place with a photograph of nothing.
VBR_TPL_BYTES = open('build/vbr.bin', 'rb').read()
fatal('vbr.bin is one sector', len(VBR_TPL_BYTES) == 512,
      str(len(VBR_TPL_BYTES)))
send('CREATE VBR-LIVE 512 ALLOT', 1.0)
# 4 pokes per line (~90 chars) stays well under the serial line
# limit; values are decimal -- BASE is DECIMAL here (the
# discriminator probe above restored it explicitly).
for i in range(0, 512, 4):
    line = '  '.join(
        f'{VBR_TPL_BYTES[i + j]} VBR-LIVE {i + j} + C!'
        for j in range(4))
    send(line, 0.2)
# Readback: byte-sum is the cheap whole-buffer oracle (max
# 512*255 = 130560, no cell overflow), then the two structural
# facts BUILD-VBR itself gates on (55AA at 510/511).
# DO/LOOP is compile-only in this kernel (every DO in the whole
# suite sits in a colon def -- none interpreted), so the sum
# loop must be compiled first, not typed bare.
send(': TPL-SUM 0 512 0 DO VBR-LIVE I + C@ + LOOP ;', 1.0)
expect('template byte-sum matches host', 'TPL-SUM',
       sum(VBR_TPL_BYTES), wait=8)
expect('template 55AA low', 'VBR-LIVE 510 + C@', 0x55)
expect('template 55AA high', 'VBR-LIVE 511 + C@', 0xAA)
send('VBR-LIVE VBR-TPL !', 0.5)
expect('VBR-TPL armed', 'VBR-TPL @ VBR-LIVE =', -1)

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
SER.close()
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
    check('(d) vbr.bin sentinel unique', len(hits) == 1, str(hits))
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
sendkey('down')          # blind: SeaBIOS buffers; GRUB consumes on menu init
sendkey('ret')           # blind: fires entry 1 before the 5 s timeout
# poll_grub_menu can't be used here -- by the time VGA shows the
# menu text the blind ret has already booted, so the GRUB menu
# assertion is replaced by the chainload-liveness probe below.
# Chainload path: iPXE->TFTP->GRUB (consumes blind keys)->VBR->kernel.
time.sleep(30)
SER = serial_connect()
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
legA_ok = v == 5
# Discriminator: chainload boot has NO memdisk hook, so the
# MEMDISK_BASE cell reads 0. POSITIVE form (stage 2's lesson:
# regex on raw output is fail-open); val() wraps as
# 'DECIMAL <expr> .' so the literal parses in hex and 0 prints
# in decimal; '?' -> None -> FAIL.
expect('leg A: discriminator 0 (chainload, no memdisk)',
       'HEX 28098 @ DECIMAL', 0)
SER.close()
qemu_kill()

print('\nStage 5: leg B -- timeout falls through to memdisk')
qemu_net_boot(DISK)
menu = poll_grub_menu()
fatal('leg B: GRUB menu up over TFTP',
      'ForthOS - memdisk' in menu, menu[:200])
# NO sendkey: the 5 s timeout must select entry 0 on its own --
# this is the daily-driver guarantee (frozen entry order).
time.sleep(25)
SER = serial_connect()
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
SER.close()
qemu_kill()

print(f'\nPassed: {PASS}/{PASS + FAIL}')
sys.exit(1 if FAIL else 0)
