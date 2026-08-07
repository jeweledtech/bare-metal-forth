#!/usr/bin/env python3
"""Offline gates for the GRUB-PXE cfg pipeline.

Three disciplines under test (spec D2 / Section 2):
1. Converter pin: cells->text is verified against the frozen
   lowercase forms computed at mint time by the INDEPENDENT
   authority (uuid.UUID(bytes_le=...)), not by code under test.
2. Scan fatality: the install.fth pattern-scan is fatal on zero
   hits AND on multiple hits (single-source-of-truth, the
   VBR-LBA-OFF discipline).
3. Drift gate: committed tools/pxe/grub.cfg == generated, entry
   order frozen (0=memdisk, 1=chainload), timeout=5, default=0,
   and every command on ONE line (no backslash continuations --
   GRUB "mostly tolerates" them; not a property a G6 leg leans on).
"""
import importlib.util
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEN = os.path.join(ROOT, 'tools', 'pxe', 'gen-grub-cfg.py')
FTH = os.path.join(ROOT, 'forth', 'dict', 'install.fth')
COMMITTED = os.path.join(ROOT, 'tools', 'pxe', 'grub.cfg')

PASS = FAIL = 0


def check(name, ok, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {name}')
    else:
        FAIL += 1
        print(f'  FAIL: {name}' + (f' -- {detail}' if detail else ''))


spec = importlib.util.spec_from_file_location('gencfg', GEN)
gencfg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gencfg)

print('Test 1: converter pin (independent-authority text forms)')
TG = [0x4E011D24, 0x45E89E20, 0xEB8549BC, 0x3285C614]
UG = [0x32BA60FB, 0x4D4C4548, 0x80FB39A4, 0x312B57CE]
check('type GUID text',
      gencfg.cells_to_uuid(TG) ==
      '4e011d24-9e20-45e8-bc49-85eb14c68532')
check('uniq GUID text',
      gencfg.cells_to_uuid(UG) ==
      '32ba60fb-4548-4d4c-a439-fb80ce572b31')

print('Test 2: install.fth scan')
cells = gencfg.scan_install_fth(FTH)
check('scan finds the four FOS-UG cells', cells == UG,
      f'got {[hex(c) for c in cells]}')

print('Test 3: scan fatality (zero and multiple hits)')


def scan_dies(body):
    with tempfile.NamedTemporaryFile('w', suffix='.fth',
                                     delete=False) as f:
        f.write(body)
        path = f.name
    try:
        gencfg.scan_install_fth(path)
        return False
    except SystemExit:
        return True
    finally:
        os.unlink(path)


check('zero hits fatal', scan_dies('\\ nothing here\n'))
with open(FTH) as f:
    dup = f.read() + '\n32BA60FB CONSTANT FOS-UG0\n'
check('duplicate hit fatal', scan_dies(dup))

print('Test 4: drift gate (committed == generated)')
gen = subprocess.run([sys.executable, GEN], capture_output=True,
                     text=True, cwd=ROOT)
check('generator exits 0', gen.returncode == 0, gen.stderr[:200])
committed = open(COMMITTED).read() if os.path.exists(COMMITTED) \
    else '<missing>'
check('committed grub.cfg matches generator byte-for-byte',
      committed == gen.stdout,
      'regenerate: python3 tools/pxe/gen-grub-cfg.py '
      '-o tools/pxe/grub.cfg')

print('Test 5: frozen shape pins')
lines = gen.stdout.splitlines()
ents = [i for i, l in enumerate(lines)
        if l.startswith('menuentry')]
check('exactly two menuentries', len(ents) == 2)
check('entry 0 is memdisk',
      len(ents) == 2 and 'memdisk' in lines[ents[0]])
check('entry 1 is chainload',
      len(ents) == 2 and 'installed' in lines[ents[1]])
check('timeout=5', 'set timeout=5' in lines)
check('default=0', 'set default=0' in lines)
check('search is one line, right guid',
      any(l.strip().startswith('search ') and
          '32ba60fb-4548-4d4c-a439-fb80ce572b31' in l and
          '--set root' in l for l in lines))
check('no line continuations anywhere',
      not any(l.rstrip().endswith('\\') for l in lines))
for mod in ('part_gpt', 'search_part_uuid', 'chain'):
    check(f'insmod {mod} explicit',
          any(l.strip() == f'insmod {mod}' for l in lines))
check('no --hint flags', '--hint' not in gen.stdout)

print('Test 6: --override-guid (leg C producer, never a hand edit)')
ov = subprocess.run(
    [sys.executable, GEN, '--override-guid',
     'deadbeef-dead-4eef-8ead-beefdeadbeef'],
    capture_output=True, text=True, cwd=ROOT)
check('override exits 0', ov.returncode == 0, ov.stderr[:200])
check('override guid present',
      'deadbeef-dead-4eef-8ead-beefdeadbeef' in ov.stdout)
check('canonical guid absent under override',
      '32ba60fb' not in ov.stdout)
check('override changes ONLY the search line',
      len([1 for a, b in zip(gen.stdout.splitlines(),
                             ov.stdout.splitlines()) if a != b])
      == 1 and
      len(gen.stdout.splitlines()) == len(ov.stdout.splitlines()))

print(f'\nPassed: {PASS}/{PASS + FAIL}')
sys.exit(1 if FAIL else 0)
