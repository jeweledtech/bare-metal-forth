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

Scripts too (2026-10-28, TASK_TEST_WIRING_SCRIPTS): a target can only
be missing from `test:` if it exists.  tests/test_reload_vocab.py never
had one, so neither half above could see it.  Every file tracked
directly under tests/ must be reached by a recipe, or carry an
exemption with a reason, in the same classes.

This gate is subject to its own rule: test-make-wiring must appear
in `test:`.  A gate absent from the aggregate is the exact defect
it polices.

SCOPE NOTE (2026-09-04): this suite is the host-side build-tooling
gate generally, not just Makefile wiring.  The embed-stripper red
fixture below is an embed-vocabs.py behavior check; it lives here
because this is the sweep's only pure-Python no-QEMU gate suite,
and because it is this suite's own finding applied once more: the
stripper's sys.exit branch executes only in a state the tree never
contains, so without a pinned red a refactor that drops it passes
every build in silence.
"""
import hashlib
import os
import re
import subprocess
import sys
import tempfile

MAKEFILE = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', 'Makefile'))
ROOT_DIR = os.path.dirname(MAKEFILE)

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

print('\nScripts: every tracked tests/ file reached by a recipe')
# The target checks above never see a script that no target names:
# tests/test_reload_vocab.py had no recipe from the day it landed, so
# `make test` never ran it (TASK_TEST_WIRING_SCRIPTS, 2026-10-28).
# Reached = (a) basename or stem a whole token in a non-comment Makefile
# line (stems: VOCAB_TESTS_ALL and GUI_TESTS_ALL name scripts without
# .py), or (b) imported, or named in a quoted string, in a non-comment
# line of a file already reached; transitive.  Comments, docstring prose
# and documents do not reach.  Static: named by a recipe, not passing.
#
# SCRIPT_EXEMPT: verified deliberate, as EXEMPT above.
SCRIPT_EXEMPT = {
}
# SCRIPT_GRANDFATHERED: unreached when this check landed; deliberateness
# unverified, review owed (wire, exempt with a verified reason, delete).
_SCRIPT_UNREVIEWED = (
    'reached by no recipe when the script check landed (2026-10-28); not'
    ' run by make test; review owed: wire it, exempt it with a verified'
    ' reason, or delete it')
SCRIPT_GRANDFATHERED = {
    'tests/eviction_flush_test.py': _SCRIPT_UNREVIEWED,
    'tests/iv_roundtrip_test.py': _SCRIPT_UNREVIEWED,
    'tests/probe_crc32_kat.py': _SCRIPT_UNREVIEWED,
    'tests/probe_crc32_literals.py': _SCRIPT_UNREVIEWED,
    'tests/test-catalog-resolver.sh': _SCRIPT_UNREVIEWED,
    'tests/test_ahci_blk_reader.py': _SCRIPT_UNREVIEWED,
    'tests/test_ahci_blk_writer.py': _SCRIPT_UNREVIEWED,
    'tests/test_asm_vocab.py': _SCRIPT_UNREVIEWED,
    'tests/test_blk_writer_vector.py': _SCRIPT_UNREVIEWED,
    'tests/test_catalog_registry.py': _SCRIPT_UNREVIEWED,
    'tests/test_dump.py': _SCRIPT_UNREVIEWED,
    'tests/test_dword_attrs.py': _SCRIPT_UNREVIEWED,
    'tests/test_fe_strip_all_cr.py': _SCRIPT_UNREVIEWED,
    'tests/test_interrupts.py': _SCRIPT_UNREVIEWED,
    'tests/test_ne2000.py': _SCRIPT_UNREVIEWED,
    'tests/test_pci_enum.py': _SCRIPT_UNREVIEWED,
    'tests/test_persist_quick.py': _SCRIPT_UNREVIEWED,
    'tests/test_pit_timer.py': _SCRIPT_UNREVIEWED,
    'tests/test_ps2_keyboard.py': _SCRIPT_UNREVIEWED,
    'tests/test_ps2_mouse.py': _SCRIPT_UNREVIEWED,
    'tests/test_shutdown.py': _SCRIPT_UNREVIEWED,
    'tests/test_vga_graphics.py': _SCRIPT_UNREVIEWED,
}
# The grandfather list may only shrink (owner 2026-10-28), pinned by
# name: every entry must be in this frozen set of the 23 found when the
# check landed.  Removing a name is allowed; adding or swapping one is
# not -- a new script is wired, or exempted with a verified reason.  The
# set is hashed too (sorted names, newline after each), so widening it
# means changing the pinned sha256, which the task doc records.
SCRIPT_GRANDFATHERED_FROZEN = frozenset({
    'tests/eviction_flush_test.py',
    'tests/iv_roundtrip_test.py',
    'tests/probe_crc32_kat.py',
    'tests/probe_crc32_literals.py',
    'tests/test-catalog-resolver.sh',
    'tests/test_ahci_blk_reader.py',
    'tests/test_ahci_blk_writer.py',
    'tests/test_asm_vocab.py',
    'tests/test_blk_writer_vector.py',
    'tests/test_catalog_registry.py',
    'tests/test_dump.py',
    'tests/test_dword_attrs.py',
    'tests/test_fe_strip_all_cr.py',
    'tests/test_interrupts.py',
    'tests/test_ne2000.py',
    'tests/test_pci_enum.py',
    'tests/test_persist_quick.py',
    'tests/test_pit_timer.py',
    'tests/test_ps2_keyboard.py',
    'tests/test_ps2_mouse.py',
    'tests/test_shutdown.py',
    'tests/test_vga_graphics.py',
    'tests/test_vocab_dedup.py',
})
SCRIPT_GRANDFATHERED_FROZEN_SHA256 = (
    '7b6fc13e0e6bfd95cd0713670984021c9127b575e481a109f4c1a3f1ccefe158')
SCRIPT_ALL = {**SCRIPT_EXEMPT, **SCRIPT_GRANDFATHERED}
_ls = subprocess.run(['git', '-C', ROOT_DIR, 'ls-files', 'tests'],
                     capture_output=True, text=True)
if _ls.returncode != 0:
    check('git ls-files lists the tracked tests/ files', False,
          f'rc={_ls.returncode} {_ls.stderr.strip()!r} -- a skip must '
          'not read like a pass')
    scripts = []
else:
    scripts = sorted(f for f in _ls.stdout.split() if f.count('/') == 1)
# The count above is of TRACKED files, so a script still untracked when
# this runs is silently left out of it (private TASK_FORTH83_VOCAB's miss:
# 175 predicted as 174, the red read before `git add`). Any untracked,
# non-ignored file under tests/ fails instead (private TASK_TESTS_UNTRACKED).
_un = subprocess.run(['git', '-C', ROOT_DIR, 'ls-files', '--others',
                      '--exclude-standard', 'tests'],
                     capture_output=True, text=True)
untracked = sorted(_un.stdout.split()) if _un.returncode == 0 else None
check('no untracked, non-ignored file under tests/',
      untracked == [],
      f'rc={_un.returncode} {_un.stderr.strip()!r}' if untracked is None
      else f'{len(untracked)}: {untracked[:8]} -- track it, ignore it, or '
      'move it out of tests/')


def _token(x):
    return r'(?<![\w.-])' + re.escape(x) + r'(?![\w-])'


def _code(text):
    return '\n'.join(l for l in text.split('\n')
                     if not l.lstrip().startswith('#'))


_mk_code = _code(_folded)
reached = {f for f in scripts
           if re.search(_token(os.path.basename(f)), _mk_code)
           or re.search(_token(os.path.splitext(os.path.basename(f))[0]),
                        _mk_code)}
# This file never reaches anything: its quoted names are exemption
# entries, not runs (miss 1: the grandfather table reached all 23).
_SELF = 'tests/test_make_wiring.py'
_todo = sorted(reached - {_SELF})
while _todo:
    with open(os.path.join(ROOT_DIR, _todo.pop()), errors='replace') as f:
        _body = _code(f.read())
    for s in scripts:
        if s in reached:
            continue
        b = os.path.basename(s)
        st = os.path.splitext(b)[0]
        if (re.search(r'^\s*(import\s+[\w\s,]*\b' + re.escape(st)
                      + r'\b|from\s+' + re.escape(st) + r'\s+import)',
                      _body, re.M)
                or re.search(r'[\'"][^\'"\n]*\b' + re.escape(b) + r'[\'"]',
                             _body)):
            reached.add(s)
            if s != _SELF:
                _todo.append(s)
_unreached = [s for s in scripts if s not in reached]
print(f'test-make-wiring scripts: {len(scripts)} tracked, {len(reached)} '
      f'reached, {len(SCRIPT_EXEMPT)} exempt, {len(SCRIPT_GRANDFATHERED)} '
      f'grandfathered (review owed), '
      f'{len([s for s in _unreached if s not in SCRIPT_ALL])} unreached')
for s in scripts:
    if s in reached:
        check(f'{s} reached by a recipe', True)
    elif s in SCRIPT_ALL:
        cls = 'exempt' if s in SCRIPT_EXEMPT else 'grandfathered'
        check(f'{s} {cls} with reason', bool(SCRIPT_ALL[s].strip()),
              'empty reason -- an orphan with paperwork')
    else:
        check(f'{s} reached by a recipe', False,
              'no recipe runs it -- wire it, or exempt it WITH a true '
              'reason')
_frozen_sha = hashlib.sha256(''.join(
    n + '\n' for n in sorted(SCRIPT_GRANDFATHERED_FROZEN)).encode()).hexdigest()
check('script grandfather frozen set is the pinned one',
      _frozen_sha == SCRIPT_GRANDFATHERED_FROZEN_SHA256,
      f'sha256 {_frozen_sha} -- the frozen set changed; it may not grow')
_new = sorted(set(SCRIPT_GRANDFATHERED) - SCRIPT_GRANDFATHERED_FROZEN)
check('every grandfathered script is in the frozen set', not _new,
      f'not frozen: {_new} -- the list only shrinks; wire the script or '
      'exempt it with a verified reason')
for e in sorted(SCRIPT_ALL):
    if e not in scripts:
        check(f'script entry {e} names a tracked file', False,
              'not tracked -- delete the entry')
    elif e in reached:
        check(f'script entry {e} still unreached', False,
              'a recipe reaches it now -- the entry is stale, delete it')
    else:
        check(f'script entry {e} valid (tracked, unreached)', True)

print('\nSelf-application')
check('this gate (test-make-wiring) is itself in test:',
      'test-make-wiring' in wired,
      'a gate absent from the aggregate is the defect it polices')

print('\nEmbed-stripper red fixture: unclosed ( refuses the build')
# The stripper's sys.exit branch (348912b) executes only in a state
# the tree never contains -- every build and every sweep passes
# whether the branch exists or not.  This pins it: the fixture is
# the real 2026-09-03 failure shape (wrapped stack comment), and
# the assertion requires the SPECIFIC refusal -- exit non-zero AND
# stderr naming the fixture AND 'unclosed' -- so a misspelled path,
# a traceback, or a missing interpreter fails loudly instead of
# satisfying a bare rc != 0.  Success requires presence of
# evidence, not absence of trouble.
#
# The diagnostic's wording is CONTRACTUAL: naming the file and the
# unclosed ( is what the gate is for.  If this goes red after a
# message reword, restore the naming in embed-vocabs.py -- do not
# loosen the assertion to whatever the code happens to say.
#
# A missing fixture kills the suite before its Passed: line
# (open() below is unguarded) -- a STATED choice: the fixture is
# this check's evidence, and running without it would be the gate
# passing in a state nobody produced.  Cost: the wiring checks
# above die with it, and the sweep drops to 28 Passed: lines,
# which is itself the loud signal.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, 'tests', 'fixtures',
                       'unclosed-paren.fth-broken')
STRIPPER = os.path.join(ROOT, 'tools', 'embed-vocabs.py')
with open(FIXTURE, 'rb') as f:
    print(f'input sha256 {hashlib.sha256(f.read()).hexdigest()}'
          f'  {FIXTURE}')
with tempfile.NamedTemporaryFile(suffix='.bin') as tmp:
    proc = subprocess.run(
        [sys.executable, STRIPPER, tmp.name, FIXTURE],
        capture_output=True, text=True)
check('embed-vocabs.py refuses unclosed ( with named diagnostic',
      proc.returncode != 0
      and 'unclosed' in proc.stderr
      and 'unclosed-paren.fth-broken' in proc.stderr,
      f'rc={proc.returncode} stderr={proc.stderr.strip()!r} -- '
      f'the refusal branch is gone or no longer names its evidence')

print(f'\nPassed: {passed}/{passed + failed}')
sys.exit(0 if failed == 0 else 1)
