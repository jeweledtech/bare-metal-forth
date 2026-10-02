# FINDING — test-harness `pkill -f "[q]emu.*<port>"` kills across worktrees (2026-09-30)

A test-infrastructure defect that produces intermittent failures which
*look like code regressions but are not*. Recorded so the next person who
hits "Failed to find an available port" does not chase it through the
kernel. Read-only audit; fix is scoped below, not applied here.

## The defect

Every QEMU test recipe tears down with a **machine-wide pattern kill**:
```
pkill -9 -f "[q]emu.*<port>"
```
`pkill -f` matches every process on the machine whose command line
contains that pattern — it is not scoped to this worktree, this recipe,
or even this QEMU. Combined with a **single shared port base**:
```
TEST_PORT_BASE ?= 4500        # Makefile:260
```
two checkouts (e.g. a main tree and a `firstboot` worktree) both default
to 4500, so their port ranges (4500–4600) overlap completely, and:

- **Cross-worktree kill:** tree A finishing `test-xhci` runs
  `pkill -9 -f "[q]emu.*4593"`, which kills tree B's QEMU on 4593 too —
  and vice versa. Each tree silently murders the other's running tests.
- **Loose match:** `"[q]emu.*4593"` also matches any QEMU whose command
  line merely *contains* `4593` (a different port field, a drive index,
  a path), not only the one bound to that serial/monitor port.
- **Stale survivors:** if a recipe is interrupted between launch and its
  teardown line, its QEMU lingers holding the port; the next run then
  fails at launch with `Failed to find an available port`.

## Blast radius

- **55** `pkill -9 -f` recipes in `Makefile`.
- Tests that pattern-kill directly: `tests/iv_roundtrip_test.py:13`,
  `tests/test_meta_b6b.py:133`, `tests/synced_reverify.py:68` (and the
  many per-test scripts that inherit the idiom).
- **One** `TEST_PORT_BASE` default for all worktrees.

## Evidence

- **2026-09-30, this tree:** a full `make test` (CARRIER-0b M2) died at
  `test-xhci` — `qemu-system-i386: -monitor tcp:127.0.0.1:4593 … Failed
  to find an available port`. A stale `qemu-system-i386 … qemu-xhci`
  (from an earlier run, at the shared base) still held 4593. Everything
  before it had passed. `pkill -9 -f qemu-system` by hand + a re-run was
  clean (`carrier-0b-make-test-2026-09-29.log`). It cost real triage to
  separate this from a genuine CARRIER-0b regression.
- **Owner, same day:** the `firstboot` worktree hit the same collision
  from the other side — confirming it is cross-worktree, not a single
  stale process.

## Why it matters beyond annoyance

An intermittent, machine-state-dependent failure on the exact suite you
just changed is the worst kind: it invites "my change broke xHCI" when
the truth is "another worktree's teardown killed my QEMU." It erodes the
must-not-move signal — a red `make test` stops meaning "you broke
something."

## The fix (owner's spec, 2026-09-30 — scoped, not applied here)

1. **pidfile + kill-by-PID, everywhere.** Each recipe launches QEMU with
   a known PID (background `&` + `$!`, or `-pidfile`), and teardown kills
   **that PID**, never a pattern. Best as one shared make helper/function
   so all 55 recipes call it instead of open-coding `pkill -f`. The three
   test `.py` files switch from `pkill -f` to killing the `Popen` handle
   they already own.
2. **Per-worktree `TEST_PORT_BASE` default.** Derive the default from the
   worktree so two trees never share a range — e.g. from a hash of the
   worktree path, or a small per-worktree override file. `?=` still lets
   CI/the user pin it.

Either fix alone reduces the collisions; **both** removes the
*port-collision* class: kill-by-PID stops the cross-kill, per-worktree
ports stop the launch-time port clash. It does **not** close the
image-lock class below — a separate dimension the port fix never touched.

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

- `known_qemu_daemonize` (the `-daemonize` TCP listener race) is a
  sibling harness hazard; the pidfile change should keep any
  `-daemonize` recipes consistent.
