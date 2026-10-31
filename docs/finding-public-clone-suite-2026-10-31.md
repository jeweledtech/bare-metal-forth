# Finding: in a public clone, `make -k test` fails 55 of 71 targets that should skip or run

Date: 2026-10-31. Status: recorded, not fixed. Found while measuring
Part B of the count-lines item (private TASK_TEST_COUNT_LINES).

## How it was measured

A worktree of public 4fa88ba with no private file in it (the ignored
private .fth, tests and tools absent) and PRIVATE_REPO absent at its
Makefile default; `make -k test`, exit 2, 891 lines. Then `make -n <t>`
for each of the 71 targets on the `test:` line, in the same worktree.

## Observed

**51 targets never start.** `make -n` stops each at `No rule to make
target 'forth/dict/ahci.fth'`. They need `$(IMAGE)` or `$(COMBINED)`,
built from build/embedded.bin, whose prerequisites are EMBED_VOCABS
(Makefile:51). Seven of those are private and have no rule here: ahci,
rtl8168, ntfs, auto-detect, fat32, file-editor-disk, file-stream (log
lines 289-295). Under `-k`, make drops each target with no line of its
own and ends `Target 'test' not remade because of errors.` Among them is
every test with a public-mode branch written for this case
(interp_abort and reload_vocab's free-kernel fallback, mirror and
pad_move's SKIPPED cases, vocab_dedup's public mode, phys_refuse and
read_flags' SKIPPED line). Those branches are present but unreachable
from `make test` in a public clone.

The 51: test-xhci test-pci-bar test-firstboot test-block-reload
test-blk-evict test-install test-log-harness test-log-harness-nic
test-log-restore test-log-validation test-log-send test-dlg2form
test-rtl8168-cksum test-stack-floor test-vga-wrap test-reload-vocab
test-load-vocab test-resolve-deps test-vbr test-uefi-boot
test-uefi-netboot test-uefi2-gdt test-carrier-write-safe test-memdisk
test-g6 test-mirror test-interp-abort test-pad-move test-hal test-hal-net
test-hal-match test-hal-match-hp test-network test-vocabs test-gui
test-integration test-file-stream test-pipeline-e2e test-net-flush-lf
test-console-band test-window-focus test-search-order test-abort-routes
test-vocab-dedup test-phys-refuse test-window-forms test-read-flags
test-double-cell test-forth83 test-arm64-boot test-meta-b6b.

**20 start. 4 of them fail:**

| target | public clone | cause |
|---|---|---|
| test-phys-alloc | Passed: 29/47, exit 1 | runs on build/bmforth-free.img; Phase 1 pins the AHCI and RTL8168 DMA buffers (CL-BUF 0x103000 ... MFT-BUF 0x109000) and the boot audit's 7 live allocations, which only the full kernel's embedded private drivers make (observed: each `got None`) |
| test-doc-drift | Passed: 54/55, exit 1 | gate A ("found at least one doc copy to check") finds 0: two of its four DOCS_TO_SCAN (tests/test_doc_drift.py:84), docs/TASK_INSTALL_BOOT_ENTRY.md and docs/superpowers/specs/2026-08-05-g6-chain-design.md, are untracked: on this disk only, in no repo; the two tracked ones hold no installed menuentry |
| test-port-inventory | 66 recipes, 86 listen entries; 2 problem(s), exit 1 | `UNGUARDED` for test-log-decode-layout and test-pipeline (their scripts are private and absent). Observed; the mechanism (why their absence reads as an unguarded QEMU) was not read |
| test-translator | exit 3 | prints "This is not a broken checkout" and fails the target: its own words say skip, its exit says fail |

The other 16 pass or skip: lint, check-coverage, test-smoke 7/7,
test-loops 5/5, test-abort 20/20, test-dict-bounds 24/24, test-pci-typing
18/18, test-squote-laydown 63/63, test-grub-cfg 31/31, test-make-wiring
190/190, test-kill-traps 64/64, test-free-boot 3/3; SKIPPED:
test-log-decode-layout, test-pipeline (the 10-30 form, naming its mode),
check-sync; test-survey prints its NOT RUN banner and exits 0.

## Reasoned, not observed

In the private tree test-doc-drift passes only because the two untracked
docs exist on this disk: the defect class TASK_PIPELINE_SKIPS found for
the survey (a wired test reads a file no repo holds).

## When it is taken up

Owner's call. The shape of it: a public clone's `make test` either builds
a public image for those targets (free embedded set) or each target
skips, naming its mode; the four failing targets skip or pin per mode.
A pre-registered red first: this measurement, made a check.
