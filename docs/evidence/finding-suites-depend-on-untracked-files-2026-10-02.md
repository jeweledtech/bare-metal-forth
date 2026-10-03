# FINDING — `make test` suites depend on files git does not carry; a fresh clone fails some and silently skips others (2026-10-02)

Recorded against master (`0209c1e`). Not fixed here. Owner to sequence.

## Observed

A git worktree has only tracked files, so it behaves like a fresh clone. In two
of them (`harness-killbypid` at `5f383cc`, master at `0209c1e`),
`make -k test` and a rerun of the affected targets gave identical results on
both trees:

| Suite | Result | Missing input (ignore rule) | Where it exists |
|---|---|---|---|
| `test-doc-drift` | **FAIL 49/50**: gate A, "zero menuentry blocks found in any scanned doc" | `docs/TASK_INSTALL_BOOT_ENTRY.md` (`.gitignore:145` `docs/TASK_*.md`), `docs/superpowers/specs/2026-08-05-g6-chain-design.md` (`.gitignore:154`) | main checkout only |
| `test-translator` | **Error 3**: `tools/translator/Makefile not present` | `tools/translator/` (`.gitignore:78`) | private repo; main checkout |
| `test-pipeline` | **Error 2**: `can't open file tests/test_pipeline_integration.py` | `tests/test_pipeline_integration.py` (`.gitignore:105`) | main checkout only |
| `test-gui` | **exit 0, 0 of 6 tests ran** | `tests/test_{stub_dispatch,ui_core,gui_harvest,ui_parser,ui_events,fe_strip_cr}.py` (`.gitignore:63-67,74`) | main checkout only |
| `check-sync` | **exit 0, skipped**: "Private vocab repo not present … skipping sync check" | `../forthos-vocabularies` | sibling checkout |

`test-doc-drift` detail: the only scanned docs that contain a
`menuentry "ForthOS (installed to disk)"` block are the two ignored ones (2
blocks each). The two tracked docs it scans, `README.md` and
`tools/pxe/RUNBOOK-G6.md`, have 0. The gate's message blames a stale regex or
list. The real cause is that the files are not in git.

## Two shapes, one mechanism

1. **Loud:** doc-drift, translator and pipeline fail, so `MAKE_TEST_EXIT` is
   non-zero in any fresh clone, whatever the code does.
2. **Silent:** `test-gui` loops over its six scripts with
   `if [ ! -f tests/$$test.py ]; then continue; fi` and exits 0 having measured
   nothing. `check-sync` prints a skip and exits 0. Both are a zero-measured
   result printed like a pass.

## Build inputs: same mechanism, plus a stale-catalog trap

The 30 vocabularies that `.gitignore` excludes under `forth/dict/` are build
inputs. A fresh clone cannot build the image:
`make: *** No rule to make target 'forth/dict/ahci.fth', needed by 'build/embedded.bin'`.

Observed in this session (an operator step, recorded because the trap is
general): after that failed build had already written `build/blocks.img`, the
30 files were copied in with `cp -p`, which kept their older mtimes. Make
treated `blocks.img` as up to date and built `combined.img` (`352a87d8…`) on a
catalog **without** the copied vocabularies: no AHCI, and FIRSTBOOT placed at
294–326. `test_firstboot.py` loaded 529–561 (the full-catalog placement), and
the guest died: `FAIL 2: FIRSTBOOT blocks load`, `BrokenPipeError`. A clean
rebuild gave `52aae44b…`, the same as the other tree, and firstboot passed
38/38 + 38/38.
So an image can be built from a catalog that is missing vocabularies, with no
warning.

## Not fixed

For the owner: decide per suite whether it belongs in the public `make test`.
Each silent skip should print as a skip, distinct from a pass, and fail where a
pass is claimed. Make the catalog depend on the set of vocabulary files, not
only their mtimes.

## Related

- `finding-image-not-reproducible-2026-10-02.md` (same "tree is not the
  artifact" class)
- `TASK_HARNESS_KILL_BY_PID.md` §7 (verification traps)
