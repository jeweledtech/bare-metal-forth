# FINDING — the built image is not reproducible from the tree: an uncommitted generator (2026-10-02)

This is the **check-sync class**, not the harness class, and it is bigger than
the kill-by-PID task — it undermines every hash gate and every "it passed"
claim until it is resolved. Recorded for the owner to sequence with the other
session; do not act on it inside the harness task.

## Observed

`build/combined.img` took three different hashes in one day with **no
committed source change**:

- `17e7da0f` — the firstboot merge-verify / "passed this morning" image.
- `b64f11d4` — main's image a few hours later (snapshotted 2026-10-02).
- `01e870ace2…` — a clean canonical build from `origin/master` (`aec9531`)
  in a fresh worktree.

## Cause

`tools/write-catalog.py` — the catalog **generator** — has **uncommitted**
changes in the main working tree: it adds `TELEMETRY_RESERVED = range(208,216)`
and `LOG_BLK = 208` and a multi-reserved-range packer (log-harness ring
persistence). Those shift every vocab's block placement, so the generator
produces a different `combined.img` than the committed generator does.
`origin/master` is `aec9531`; the generator change is not committed anywhere.
So the canonical tree builds `01e870ac`, while main's working tree builds
`b64f11d4` — same `git HEAD`, different image.

## Why it is the check-sync class

An uncommitted generator means **the image cannot be rebuilt from the tree**:

- `make desk-hashes` prints a hash that matches no committed state — the
  provenance it exists to give (trip cards point at it) is void.
- `check-sync` cannot mean "the tree is the artifact" when the artifact is
  produced by a generator the tree doesn't contain.
- "It passed this morning" cites `17e7da0f` — bytes that no longer exist and
  that no one can rebuild from any commit.

A `make test` green on an unreproducible image proves nothing about the
committed tree. So **no `make test` green is claimable** — not for the
kill-by-PID task, not for anything — until the generator is in the tree.

## Fix

Commit (or stash with a tag) `tools/write-catalog.py` before any image-hash
or `make test` claim. A generator is source; it belongs in the tree. Once
committed, every image hash becomes reproducible from a commit again.

## Status

OPEN. Owner (Lynx) to sequence with the session that holds the uncommitted
`write-catalog.py`. Not to be touched from the harness task (it is another
session's work-in-progress).

## Related

- `finding-harness-pkill-cross-worktree-2026-09-30.md` (the cross-session
  collisions that surfaced this)
- `TASK_HARNESS_KILL_BY_PID.md` (its H4 "make test green" gate is blocked by
  this)
- `make desk-hashes` / the desk-card hash provenance (all rest on
  reproducibility)
