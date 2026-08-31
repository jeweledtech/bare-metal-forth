"""Makefile wiring gate: every test-* target is in `test:` or is
exempted WITH a reason.

History that earns the gate: two suites were found orphaned from the
`test:` aggregate -- test-survey (2026-07, finding_survey_tests
resolution) and test-squote-laydown (2026-08-30, caught by headline
lineage: 905 unchanged after adding a 63-check suite).  A third,
test-network, was found not merely orphaned but BROKEN (NameError on
a stale return, unrunnable) -- orphaning is what hid the breakage.
The `test:` line is a hand-maintained list; this gate makes the
third silent orphan impossible rather than merely embarrassing.
Third granularity of "what calls this?": FREE-SLOT was a word with
no caller, dict_under_ nearly a label with no branch, these are
suites with no aggregate.

An exemption is a CLAIM that the suite should not run in the sweep,
and the claim must be true -- reasons are load-bearing, checked
non-empty, and an exemption for a target that IS wired (or does not
exist) is stale and fails.  Entries marked "grandfathered" say so
explicitly: skip must not read like a pass (gate discipline,
2026-07-28).

This gate is subject to its own rule: test-make-wiring must appear
in `test:`.  A gate absent from the aggregate is the exact defect
it polices.
"""
import hashlib
import os
import re
import sys

MAKEFILE = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', 'Makefile'))

# Three classes, three different claims -- kept apart so the debt
# stays countable instead of becoming prose inside a reason string
# (the place debt goes to become permanent).  The counts are
# printed; "N grandfathered, N broken" is a number someone watches
# shrink.
#
# EXEMPT: verified deliberate.  The claim "this should not run in
# the sweep" has been checked and is true.
EXEMPT = {
    'test-squote-laydown-backstop0':
        'needs the throwaway -DDICT_BACKSTOP=0 image (make backstop0);'
        ' one-shot liveness proof with its own evidence total, pinned'
        ' out of the sweep by the suite docstring',
    'test-pipeline':
        'UBT translator pipeline, not a kernel suite; excluded from'
        ' make test by design (docs/CLAUDE.md)',
    'test-arm64-boot':
        'ARM64 virt dispatch defect open (wild jump to 0x401A1FA4,'
        ' recorded 2026-07) -- cannot be green until resolved; needs'
        ' qemu-system-aarch64',
}
# GRANDFATHERED: outside `test:` when this gate landed (2026-08-30);
# deliberateness UNVERIFIED, review owed.  A deferred claim, not a
# true one -- each entry either moves to EXEMPT with a verified
# reason, gets wired, or gets repaired.
GRANDFATHERED = {
    'test-cortexm':
        'needs ARM Cortex-M QEMU',
    'test-flush':
        'bulk SAVE-BUFFERS known issue (bug #21 family)',
    'test-ahci-write':
        'needs AHCI scratch disk',
    'test-meta':
        'long QEMU metacompiler chain',
}
# BROKEN: cannot run at all; repair owed.  Orphaning is what hid
# the breakage -- a suite outside the aggregate never runs, so it
# rots silently.
BROKEN = {
    'test-network':
        'NameError blocks_b in start_qemu_pair (stale return from a'
        ' refactor), observed 2026-08-30 -- make test-network cannot'
        ' run at all',
}
ALL_EXEMPT = {**EXEMPT, **GRANDFATHERED, **BROKEN}
if len(ALL_EXEMPT) != len(EXEMPT) + len(GRANDFATHERED) + len(BROKEN):
    print('FAIL: a target appears in more than one exemption class')
    sys.exit(1)

passed = 0
failed = 0


def check(name, ok, detail=''):
    global passed, failed
    if ok:
        passed += 1
        print(f'  PASS: {name}')
    else:
        failed += 1
        print(f'  FAIL: {name}' + (f' -- {detail}' if detail else ''))


with open(MAKEFILE, 'rb') as f:
    _raw = f.read()
print(f'input sha256 {hashlib.sha256(_raw).hexdigest()}  {MAKEFILE}')
src = _raw.decode()

targets = sorted(set(re.findall(r'^(test-[A-Za-z0-9_-]+):', src, re.M)))
# The aggregate line, with backslash continuations folded so the
# gate survives the line being wrapped.  Folded BEFORE the search:
# a regex that tries to span the continuation inline can succeed
# greedily on the first physical line alone (the `(?:\\\n...)*`
# branch legally matches zero times and multiline $ accepts the
# spot), and a successful match is never backtracked into -- the
# wrapped-Makefile fixture caught exactly that (9 deps for 17).
_folded = src.replace('\\\n', ' ')
m = re.search(r'^test:(.*)$', _folded, re.M)
if not m:
    print('FAIL: no `test:` aggregate target found')
    sys.exit(1)
wired = set(m.group(1).split())

# Class counts, printed on EVERY run including green: the
# grandfathered and broken counts are standing debt markers, and a
# number that appears only on failure is never watched.
_wired_suites = [t for t in targets if t in wired]
print(f'\ntest-make-wiring: {len(_wired_suites)} wired, '
      f'{len(EXEMPT)} exempt, {len(GRANDFATHERED)} grandfathered '
      f'(review owed), {len(BROKEN)} broken (repair owed); '
      f'{len(targets)} test-* targets, {len(wired)} deps on `test:`')

print('\nMembership: every test-* target wired or exempted')
_class_of = {}
for name, entries in (('exempt', EXEMPT),
                      ('grandfathered', GRANDFATHERED),
                      ('broken', BROKEN)):
    for t in entries:
        _class_of[t] = name
for t in targets:
    if t in wired:
        check(f'{t} wired into test:', True)
    elif t in ALL_EXEMPT:
        cls = _class_of[t]
        reason = ALL_EXEMPT[t]
        check(f'{t} {cls} with reason', bool(reason.strip()),
              'empty reason -- an exemption without a reason is an '
              'orphan with paperwork')
        print(f'        reason: {reason}')
    else:
        check(f'{t} wired or exempt', False,
              'orphaned suite -- wire it into `test:` or exempt it '
              'WITH a true reason')

print('\nStaleness: every exemption names a real, unwired target')
for e in sorted(ALL_EXEMPT):
    cls = _class_of[e]
    if e not in targets:
        check(f'{cls} entry {e} names an existing target', False,
              'target gone -- delete the entry')
    elif e in wired:
        check(f'{cls} entry {e} still unwired', False,
              'target is wired now -- the entry is stale, delete it '
              '(for BROKEN entries: the repair that wired it must '
              'also remove the entry, not leave a lie about a suite '
              'that now works)')
    else:
        check(f'{cls} entry {e} valid (exists, unwired)', True)

print('\nSelf-application')
check('this gate (test-make-wiring) is itself in test:',
      'test-make-wiring' in wired,
      'a gate absent from the aggregate is the defect it polices')

print(f'\nPassed: {passed}/{passed + failed}')
sys.exit(0 if failed == 0 else 1)
