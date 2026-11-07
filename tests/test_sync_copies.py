#!/usr/bin/env python3
"""tools/sync_copies.py: copy each private-tracked file to the same path
wherever this repo's .gitignore ignores it, never touching a path this repo
tracks (private TASK_SYNC_COPIES). Host only: every check runs on a scratch
public/private git repo pair in a mkdtemp; no real tree is read or written.
13 checks, S1-S13.

  python3 tests/test_sync_copies.py      (cwd: tree root)
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.getcwd()
SCRIPT = os.path.join(ROOT, 'tools', 'sync_copies.py')
TOTAL = 13
NAMES = [f'S{i}' for i in range(1, TOTAL + 1)]
RESULT = {}


def check(label, ok, detail=''):
    key = label.split()[0]
    assert key in NAMES and key not in RESULT
    RESULT[key] = bool(ok)
    print(f'  {"PASS" if ok else "FAIL"}: {label}' + (f' -- {detail}' if detail and not ok else ''),
          flush=True)


def git(d, *a):
    return subprocess.run(['git', '-C', d, '-c', 'user.name=t', '-c', 'user.email=t@t', *a],
                          capture_output=True, text=True, check=True).stdout


def write(d, rel, data):
    p = os.path.join(d, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w').write(data)


def read(d, rel):
    p = os.path.join(d, rel)
    return open(p).read() if os.path.isfile(p) else None


def pair(top, priv_files, pub_tracked, pub_untracked, gitignore, priv_untracked=()):
    """A private repo tracking priv_files, a public repo tracking .gitignore
    and pub_tracked, with pub_untracked on disk (untracked)."""
    priv, pub = os.path.join(top, 'priv'), os.path.join(top, 'pub')
    for d in (priv, pub):
        os.makedirs(d)
        git(d, 'init', '-q')
    for rel, data in priv_files.items():
        write(priv, rel, data)
    git(priv, 'add', '-A')
    git(priv, 'commit', '-q', '-m', 'p')
    for rel, data in dict(priv_untracked).items():
        write(priv, rel, data)
    write(pub, '.gitignore', gitignore)
    for rel, data in pub_tracked.items():
        write(pub, rel, data)
    git(pub, 'add', '-A')
    git(pub, 'commit', '-q', '-m', 'q')
    for rel, data in pub_untracked.items():
        write(pub, rel, data)
    return priv, pub


def run(pub, *args):
    r = subprocess.run(['python3', SCRIPT, *args], cwd=pub, capture_output=True, text=True)
    return r.returncode, r.stdout.splitlines()


def summary(lines):
    s = [x for x in lines if x.startswith('sync-copies')]
    return s


def line(n, c, e, f, k, dry=False):
    tag = 'sync-copies (dry run)' if dry else 'sync-copies'
    verb = 'would be copied' if dry else 'copied'
    return (f'{tag}: {n} private-tracked files at paths ignored here; {c} {verb}, '
            f'{e} already equal, {f} failed; {k} skipped (tracked here)')


print(f'input script: {SCRIPT}' + ('' if os.path.exists(SCRIPT) else ' (absent)'), flush=True)
if not os.path.exists(SCRIPT):
    for n in NAMES:
        check(f'{n} not run', False, 'tools/sync_copies.py absent')
    print(f'\nPassed: 0/{TOTAL}', flush=True)
    sys.exit(1)

GITIGNORE = 'ign/\nshared.txt\n'
PRIV = {
    'ign/a.txt': 'A private\n',            # S1: absent here
    'ign/b.txt': 'B private\n',            # S2: here with other bytes
    'ign/e.txt': 'E same\n',               # already equal
    'ign/deep/new/d.txt': 'D private\n',   # S6: missing parents
    'shared.txt': 'shared private\n',      # S3/S12: tracked here (and matches an ignore line)
    'plain/c.txt': 'C private\n',          # S4: neither tracked nor ignored here
}
PUB_TRACKED = {'shared.txt': 'shared public\n'}
PUB_UNTRACKED = {'ign/b.txt': 'B stale\n', 'ign/e.txt': 'E same\n'}
PRIV_UNTRACKED = {'ign/u.txt': 'U untracked\n'}   # S5

top = tempfile.mkdtemp(prefix='sync-copies-')
try:
    # ---- the main pair -------------------------------------------------
    priv, pub = pair(os.path.join(top, 'm'), PRIV, PUB_TRACKED, PUB_UNTRACKED, GITIGNORE, PRIV_UNTRACKED)
    e_mtime = os.stat(os.path.join(pub, 'ign/e.txt')).st_mtime_ns
    time.sleep(0.05)
    rc, out = run(pub, '--private', priv)
    print('    run 1: ' + ' | '.join(out), flush=True)
    check('S1 an ignored path, absent here, is copied byte-equal',
          read(pub, 'ign/a.txt') == PRIV['ign/a.txt'], f'{read(pub, "ign/a.txt")!r}')
    check('S2 an ignored path with other bytes here is overwritten with the private bytes',
          read(pub, 'ign/b.txt') == PRIV['ign/b.txt'], f'{read(pub, "ign/b.txt")!r}')
    check('S3 a path this repo tracks is not touched',
          read(pub, 'shared.txt') == PUB_TRACKED['shared.txt'], f'{read(pub, "shared.txt")!r}')
    check('S4 a path neither tracked nor ignored here is not copied',
          read(pub, 'plain/c.txt') is None, f'{read(pub, "plain/c.txt")!r}')
    check('S5 a private untracked file at an ignored path is not copied',
          read(pub, 'ign/u.txt') is None, f'{read(pub, "ign/u.txt")!r}')
    check('S6 a missing parent directory is created',
          read(pub, 'ign/deep/new/d.txt') == PRIV['ign/deep/new/d.txt'], f'{read(pub, "ign/deep/new/d.txt")!r}')
    want = line(4, 3, 1, 0, 1)
    s = summary(out)
    check('S7 the summary line, once: N 4, C 3, E 1, F 0, K 1; exit 0',
          s == [want] and rc == 0, f'rc {rc}, summary {s!r}, wanted {want!r}')
    check('S12 the tracked-here path is listed and counted',
          out.count('skipped (tracked here): shared.txt') == 1 and s == [want], f'{out!r}')
    mt = {r: os.stat(os.path.join(pub, r)).st_mtime_ns for r in ('ign/a.txt', 'ign/b.txt', 'ign/e.txt', 'ign/deep/new/d.txt')}
    time.sleep(0.05)
    rc2, out2 = run(pub, '--private', priv)
    mt2 = {r: os.stat(os.path.join(pub, r)).st_mtime_ns for r in mt}
    check('S8 a second run copies 0, all 4 already equal, none rewritten (mtimes kept)',
          summary(out2) == [line(4, 0, 4, 0, 1)] and rc2 == 0 and mt == mt2
          and mt['ign/e.txt'] == e_mtime,
          f'rc {rc2}, {summary(out2)!r}, mtimes changed {[r for r in mt if mt[r] != mt2[r]]}, '
          f'e.txt first run rewritten {mt["ign/e.txt"] != e_mtime}')

    # ---- S9: --dest into a plain directory --------------------------------
    priv9, pub9 = pair(os.path.join(top, 'd'), PRIV, PUB_TRACKED, PUB_UNTRACKED, GITIGNORE)
    before = {r: read(pub9, r) for r in ('ign/a.txt', 'ign/b.txt', 'ign/e.txt', 'shared.txt')}
    dest = os.path.join(top, 'export')
    os.makedirs(dest)
    rc9, out9 = run(pub9, '--private', priv9, '--dest', dest)
    after = {r: read(pub9, r) for r in before}
    ok = (rc9 == 0 and summary(out9) == [line(4, 4, 0, 0, 1)]
          and all(read(dest, r) == PRIV[r] for r in ('ign/a.txt', 'ign/b.txt', 'ign/e.txt', 'ign/deep/new/d.txt'))
          and read(dest, 'shared.txt') is None and read(dest, 'plain/c.txt') is None and before == after)
    check('S9 --dest writes into a plain directory, and the public repo is untouched', ok,
          f'rc {rc9}, {summary(out9)!r}, public changed {before != after}')

    # ---- S10: --private not a git work tree --------------------------------
    nogit = os.path.join(top, 'nogit')
    os.makedirs(nogit)
    rc10, out10 = run(pub9, '--private', nogit)
    check('S10 a --private that is not a git work tree exits 1', rc10 == 1, f'rc {rc10}, {out10!r}')

    # ---- S11: --dry-run ----------------------------------------------------
    priv11, pub11 = pair(os.path.join(top, 'n'), PRIV, PUB_TRACKED, PUB_UNTRACKED, GITIGNORE)
    rc11, out11 = run(pub11, '--private', priv11, '--dry-run')
    would = sorted(x[len('would copy: '):] for x in out11 if x.startswith('would copy: '))
    ok = (rc11 == 0 and would == ['ign/a.txt', 'ign/b.txt', 'ign/deep/new/d.txt']
          and summary(out11) == [line(4, 3, 1, 0, 1, dry=True)]
          and read(pub11, 'ign/a.txt') is None and read(pub11, 'ign/b.txt') == 'B stale\n')
    check('S11 --dry-run lists what would be copied, copies nothing, and says dry run', ok,
          f'rc {rc11}, would {would}, {summary(out11)!r}')

    # ---- S13: a failing copy -----------------------------------------------
    priv13, pub13 = pair(os.path.join(top, 'f'), {'ign/blk/f.txt': 'F\n'}, {}, {'ign/blk': 'a file\n'}, 'ign/\n')
    rc13, out13 = run(pub13, '--private', priv13)
    check('S13 a failed copy prints FAILED, counts F 1, and exits 1',
          rc13 == 1 and any(x.startswith('FAILED: ign/blk/f.txt') for x in out13)
          and summary(out13) == [line(1, 0, 0, 1, 0)], f'rc {rc13}, {out13!r}')
finally:
    shutil.rmtree(top, ignore_errors=True)

for n in NAMES:
    if n not in RESULT:
        print(f'  FAIL: {n} -- not run', flush=True)
passed = sum(1 for n in NAMES if RESULT.get(n))
print(f'\nPassed: {passed}/{TOTAL}', flush=True)
sys.exit(0 if passed == TOTAL else 1)
