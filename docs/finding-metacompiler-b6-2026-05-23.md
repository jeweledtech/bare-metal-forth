# Finding — Metacompiler test suite: 86/89, not 89/89 — 2026-05-23

**Type:** Findings record + open investigation. Captures the first live run of
the metacompiler test suite under `make test-meta`, which surfaced that the
recorded pass count was stale.

**Status of the harness:** `make test-meta` is wired and committed (commit
`test: wire metacompiler suite into make test-meta`). The target works
correctly — runs all 5 files sequentially, `set -e` fail-stops on the first
failure. The harness is done; this finding is about what its first run revealed.

---

## The number is 86/89, and the old 89 was never run

| Test file | Result | Status |
|---|---|---|
| `test_metacompiler.py` | 26/26 | green |
| `test_meta_compile.py` | 11/11 | green |
| `test_meta_b6.py` | **12/15** | 3 pre-existing failures |
| `test_meta_boot.py` | 20/20 | green |
| `test_meta_b6b.py` | 17/17 | green |
| **Total** | **86/89** | |

The MEMORY.md "89 pass" figure (15/15 for b6) was stale — it had never been
executed under the harness; it was a recorded claim. The completion audit
(2026-05-23) was explicit that it could not run the tests live due to a QEMU
conflict and that 89 came from MEMORY.md, not a run. The first live run
corrected it to 86/89.

**This is the third stale metacompiler claim this period.** First the "21 of 50
words" note (actually ~180 host / ~131 target, zero stubs). Then the "89 pass"
(actually 86). The pattern: the metacompiler's recorded state drifts from
reality, and until now nothing caught it automatically. That is precisely what
`make test-meta` now prevents — the value of the harness is not that it's green,
it's that it won't let the number drift silently again.

---

## The b6 failure — symptom and what passes

All 3 failures in `test_meta_b6` are one root cause: `META-COMPILE-X86 ?` — the
word is not found when the test calls it after `USING TARGET-X86`. The
symbol-count and META-SIZE checks cascade from that one not-found.

Verified pre-existing, not introduced by this work: re-running `test_meta_b6` at
its own default port 4590 (outside the harness) reproduces the same 3 failures.
So this is not a port-change artifact and not a harness bug.

What still passes inside b6: the 12 interactive self-hosting checks (arithmetic,
colon defs, IF/ELSE, BEGIN/UNTIL, DO/LOOP) all pass. META-TRANSFER works, the
kernel boots, interactive Forth runs. And `test_meta_b6b` (the harder
standalone-boot path) is a clean 17/17. So the *self-hosting capability* —
metacompiled kernel boots standalone and runs interactive Forth — is intact and
proven. What's broken is narrower: the `META-COMPILE-X86` invocation path in
this one test.

---

## The open question (do NOT assume the answer)

The failure is `META-COMPILE-X86` not found after `USING TARGET-X86`. There are
two very different explanations, and which one is true changes everything:

1. **Test bug.** The test's `USING`/`ALSO` setup doesn't put `TARGET-X86` in the
   search order correctly at the point it calls `META-COMPILE-X86`, or a silent
   `?` during the long `TARGET-X86` block load (1217–1307, 91 blocks) left the
   vocab incompletely loaded while the final `THRU` still reported `ok`. If so,
   it's a ~5-minute fix in the test.

2. **Metacompiler bug.** `META-COMPILE-X86` genuinely isn't visible after
   `USING TARGET-X86` the way it should be — a real search-order / vocabulary-
   visibility gap in the metacompiler. If so, it's more significant, and it
   matters directly for DOES>, which also depends on vocabulary context in
   `target-x86.fth`.

**The investigation's first job is to settle this fork before touching
anything.** The provisional read ("likely a search-order issue in the test") is
plausible but UNCONFIRMED — it has not been proven whether the bug is in the
test's invocation or the metacompiler's vocab handling. Given that two prior
metacompiler claims have already been wrong this period, do not let "probably
the test" harden into an assumption. Prove which one first.

---

## Resolution — 2026-05-24

**Root cause: BLOCKS_LBA_BASE offset applied to standalone blocks.img.**

The kernel hardcodes `BLOCKS_LBA_BASE = COMBINED_HEADER_SIZE / 512 = 225`
sectors. Every block read adds 225 to the LBA. This is correct for the
`combined.img` layout (boot + kernel + blocks on one disk — block 0 sits at
sector 225). But `test_meta_b6.py` was the only test using standalone
`blocks.img` on a separate IDE drive, where block 0 is at LBA 0. The +225
offset read 112.5 KB past the start every time, landing in the PCI-ENUM
region. All blocks returned identical wrong content, vocab definitions never
executed, and `USING TARGET-X86 → TARGET-X86 ?`.

**Evidence chain:**
1. Live `LIST` of blocks 0, 1, 501, 1217 from b6's image combo all returned
   PCI-ENUM code (SCAN-KNOWN, DEVICE-KNOWN?) — same content regardless of
   block number.
2. `BLOCKS_LBA_BASE` traced to `forth.asm` line 97:
   `BLOCKS_LBA_BASE equ COMBINED_HEADER_SIZE / BOOT_SECTOR_SIZE` = 225.
3. Every `ata_read_sector` call adds this base (lines 2330, 2453, 2531, 2593,
   4848).

**Fix:** Changed `test_meta_b6.py` to use `combined.img` + `combined-ide.img`
(matching the other 4 meta tests). Result: **15/15**, full suite **89/89**.

The underlying metacompiler was never broken. The 3 failures were a
test-harness image-layout inconsistency. The fix is local (test files are
gitignored per the open-core split, commit 4bbf6a2).

**Fork resolution:** Not a search-order bug. Not a metacompiler-code bug. A
block-addressing path mismatch specific to the standalone-blocks-on-IDE layout
that only b6 used. The metacompiler's actual state is 89/89 from a trusted
suite.

## Sequencing consequence

~~DOES> is gated behind this.~~ Resolved. DOES> Phase 0 can start from a
89/89 suite. The metacompiler's vocab handling is not implicated.
