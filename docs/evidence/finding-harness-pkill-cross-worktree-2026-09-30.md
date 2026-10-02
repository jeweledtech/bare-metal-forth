# FINDING — QEMU cleanup by name pattern is a cross-session kill (2026-09-30)

A test-infrastructure defect that produces intermittent failures which
*look like code regressions but are not*. Recorded so the next person who
hits "Failed to find an available port" or a mid-suite `BrokenPipeError`
does not chase it through the kernel. Read-only audit; the fixes are
scoped below (per-worktree ports and the CLAUDE.md advice are done; the
Makefile recipes are not).

> Reconciles two independently-written drafts (one in the main tree, one
> in the firstboot worktree, 2026-09-30) into one doc. The worktree draft's
> timeline analysis (the Evidence section) is the reason the earlier
> "confirmed cross-worktree recipe kill" reading is now stated as
> contradicted.

## The defect — cleanup by pattern, not by PID

Every daemonized test QEMU is torn down by name pattern, never by PID:
```
pkill -9 -f "[q]emu.*<port>"
```
`pkill -f` matches every process on the machine whose command line
contains that pattern — it is not scoped to this worktree, this recipe,
or even this QEMU. The main-tree Makefile has **55** such lines, **17**
`-daemonize` launches, and **no** `-pidfile`. Combined with a **single
shared port base**:
```
TEST_PORT_BASE ?= 4500        # Makefile:260 (at the time of this finding)
```
two checkouts (a main tree and a `firstboot` worktree) both defaulted to
4500, so their ranges (4500–4600) overlapped completely, and:

- **Cross-worktree kill:** tree A finishing `test-xhci` runs
  `pkill -9 -f "[q]emu.*4593"`, which also kills tree B's QEMU on 4593 —
  and vice versa. Each tree can silently murder the other's running tests,
  surfacing as a `BrokenPipeError` or an empty read after checks had been
  passing.
- **Loose / substring match:** `"[q]emu.*4593"` matches any QEMU whose
  command line merely *contains* `4593` (a different port field, a drive
  index, a path), not only the one bound to that serial/monitor port.
- **Stale survivors:** if a recipe is interrupted between launch and its
  teardown line, its QEMU lingers holding the port; the next run then
  fails at launch with `Failed to find an available port`.

## A broader instance — the documented pre-launch kill

`docs/CLAUDE.md`'s QEMU guidance used to say "always `pkill -9 -f qemu ||
true` before starting new instances." That kills **every QEMU on the
machine by name**, regardless of port — so any session following the
advice killed every other session's QEMUs. This is the wider version of
the same mistake: a name kill that cannot tell its own process from
anyone else's. **Replaced 2026-10-01** — `docs/CLAUDE.md` now says *never*
`pkill -9 -f qemu`, start with a known PID and kill only that PID.

## Blast radius

- **55** `pkill -9 -f` recipes in `Makefile`.
- Tests that pattern-kill directly: `tests/iv_roundtrip_test.py:13`,
  `tests/test_meta_b6b.py:133`, `tests/synced_reverify.py:68` (and the
  per-test scripts that inherit the idiom).
- **One** `TEST_PORT_BASE` default for all worktrees (before the fix).

## Evidence — the 2026-09-30 xHCI failure, carefully bounded

The firstboot worktree's full `make test` (base 4500) died in `test-xhci`
with a `BrokenPipeError` right after a read returned empty — the signature
of a killed QEMU. A main-tree `make test`, also at base 4500, was running
when the owner looked. What that does and does **not** establish:

- **Established:** both trees were at base 4500, so the mechanism above
  was live and the ranges did overlap.
- **Contradicted for the recipe-kill path:** the main-tree `make` started
  at **16:41:30** (`ps lstart`); the worktree's traceback — its last log
  write — was at **16:41:26**, four seconds *earlier*. A fresh aggregate
  needs minutes to reach `test-xhci`, the only main-tree recipe whose
  pattern matches 4593/4594. So that run's recipe cleanup **cannot** have
  made this kill. The tempting "the other tree's test-xhci teardown killed
  mine" reading does not fit the timestamps.
- **Consistent but unverified:** a broad pre-launch `pkill -f qemu` (the
  §"broader instance" kind) issued just before the 16:41:30 launch would
  explain it and fits the timing. The launching shell's command line is
  gone, so this cannot be confirmed now.

The fixes below remove **both** paths, so the repair does not depend on
which kill it actually was — which is the right posture given the evidence
cannot choose between them.

## Why it matters beyond annoyance

An intermittent, machine-state-dependent failure on the exact suite you
just changed is the worst kind: it invites "my change broke xHCI" when the
truth is "another session's cleanup killed my QEMU." It erodes the
must-not-move signal — a red `make test` stops meaning "you broke
something."

## The fix

1. **Kill by PID, never by pattern** (not yet applied to the 55 Makefile
   recipes). Give every daemonized launch `-pidfile`, wrap each recipe in
   one shell with `trap '<kill $(cat pidfile)>' EXIT INT TERM HUP`, and
   pre-clean a leftover pidfile's PID before launching (SIGKILL cannot be
   trapped). Pidfiles live in the tree's own `build/`, so a tree can only
   ever kill its own QEMUs. This is already `test-firstboot`'s pattern
   (`FB_KILL`), verified on normal exit, SIGINT, SIGTERM and SIGKILL
   (2026-09-29). Best as one shared make helper so all 55 recipes call it;
   the three `.py` files switch from `pkill -f` to killing the `Popen`
   handle they already own.
2. **Per-worktree `TEST_PORT_BASE` default — DONE (65a5cdd).** Derived
   from a cksum of `$(CURDIR)` (step 200), so two checkouts never share a
   range; `?=` still lets CI/the user pin it. Optionally also have a recipe
   refuse to start when its serial port is already bound (`ss -tln`), so a
   collision fails loudly instead of killing or hijacking.
3. **Replace the CLAUDE.md pre-launch kill — DONE (2026-10-01).** See the
   "broader instance" section.

Either (1) or (2) alone reduces the collisions; **both** remove the
*port-collision* class: kill-by-PID stops the cross-kill, per-worktree
ports stop the launch-time port clash. They do **not** close the
image-lock class below — a separate dimension the port fix never touched.

Red first: two trees at the same base, one mid-suite, the other running a
single recipe. Today the first loses its QEMU; after (1) it must not.

## An adjacent class the port fix does not close (2026-10-01)

Per-worktree `TEST_PORT_BASE` isolates **ports**, not the **image**. QEMU
takes a write lock on `build/bmforth.img`, and that file is shared by every
run in the same worktree. So two `make test` in one tree still collide — at
`test-smoke`, the first QEMU test:
```
qemu-system-i386: Failed to get "write" lock
Is another process using the image [build/bmforth.img]?
make: *** [Makefile:280: test-smoke] Error 1
```
A `-daemonize` QEMU **orphaned** by a killed run holds the lock
indefinitely (e.g. a `timeout` SIGTERM landing mid-`test-xhci`, before its
teardown line runs). Diagnose with `fuser build/bmforth.img` → PID; confirm
the holder's `tcp::PORT` is in **this** worktree's range (`TEST_PORT_BASE` +
offset; xhci = base+94) before killing it by PID — it may be your own
orphan, or another session's live run, and only the first is yours to kill.
The real cure is the same as the port class: kill-by-PID teardown that
cannot leave a daemonized survivor.

**Second occurrence, 2026-10-02 (it is the standing condition, not an
exception to wait out).** While diagnosing the test-hang fix, a parallel
session's QEMU held this worktree's `build/combined-ide.img` and rebuilt the
shared images under an active run, killing the guest mid-test at
non-deterministic points and masquerading as a fix bug — a second
cross-session collision costing a diagnosis cycle this week. The answer is
not to wait for a quiet tree but to **work in a dedicated git worktree**: a
separate `build/` ends the image collision by construction (CPU is still
shared, so TCG runs slow under load, but that only slows — it does not
corrupt). Parallel terminals here are standing, so trip/harness work that
touches shared `build/` artifacts should assume them.

Two verification traps seen running this down, each of which makes a green
tree look red or a red look green:

- **`make -n test` inverts the corpus-absent gate.** `test-corpus-absent`
  shells out to `make <subtest>` with an empty `CORPUS_ROOT` and expects
  each to *refuse*. Under `-n`, every child dry-run-exits 0 **without
  running**, so the gate reports its own failure condition — "3 passed
  without inputs", `Error 1` — precisely because nothing ran. `make -n test`
  is therefore not a valid pre-flight; verify with a real invocation
  (`make -C tools/translator test-corpus-absent` → "3 refused, 0 passed
  without inputs").
- **A wrapper's exit code is not make's.** `make test | tail` or
  `make test; echo done` reports the *wrapper's* status; a `make test` that
  exited 2 showed through as "exit 0". Capture `MAKE_TEST_EXIT=$?` into the
  log and read that, plus the suite's own `All tests passed!` marker — never
  the harness's status line.

## Related

- `known_qemu_daemonize` (the `-daemonize` TCP listener race) is a sibling
  harness hazard; the pidfile change should keep any `-daemonize` recipes
  consistent.
