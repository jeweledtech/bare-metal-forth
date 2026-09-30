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

Either fix alone reduces the collisions; **both** removes the class:
kill-by-PID stops the cross-kill, per-worktree ports stop the
launch-time port clash.

## Related

- `known_qemu_daemonize` (the `-daemonize` TCP listener race) is a
  sibling harness hazard; the pidfile change should keep any
  `-daemonize` recipes consistent.
