#!/usr/bin/env python3
"""The PXE menu names the image it serves (private TASK_PXE_PUSH_LABEL).

Both push scripts, pointed at scratch roots (TFTP_ROOT under this test's
own mktemp directory, SUDO empty), never at /srv/tftp:
  push.sh (make pxe-push) on four seeded roots:
    A  the committed cfg, entry 0 "ForthOS - memdisk (dev)"
    B  entry 0 as the live 2026-10-30 relabel
    C  no grub/grub.cfg: refused, nothing copied
    D  a cfg with no memdisk entry: refused, nothing copied
    E  an image whose mtime is 2020-01-01: labelled with the push date
  push-grub.sh (make pxe-push-grub) on a copy of the staged build/tftp.
A labelled push writes forth.img.sha256 (sha256sum form) next to the
image and rewrites only entry 0's title to
  ForthOS - memdisk <sha256[:8]> pushed <the push date, UTC, YYYY-MM-DD>
(the push date, not the image's mtime, which a copy resets; P15) keeping the "ForthOS - memdisk" prefix test_g6_chain finds the menu by;
the staged tree stays unlabelled (test_g6_chain.py:649).
"""
import datetime
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PXE = os.path.join(ROOT, 'tools', 'pxe')
IMG = os.path.join(ROOT, 'build', 'combined.img')
TREE = os.path.join(ROOT, 'build', 'tftp')
COMMITTED = os.path.join(PXE, 'grub.cfg')
ENTRY0 = re.compile(r'^menuentry "ForthOS( -)? memdisk')
RELABEL = 'menuentry "ForthOS memdisk 2026-10-01 6fac2873 (old build)" {'
OLD = b'old'
TOTAL = 19
OLD_MTIME = 1577836800  # 2020-01-01 00:00 UTC

PASS = FAIL = 0


def check(name, ok, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {name}')
    else:
        FAIL += 1
        print(f'  FAIL: {name}' + (f' -- {detail}' if detail else ''))


def sha256(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


# ---- the bytes under test, hashed before they run ----
for p in ('push.sh', 'push-grub.sh', 'label.sh'):
    f = os.path.join(PXE, p)
    print(f'  input: tools/pxe/{p} '
          f'{sha256(f) if os.path.exists(f) else "(absent)"}')
print(f'  input: tests/test_pxe_label.py {sha256(os.path.abspath(__file__))}')
SHA = sha256(IMG)


def today():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')


def title(date):
    return f'menuentry "ForthOS - memdisk {SHA[:8]} pushed {date}" {{'


DATES = {today()}  # the push date, read before and after the pushes
print(f'  image: build/combined.img {SHA}')
print(f'  expected entry 0: {title(today())}')

SCRATCH = tempfile.mkdtemp(prefix='pxe-label-')


def guard(root):
    """Never /srv/tftp, never sudo: FAIL before any push otherwise."""
    real = os.path.realpath(root)
    if not real.startswith(os.path.realpath(SCRATCH) + os.sep) or \
            real.startswith('/srv/'):
        print(f'FAIL: root {root} is not under {SCRATCH}; nothing run')
        sys.exit(1)


def run(script, root, *args):
    guard(root)
    env = dict(os.environ, TFTP_ROOT=root, SUDO='')
    return subprocess.run(['bash', os.path.join(PXE, script), *args],
                          cwd=ROOT, env=env, capture_output=True, text=True)


def seed(name, cfg):
    root = os.path.join(SCRATCH, name)
    os.makedirs(root)
    open(os.path.join(root, 'forth.img'), 'wb').write(OLD)
    if cfg is not None:
        os.makedirs(os.path.join(root, 'grub'))
        open(os.path.join(root, 'grub', 'grub.cfg'), 'w').write(cfg)
    return root


def cfg_lines(root):
    return open(os.path.join(root, 'grub', 'grub.cfg')).read().split('\n')


def entry0(lines):
    return next((i for i, l in enumerate(lines) if ENTRY0.match(l)), None)


def sha_file_ok(root):
    f = os.path.join(root, 'forth.img.sha256')
    return os.path.exists(f) and open(f).read() == f'{SHA}  forth.img\n'


def labelled_one_line(root, seeded):
    """Entry 0 is the title with a push date, and the cfg differs from
    the seed there only."""
    now = cfg_lines(root)
    i = entry0(seeded)
    diff = [k for k in range(max(len(now), len(seeded)))
            if k >= len(now) or k >= len(seeded) or now[k] != seeded[k]]
    ok = i is not None and i < len(now) and \
        now[i] in {title(d) for d in DATES | {today()}}
    return ok, diff == [i]


committed = open(COMMITTED).read()
try:
    print('\npush.sh, seed A: the committed cfg')
    a = seed('A', committed)
    r = run('push.sh', a, IMG)
    check('P1 exit 0', r.returncode == 0, r.stderr[-200:])
    check('P2 forth.img is the image', sha256(os.path.join(a, 'forth.img')) == SHA)
    check('P3 forth.img.sha256 is "<sha256>  forth.img"', sha_file_ok(a))
    DATES.add(today())
    ok, one = labelled_one_line(a, committed.split('\n'))
    check(f'P4 entry 0 reads {title("<push date>")}', ok,
          cfg_lines(a)[entry0(committed.split(chr(10)))])
    check('P5 the cfg differs from the seed in that line only', one)
    check('P6 the output prints the sha256, the push date and the title',
          SHA in r.stdout and any(d in r.stdout and title(d)[11:-3] in r.stdout
                                  for d in DATES),
          r.stdout[-300:])

    print('\npush.sh, seed B: entry 0 as the live relabel')
    b_cfg = committed.replace('menuentry "ForthOS - memdisk (dev)" {', RELABEL)
    b = seed('B', b_cfg)
    r = run('push.sh', b, IMG)
    check('P7 exit 0', r.returncode == 0, r.stderr[-200:])
    DATES.add(today())
    ok, one = labelled_one_line(b, b_cfg.split('\n'))
    check('P8 entry 0 reads the title with the push date', ok)
    check('P9 the cfg differs from the seed in that line only', one)

    print('\npush.sh, seed C: no grub/grub.cfg')
    c = seed('C', None)
    r = run('push.sh', c, IMG)
    check('P10 refused (exit not 0)', r.returncode != 0)
    check('P11 forth.img still the old 3 bytes',
          open(os.path.join(c, 'forth.img'), 'rb').read() == OLD)
    check('P12 no forth.img.sha256', not os.path.exists(os.path.join(c, 'forth.img.sha256')))

    print('\npush.sh, seed D: a cfg with no memdisk entry')
    d = seed('D', committed.replace('menuentry "ForthOS - memdisk (dev)" {',
                                    'menuentry "Other" {'))
    r = run('push.sh', d, IMG)
    check('P13 refused (exit not 0)', r.returncode != 0)
    check('P14 forth.img still the old 3 bytes',
          open(os.path.join(d, 'forth.img'), 'rb').read() == OLD)

    print('\npush.sh, seed E: an image whose mtime is 2020-01-01')
    e = seed('E', committed)
    old_img = os.path.join(SCRATCH, 'old-mtime.img')
    shutil.copyfile(IMG, old_img)
    os.utime(old_img, (OLD_MTIME, OLD_MTIME))
    r = run('push.sh', e, old_img)
    DATES.add(today())
    got = cfg_lines(e)[entry0(committed.split('\n'))]
    check('P15 labelled with the push date, not the mtime (2020-01-01)',
          got in {title(d) for d in DATES} and '2020-01-01' not in got, got)

    print('\npush-grub.sh, a copy of the staged build/tftp')
    g = os.path.join(SCRATCH, 'G')
    shutil.copytree(TREE, g)
    staged = open(os.path.join(TREE, 'grub', 'grub.cfg')).read().split('\n')
    r = run('push-grub.sh', g)
    check('G1 exit 0', r.returncode == 0, (r.stdout + r.stderr)[-300:])
    check('G2 forth.img.sha256 is "<sha256>  forth.img"', sha_file_ok(g))
    DATES.add(today())
    ok, one = labelled_one_line(g, staged)
    check('G3 entry 0 reads the title with the push date', ok and one)
    check('G4 the staged build/tftp/grub/grub.cfg still the committed cfg',
          open(os.path.join(TREE, 'grub', 'grub.cfg')).read() == committed)
finally:
    shutil.rmtree(SCRATCH)

print(f'\nPassed: {PASS}/{TOTAL}')
sys.exit(0 if PASS == TOTAL and not FAIL else 1)
