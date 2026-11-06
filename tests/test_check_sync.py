"""check-sync compares every private-owned copy (private
TASK_CHECK_SYNC_BUILD_COPIES, amendment 1).

check-sync compares the paid vocabularies and the private repo's
top-level tests/*.py with their private copies.  Every other file the
private repo tracks and this tree holds as an ignored copy was compared
by nothing, and the LEAK loop passed it because it is ignored: a stale
copy read OK.  The rule: every private-tracked file that is on disk
here, untracked here and ignored here equals its private copy, or
check-sync prints `DIVERGED: <path>` and fails, and it prints how many
it compared.

Host only.  The stale copies are made in a scratch private repo only:
a `git clone --shared` of PRIVATE_REPO in this test's own mkdtemp
directory (prefix check-sync-), with the working copy of every tracked
file copied over it, so an uncommitted private edit is what is
compared.  `make -s check-sync PRIVATE_REPO=<scratch>` runs in this
tree; neither real tree is written.  The directory is removed at the
end, pass or fail.

  C1  control: exit 0, last line `check-sync OK: all paid files in
      sync`, no DIVERGED, MISSING or LEAK line
  C2  control: `check-sync: N build copies compared` once, N counted
      here (private ls-files, on disk here, untracked here, ignored
      here, less the paid vocabularies and top-level tests/*.py)
  C3  stale forth/dict/ros-notepad.fth   -> DIVERGED, once
  C4  stale tools/log_decode.py          -> DIVERGED, once
  C5  stale forth/dict/ahci.fth          -> `DIVERGED: ahci.fth`, once
  C6  stale tests/test_log_harness.py    -> DIVERGED, once
  C7  control again, after every restore: as C1

C3-C6 pass on make's exit 2 plus make's `Error 1` line (the recipe's
exit 1).  TOTAL = 7 is pinned; exit 0 only when all 7 run and pass.
"""
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import run_mode

TOTAL = 7
MAKEFILE = os.path.join(ROOT, 'Makefile')
OK_LINE = 'check-sync OK: all paid files in sync'
COUNT_RE = re.compile(r'^check-sync: (\d+) build copies compared$')
STALE = b'\n# stale copy, test_check_sync\n'

for p in (MAKEFILE, os.path.abspath(__file__)):
    with open(p, 'rb') as f:
        print(f'input sha256 {hashlib.sha256(f.read()).hexdigest()}  {p}')

MODE = run_mode.resolve(ROOT)
if not MODE.private:
    MODE.skip('test-check-sync', TOTAL)
PRIV = os.path.abspath(MODE.repo)

passed = 0
ran = 0


def check(name, ok, detail=''):
    global passed, ran
    ran += 1
    if ok:
        passed += 1
        print(f'  PASS: {name}')
    else:
        print(f'  FAIL: {name}' + (f' -- {detail}' if detail else ''))


def git(*args, cwd=ROOT, data=None):
    return subprocess.run(['git', '-C', cwd, *args], input=data,
                          capture_output=True, check=True).stdout


def lines(out):
    return out.decode('utf-8', 'replace').splitlines()


# The count, from here: what the general rule should compare
with open(MAKEFILE) as f:
    paid = re.search(r'^PAID_VOCABS = (.*)$', f.read(), re.M).group(1).split()
skip = {f'forth/dict/{v}.fth' for v in paid}
priv_files = git('ls-files', '-z', cwd=PRIV).decode().split('\0')[:-1]
pub_tracked = set(git('ls-files', '-z').decode().split('\0')[:-1])
cand = [f for f in priv_files
        if os.path.exists(os.path.join(ROOT, f)) and f not in pub_tracked]
ignored = set(git('check-ignore', '-z', '--stdin',
                  data='\0'.join(cand).encode()).decode().split('\0')[:-1]) \
    if cand else set()
N = sum(1 for f in cand if f in ignored and f not in skip
        and not re.match(r'^tests/[^/]+\.py$', f))
print(f'counted here: {N} build copies (PAID_VOCABS {len(paid)})')

TMP = tempfile.mkdtemp(prefix='check-sync-')
SCR = os.path.join(TMP, 'priv')
print(f'scratch: {SCR}')
ENV = {k: v for k, v in os.environ.items()
       if k not in ('MAKEFLAGS', 'MFLAGS', 'MAKELEVEL', 'MAKEOVERRIDES')}


def overlay(f):
    src, dst = os.path.join(PRIV, f), os.path.join(SCR, f)
    if os.path.lexists(src):
        shutil.copy2(src, dst, follow_symlinks=False)
    elif os.path.lexists(dst):
        os.remove(dst)


def run():
    p = subprocess.run(['make', '-s', 'check-sync', f'PRIVATE_REPO={SCR}'],
                       cwd=ROOT, env=ENV, capture_output=True)
    return p.returncode, lines(p.stdout), lines(p.stderr)


def control(name):
    rc, out, err = run()
    last = [l for l in out if l.strip()][-1:] or ['']
    bad = [l for l in out if l.startswith(('DIVERGED', 'MISSING', 'LEAK'))]
    check(f'{name}: control reads {OK_LINE!r}',
          rc == 0 and last[0] == OK_LINE and not bad,
          f'rc={rc} last={last[0]!r} bad={bad[:3]} stderr={err[-2:]}')
    return out


def stale(name, f, want):
    with open(os.path.join(SCR, f), 'ab') as fh:
        fh.write(STALE)
    try:
        rc, out, err = run()
    finally:
        git('checkout', '--', f, cwd=SCR)
        overlay(f)
    div = [l for l in out if l.startswith('DIVERGED')]
    err1 = [l for l in err if re.match(r'^make: \*\*\* \[.*check-sync\] Error 1$', l)]
    check(f'{name}: stale {f} reads {want!r}, once',
          rc == 2 and len(err1) == 1 and div == [want],
          f'rc={rc} DIVERGED={div} Error1={len(err1)} last={out[-1:]}')


try:
    subprocess.run(['git', 'clone', '-q', '--shared', PRIV, SCR], check=True)
    for f in priv_files:
        overlay(f)

    out = control('C1')
    cl = [m.group(1) for m in map(COUNT_RE.match, out) if m]
    check(f'C2: `check-sync: {N} build copies compared`, once',
          cl == [str(N)], f'count lines read {cl}')
    stale('C3', 'forth/dict/ros-notepad.fth', 'DIVERGED: forth/dict/ros-notepad.fth')
    stale('C4', 'tools/log_decode.py', 'DIVERGED: tools/log_decode.py')
    stale('C5', 'forth/dict/ahci.fth', 'DIVERGED: ahci.fth')
    stale('C6', 'tests/test_log_harness.py', 'DIVERGED: tests/test_log_harness.py')
    control('C7')
finally:
    shutil.rmtree(TMP, ignore_errors=True)

print(f'\n{MODE.line(passed, TOTAL)}'
      + ('' if ran == TOTAL else f' ({ran} checks ran, {TOTAL} pinned)'))
sys.exit(0 if passed == TOTAL and ran == TOTAL else 1)
