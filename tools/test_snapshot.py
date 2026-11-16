#!/usr/bin/env python3
"""test_snapshot.py - the full run from throwaway clones (make test-snapshot).

Clones both repos at fixed commits into CLONES snapshot folders under
$TMPDIR/forthos-snapshot, builds in each, and runs every target on the
Makefile's test: line, split across the clones by the last timing
table; each clone runs its share one target at a time. The real trees
are only read, apart from one result file, build/test-snapshot.txt.

Gate: every clone must build the same image hashes. A difference from
the real tree's build/ images is recorded, not a stop. Any target whose
own log has a line starting with SKIP or SKIPPED (optionally indented
or in brackets) fails the run; test-public-clone's checks start with
PASS:/FAIL:, so the skips it checks for do not count.

Usage: test_snapshot.py --private-repo PATH [--clones N]
                        [--public REF] [--private REF] [--targets 'T ...']
"""
import argparse
import hashlib
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time

PUB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.join(tempfile.gettempdir(), 'forthos-snapshot')
MARK = '.forthos-snapshot'
IMAGES = ['combined.img', 'bmforth.img', 'kernel.bin', 'blocks.img', 'test.img']
# Inputs in no repo (ignored in public, absent from private): copied from
# the real tree, each hash recorded. A missing one fails the setup.
OUTSIDE_GIT = ['tools/translator/tests/data/' + n + '.sys'
               for n in ('i8042prt', 'beep', 'floppy', 'pci', 'serial')]
SKIP = re.compile(r'^\s*\[?SKIP(PED)?\b')
running, stop = {}, threading.Event()


def sh(args, cwd, **kw):
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True,
                          text=True, **kw).stdout


def sha(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest() if os.path.exists(path) else '-'


def port_base(path):
    b = int(sh(['cksum'], '/', input=path).split()[0])
    return 2200 + (b % 34) * 200


def lane_build(i, pub_c, priv_c, priv_real):
    lane = os.path.join(ROOT, f'lane{i}')
    pub, priv = os.path.join(lane, 'forthos'), os.path.join(lane, 'forthos-vocabularies')
    for src, dst, c in ((PUB, pub, pub_c), (priv_real, priv, priv_c)):
        sh(['git', 'clone', '--quiet', '--no-hardlinks', '--no-checkout', src, dst], ROOT)
        sh(['git', '-c', 'advice.detachedHead=false', 'checkout', '--quiet', c], dst)
    for f in OUTSIDE_GIT:
        os.makedirs(os.path.dirname(os.path.join(pub, f)), exist_ok=True)
        shutil.copy2(os.path.join(PUB, f), os.path.join(pub, f))
    env = dict(os.environ, PRIVATE_REPO=priv)
    sh(['python3', 'tools/sync_copies.py', '--private', priv], pub, env=env)
    for goal in ([], ['combined', 'forth-test-image']):
        sh(['make', '--no-print-directory', f'PRIVATE_REPO={priv}'] + goal, pub, env=env)
    return lane, pub, priv, {n: sha(os.path.join(pub, 'build', n)) for n in IMAGES}


def run_lane(i, lane, pub, priv, base, share, results):
    logs = os.path.join(lane, 'logs')
    os.makedirs(logs, exist_ok=True)
    env = dict(os.environ, PRIVATE_REPO=priv)
    for t in share:
        if stop.is_set():
            results[t] = (0, 'not run', [], i, [])
            continue
        extra = ['-o', 'test-mirror'] if t == 'test-vocabs' and 'test-mirror' in share else []
        log = os.path.join(logs, t + '.log')
        s = time.time()
        with open(log, 'w') as f:
            p = subprocess.Popen(['make', '--no-print-directory', t, f'PRIVATE_REPO={priv}',
                                  f'TEST_PORT_BASE={base}'] + extra, cwd=pub, env=env,
                                 stdout=f, stderr=subprocess.STDOUT, start_new_session=True)
            running[i] = p
            rc = p.wait()
            running.pop(i, None)
        lines = open(log, errors='replace').read().splitlines()
        results[t] = (round(time.time() - s), rc, [ln for ln in lines if SKIP.match(ln)], i, lines[-30:])


def interrupt(signum, _frame):
    stop.set()
    for p in list(running.values()):
        try:
            os.killpg(p.pid, signal.SIGTERM)   # the recipes' traps kill their QEMUs by PID
        except ProcessLookupError:
            pass


def qemu_left():
    left = []
    for d in os.listdir('/proc'):
        try:
            cmd = open(f'/proc/{d}/cmdline', 'rb').read().replace(b'\0', b' ').decode(errors='replace')
        except (OSError, ValueError):
            continue
        if 'qemu-system' in cmd and ROOT in cmd:
            left.append(d)
    return left


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--private-repo', required=True)
    ap.add_argument('--clones', type=int, default=1)
    ap.add_argument('--public', default='HEAD')
    ap.add_argument('--private', default='HEAD')
    ap.add_argument('--targets', default='', help='a subset of the test: line (default: all of it)')
    a = ap.parse_args()
    priv_real = os.path.abspath(os.path.join(PUB, a.private_repo))
    if not os.path.isdir(os.path.join(priv_real, '.git')):
        sys.exit(f'test-snapshot: FAIL: no private repo at {priv_real}')
    missing = [f for f in OUTSIDE_GIT if not os.path.isfile(os.path.join(PUB, f))]
    if missing:
        sys.exit(f'test-snapshot: FAIL: input outside git missing in the real tree: {" ".join(missing)}')
    if os.path.exists(ROOT):
        sys.exit(f'test-snapshot: REFUSED: {ROOT} is left from an earlier run; remove it first')
    pub_c = sh(['git', 'rev-parse', a.public + '^{commit}'], PUB).strip()
    priv_c = sh(['git', 'rev-parse', a.private + '^{commit}'], priv_real).strip()
    real_base = port_base(PUB)
    bases = [b for b in range(2200, 9000, 200) if b != real_base][:a.clones]
    if len(bases) < a.clones or len(set(bases)) != len(bases):
        sys.exit(f'test-snapshot: REFUSED: no {a.clones} distinct port bases')
    head = [f'public  {pub_c}  {PUB}', f'private {priv_c}  {priv_real}', f'clones  {a.clones}',
            f'ports   {" ".join(map(str, bases))} (real tree {real_base})']
    for name, tree in (('public', PUB), ('private', priv_real)):
        st = sh(['git', '--no-optional-locks', 'status', '--porcelain'], tree).splitlines()
        head += [f'not included ({name}, uncommitted): {ln[3:]}' for ln in st if not ln.startswith('??')]
        n = sum(ln.startswith('??') for ln in st)
        if n:
            head.append(f'not included ({name}, untracked): {n} paths (git status shows them)')
    for ln in head:
        print(ln, flush=True)
    os.makedirs(ROOT)
    open(os.path.join(ROOT, MARK), 'w').write(f'{os.getpid()}\n')
    signal.signal(signal.SIGINT, interrupt)
    signal.signal(signal.SIGTERM, interrupt)
    t0, results, rc_all = time.time(), {}, 1
    try:
        built = [lane_build(i, pub_c, priv_c, priv_real) for i in range(a.clones)]
        hashes = built[0][3]
        head += [f'{f} sha256 {sha(os.path.join(PUB, f))} (outside git, copied from the real tree)'
                 for f in OUTSIDE_GIT]
        for n in IMAGES:
            real = sha(os.path.join(PUB, 'build', n))
            head.append(f'image {n} {hashes[n]}  real build/: {"same" if real == hashes[n] else "differs (" + real[:16] + ")"}')
        if any(b[3] != hashes for b in built):
            head += [f'lane{i} {b[3]}' for i, b in enumerate(built)]
            head.append('GATE FAIL: the clones built different images (build not reproducible)')
            return 1
        targets = sh(['sed', '-n', 's/^test: //p', 'Makefile'], built[0][1]).split()
        if a.targets:
            unknown = [t for t in a.targets.split() if t not in targets]
            if unknown:
                head.append(f'REFUSED: not on the test: line: {" ".join(unknown)}')
                return 1
            targets = [t for t in targets if t in a.targets.split()]
            head.append(f'SUBSET: {len(targets)} targets, not a full run')
        cost = {}
        tsv = os.path.join(PUB, 'build', 'test-timing.tsv')
        if os.path.exists(tsv):
            for ln in open(tsv):
                s, _, t = ln.rstrip('\n').split('\t')
                cost[t] = int(s)
        groups = [[t] for t in targets if t not in ('test-mirror', 'test-vocabs')]
        groups.append(['test-mirror', 'test-vocabs'])
        load, share = [0] * a.clones, [set() for _ in range(a.clones)]
        for g in sorted(groups, key=lambda g: -sum(cost.get(t, 30) for t in g)):
            k = load.index(min(load))
            share[k].update(g)
            load[k] += sum(cost.get(t, 30) for t in g)
        threads = [threading.Thread(target=run_lane, args=(i, b[0], b[1], b[2], bases[i],
                                    [t for t in targets if t in share[i]], results))
                   for i, b in enumerate(built)]
        for th in threads:
            th.start()
        for th in threads:
            while th.is_alive():
                th.join(1)
        bad = [t for t in targets if t not in results or results[t][1] != 0 or results[t][2]]
        rc_all = 1 if bad or stop.is_set() else 0
        rows = ['seconds\texit\tskips\tlane\ttarget']
        for t in targets:
            s, rc, sk, ln, _ = results.get(t, (0, 'not run', [], '-', []))
            rows.append(f'{s}\t{rc}\t{len(sk)}\t{ln}\t{t}')
        head += rows
        for t in targets:
            if t in results and results[t][2]:
                head += [f'skip {t}: {x.strip()}' for x in results[t][2]]
        for t in bad:
            if t in results and results[t][1] != 0:
                head += [f'--- {t} exit {results[t][1]}, last lines:'] + results[t][4]
        head.append(f'TOTAL {round(time.time() - t0)} s  ' +
                    ('PASS' if rc_all == 0 else f'FAIL ({len(bad)}: {" ".join(bad)})'))
    except subprocess.CalledProcessError as e:
        head.append(f'SETUP FAIL: {" ".join(e.cmd)}\n{e.stdout}\n{e.stderr}')
    finally:
        left = qemu_left()
        if left:
            head.append(f'QEMU still running from the snapshot (pids {" ".join(left)}); {ROOT} kept')
        elif os.path.isfile(os.path.join(ROOT, MARK)):
            shutil.rmtree(ROOT)
        os.makedirs(os.path.join(PUB, 'build'), exist_ok=True)
        out = os.path.join(PUB, 'build', 'test-snapshot.txt')
        open(out, 'w').write('\n'.join(head) + '\n')
        print('\n'.join(head[4:]), flush=True)
        print(f'Result: {out}')
    return rc_all


if __name__ == '__main__':
    sys.exit(main())
