#!/usr/bin/env python3
"""Every recipe trap that runs a kill macro must include PIPE.

A recipe's output often goes into a pipe (`make test-x 2>&1 | grep ...`).
If the pipe's reader dies (e.g. it shares timeout's process group), the
recipe shell's next write raises SIGPIPE; without PIPE in the trap list
the shell dies there and its kill trap never runs, orphaning any QEMU
it started (docs/TASK_TEST_META_ORPHAN_RACE.md).

usage: check_kill_traps.py [Makefile]
Prints one line per offending trap and "kill traps with PIPE: N/M".
Exit 0 only when M > 0 and N == M.
"""
import re
import sys

path = sys.argv[1] if len(sys.argv) > 1 else 'Makefile'
lines = open(path).read().split('\n')
# join backslash continuations so a trap split across lines is one record,
# keeping the line number where it starts
records, buf, start = [], '', None
for i, ln in enumerate(lines, 1):
    if start is None:
        start = i
    if ln.endswith('\\'):
        buf += ln[:-1] + ' '
        continue
    records.append((start, buf + ln))
    buf, start = '', None

TRAP = re.compile(r"\btrap\s+'([^']*)'\s+([A-Z0-9 ]+?)\s*(?:;|$)")
total = good = 0
for lineno, rec in records:
    for m in TRAP.finditer(rec):
        action, sigs = m.group(1), m.group(2).split()
        if 'KILL' not in action:
            continue
        total += 1
        if 'PIPE' in sigs:
            good += 1
        else:
            print(f"{path}:{lineno}: trap '{action}' {' '.join(sigs)} -- no PIPE")
print(f"kill traps with PIPE: {good}/{total}")
if total == 0:
    print("FAIL: no kill traps found (parser or Makefile changed)")
sys.exit(0 if total and good == total else 1)
