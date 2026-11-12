#!/usr/bin/env python3
"""A public clone's make test skips, never drops (private
TASK_PUBLIC_CLONE_SUITE).

A clone of this repo's committed HEAD in a mktemp directory, with no
private repo beside it (public mode at the Makefile default), host only:
no QEMU is started.
  P1 (84) make -n <t> never stops at "No rule to make target", for every
          target on test: (the pinned 83 and the clone's test: line).
  P2 (30) each skip-whole target runs its run-mode guard first, ends with
          its exact SKIPPED line, exits 0 and builds no build/combined.img.
  P3 (1)  the free tier builds the usual names from the free set:
          build/kernel.bin = build/kernel-free.bin.
  P4 (3)  no fallback to public mode: PRIVATE_REPO set and absent FAILS;
          a private repo beside the clone with forth/dict/ahci.fth absent
          from the tree FAILS; test-translator with a private repo beside
          it and tools/translator absent FAILS.
  P5 (2)  VOCAB_SOURCES follows PRIVATE_REPO, not ../forthos-vocabularies.
  P6 (1)  port_inventory.py --check: 0 problems.

Usage: test_public_clone.py [<patch>]
With a patch (`git diff HEAD`, saved to a file), the clone of HEAD has it
applied before any check, and its sha256 is printed: the green gate
before a commit. Without one, HEAD is checked as is.
"""
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOTAL = 121

# The 32 that run in a public clone: 31 on the free kernel, and the host-only
# test-sync-copies (private TASK_SYNC_COPIES). (Measured, M1/M2;
# test-block-read-error added by private TASK_KERNEL_BLOCK_READ_ERROR;
# test-vbe-boot and test-vbe-nostub by private TASK_UNICORN_WRITER, measured
# in a public clone 2026-11-02).
RUN = '''test-xhci test-pci-bar test-block-reload test-blk-evict test-block-read-error test-stack-floor
test-vga-wrap test-reload-vocab test-load-vocab test-vbr test-pxe-label test-uefi2-gdt
test-carrier-write-safe test-memdisk test-mirror test-hal test-hal-match test-network
test-vocabs test-integration test-file-stream test-net-flush-lf test-console-band
test-window-focus test-search-order test-vocab-dedup test-window-forms test-double-cell
test-forth83 test-vbe-boot test-vbe-nostub test-sync-copies'''.split()
# The 29 that skip whole, and the reason each names.
PRIVATE_TEST = '''test-log-harness test-log-harness-nic test-log-restore test-log-validation
test-log-send test-lic-observe test-dlg2form test-rtl8168-cksum test-hal-match-hp test-pipeline-e2e
test-arm64-boot test-meta-b6b test-gui test-translator test-urw-canvas'''.split()
NEEDS_VOCABS = '''test-firstboot test-install test-resolve-deps test-uefi-boot test-fat32-read
test-uefi-netboot test-g6 test-hal-net test-interp-abort test-pad-move test-abort-routes
test-phys-alloc'''.split()
SKIP = {t: 'the test is private' for t in PRIVATE_TEST}
SKIP.update({t: 'needs the private vocabularies' for t in NEEDS_VOCABS + ['test-survey']})
SKIP['check-sync'] = 'no private repo to compare'
SKIP['test-check-sync'] = 'no private repo to compare'
# The 2 whose scripts print SKIPPED themselves, and the other 20 (test-nasm-pin
# and test-net-receive-replace host-only, private TASK_UNICORN_WRITER;
# test-capture-boot-path host-only, private TASK_TFTP_TRANSFER_LOGGING).
SELF_SKIP = ['test-phys-refuse', 'test-read-flags']
OTHER = '''lint check-coverage test-smoke test-loops test-abort test-dict-bounds
test-pci-typing test-squote-laydown test-log-decode-layout test-grub-cfg test-doc-drift
test-make-wiring test-port-inventory test-kill-traps test-pipeline
test-free-boot test-public-clone test-nasm-pin test-net-receive-replace
test-capture-boot-path'''.split()
ALL = RUN + list(SKIP) + SELF_SKIP + OTHER
assert (len(RUN), len(SKIP), len(SELF_SKIP), len(OTHER), len(set(ALL))) == (32, 30, 2, 20, 84)

PASS = FAIL = 0


def check(name, ok, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {name}', flush=True)
    else:
        FAIL += 1
        print(f'  FAIL: {name}' + (f' -- {detail}' if detail else ''), flush=True)


def sha(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


# The outer make's flags (-k, the jobserver) and any PRIVATE_REPO must not
# reach the clone's make: it runs at its own Makefile defaults.
ENV = {k: v for k, v in os.environ.items()
       if k not in ('MAKEFLAGS', 'MFLAGS', 'MAKELEVEL', 'MAKEOVERRIDES',
                    'PRIVATE_REPO', 'PRIVATE_REPO_ORIGIN')}


def run(cmd, cwd, timeout=300):
    try:
        p = subprocess.run(cmd, cwd=cwd, env=ENV, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=timeout)
        return p.returncode, p.stdout.decode('utf-8', 'replace')
    except subprocess.TimeoutExpired as e:
        return 124, (e.stdout or b'').decode('utf-8', 'replace') + '\n[timeout]'


def make(args, cwd, timeout=300):
    return run(['make', '--no-print-directory'] + args, cwd, timeout)


def last_line(out):
    lines = [ln for ln in out.split('\n') if ln.strip()]
    return lines[-1].strip() if lines else ''


patch = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else None
head = subprocess.run(['git', '-C', ROOT, 'rev-parse', 'HEAD'], stdout=subprocess.PIPE,
                      check=True).stdout.decode().strip()
print(f'input sha256 {sha(os.path.abspath(__file__))}  tests/test_public_clone.py')
print(f'HEAD {head}')
if patch:
    print(f'patch sha256 {sha(patch)}  {patch}')
else:
    print('patch: none (HEAD as is)')

TMP = tempfile.mkdtemp(prefix='pubclone-')
W = os.path.join(TMP, 'w')
PUB = os.path.join(W, 'pub')
SIB = os.path.join(W, 'forthos-vocabularies')
try:
    os.makedirs(W)
    subprocess.run(['git', 'clone', '-q', '--no-hardlinks', ROOT, PUB], check=True)
    subprocess.run(['git', '-C', PUB, 'checkout', '-q', head], check=True)
    if patch:
        subprocess.run(['git', '-C', PUB, 'apply', '--index', patch], check=True)
    assert not os.path.exists(os.path.join(PUB, 'forth', 'dict', 'ahci.fth'))
    assert not os.path.exists(SIB)

    print('\nP1: make -n <t> never stops at "No rule to make target"')
    src = open(os.path.join(PUB, 'Makefile')).read().replace('\\\n', ' ')
    wired = re.search(r'^test:(.*)$', src, re.M).group(1).split()
    for t in ALL + [t for t in wired if t not in ALL]:
        rc, out = make(['-n', t], PUB)
        bad = [ln for ln in out.split('\n') if 'No rule to make target' in ln]
        check(f'P1 {t}: make -n starts it', not bad and t in wired,
              bad[0].strip() if bad else (f'not on test:' if t not in wired else ''))

    print('\nP2: each skip-whole target skips by its guard, naming the mode')
    for t, reason in SKIP.items():
        want = f'SKIPPED (public mode: PRIVATE_REPO absent): {t}, {reason}'
        rc, out = make(['-n', t], PUB)
        first = next((ln.strip() for ln in out.split('\n') if ln.strip()), '')
        if f'tests/run_mode.py {t}' not in first:
            check(f'P2 {t}: guard first, then "{want}"', False,
                  f'first command is not its guard (not run): {first[:100]!r}')
            continue
        rc, out = make([t], PUB, 120)
        img = os.path.exists(os.path.join(PUB, 'build', 'combined.img'))
        got = last_line(out)
        check(f'P2 {t}: "{want}", exit 0, no image',
              rc == 0 and got == want and not img,
              f'exit {rc}, last line {got!r}, combined.img {"built" if img else "absent"}')

    print('\nP3: the free tier builds the usual names from the free set')
    rc, out = make(['build/kernel.bin', 'build/kernel-free.bin'], PUB, 300)
    k, kf = (os.path.join(PUB, 'build', n) for n in ('kernel.bin', 'kernel-free.bin'))
    same = rc == 0 and os.path.exists(k) and os.path.exists(kf) and sha(k) == sha(kf)
    check('P3 build/kernel.bin = build/kernel-free.bin', same,
          f'exit {rc}: {last_line(out)!r}' if rc else
          (f'{sha(k)[:16]} != {sha(kf)[:16]}' if os.path.exists(k) and os.path.exists(kf) else 'missing'))

    print('\nP4: no fallback to public mode')
    absent = os.path.join(TMP, 'absent')
    rc, out = make(['test-firstboot', f'PRIVATE_REPO={absent}'], PUB, 120)
    check('P4 PRIVATE_REPO set and absent: test-firstboot FAILS',
          rc != 0 and f'FAIL: PRIVATE_REPO set (command line) to {absent}, not found' in out,
          f'exit {rc}, last line {last_line(out)!r}')
    os.makedirs(os.path.join(SIB, 'forth', 'dict'))
    rc, out = make(['test-firstboot'], PUB, 120)
    check('P4 private repo beside it, forth/dict/ahci.fth absent: test-firstboot FAILS',
          rc != 0 and 'FAIL: PRIVATE_REPO' in out and 'forth/dict/ahci.fth' in out
          and 'SKIPPED' not in out, f'exit {rc}, last line {last_line(out)!r}')
    rc, out = make(['test-translator'], PUB, 120)
    check('P4 private repo beside it, tools/translator absent: test-translator FAILS',
          rc != 0 and 'FAIL: PRIVATE_REPO' in out and 'tools/translator/Makefile' in out,
          f'exit {rc}, last line {last_line(out)!r}')
    shutil.rmtree(SIB)

    print('\nP5: VOCAB_SOURCES follows PRIVATE_REPO')
    px = os.path.join(TMP, 'px')
    os.makedirs(os.path.join(px, 'forth', 'dict'))
    open(os.path.join(px, 'forth', 'dict', 'zz.fth'), 'w').close()
    os.makedirs(os.path.join(SIB, 'forth', 'dict'))
    open(os.path.join(SIB, 'forth', 'dict', 'yy.fth'), 'w').close()
    rc, out = make(['-s', '--eval', 'pc-vocab-sources: ; @echo $(VOCAB_SOURCES)',
                    'pc-vocab-sources', f'PRIVATE_REPO={px}'], PUB, 60)
    check('P5 VOCAB_SOURCES lists PRIVATE_REPO/forth/dict/zz.fth',
          os.path.join(px, 'forth', 'dict', 'zz.fth') in out.split(), f'got {out.strip()[-200:]!r}')
    check('P5 VOCAB_SOURCES does not list ../forthos-vocabularies/forth/dict/yy.fth',
          'yy.fth' not in out, f'got {out.strip()[-200:]!r}')
    shutil.rmtree(SIB)

    print('\nP6: the port inventory in a public clone')
    rc, out = run(['python3', 'tools/port_inventory.py', '--check', 'tools/qemu_ports.json'], PUB, 120)
    check('P6 port_inventory.py --check: 0 problems, exit 0',
          rc == 0 and '; 0 problem(s)' in out, f'exit {rc}, {last_line(out)!r}')
finally:
    shutil.rmtree(TMP, ignore_errors=True)

n = PASS + FAIL
print(f'\nPassed: {PASS}/{TOTAL}' + ('' if n == TOTAL else f' ({n} checks ran, {TOTAL} pinned)'))
sys.exit(0 if PASS == TOTAL and n == TOTAL else 1)
