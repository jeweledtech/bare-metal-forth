# FINDING — check-sync compares only `.fth`; private test scripts drifted silently (2026-10-04)

Recorded against master (`17c912f`). The drift itself is repaired (private
`dc043a8`); the gap in check-sync is not.

## Observed

`make check-sync` compares `forth/dict/<v>.fth` for each name in
`PAID_VOCABS` against the private repo, and nothing else. Private-owned test
scripts are outside its scope. On 2026-10-03:

- **11 private test scripts were stale.** The test-gui set (stub_dispatch,
  ui_core, gui_harvest, ui_parser, ui_events) and the test-meta set
  (metacompiler, meta_compile, meta_b6, meta_boot, meta_b6b, meta_does) in
  forthos-vocabularies predated the 2026-07-04 catalog-layout change
  (placement derived from the multi-block catalog). Copied fresh from the
  private repo into a worktree, they computed one-block-catalog `THRU` ranges
  and crashed the guest. test-gui failed 4/10 at its first fixture, and
  test-meta failed at its first load. The public working tree's copies
  passed (gui 6/6 fixtures, meta 6/6 suites).
- **One script was in neither repo.** `tests/test_fe_strip_cr.py`, the sixth
  test-gui fixture, existed only in one working tree.

`make check-sync` reported `OK: all paid files in sync` throughout.

## Repaired

Private `dc043a8` syncs the 11 scripts from the public working tree
(byte-identical) and adds `test_fe_strip_cr.py`.

## Owed (next task)

Extend check-sync to the private-owned test scripts, so a drifted or missing
copy fails the check rather than passing it.
