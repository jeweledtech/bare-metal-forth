# TASK: LOAD-VOCAB of a vocabulary already present adds nothing

Status: implemented on branch `vocab-dedup`; results in §5. Owner ruling
2026-10-09: fix the repeated vocabulary compilation as its own task, before
the write floor (parked: with it, test-install ran out of dictionary in its
test 38).

## 1. What the source did (catalog-resolver.fth, master 175d223)

- `LOAD-VOCAB` = `LOADING-RESET LOAD-VOCAB-INNER`. `LOAD-VOCAB-INNER`:
  `LOADING-PUSH` (a cycle guard: a name already on the in-progress stack is
  skipped; each name is popped when its load returns), then `CATALOG-FIND`.
  A hit in the in-memory registry (only vocabularies that call
  `CATALOG-REGISTER`) loads nothing; a hit in the block catalog runs
  `RESOLVE-DEPS` on the vocabulary's first block, then `THRU` over its range.
- Nothing asked whether the vocabulary was already in the dictionary. The
  embedded vocabularies are compiled at boot but are not in the registry, so
  a `LOAD-VOCAB` of one, direct or through a `REQUIRES:` line, compiled it
  again from blocks.
- No test, tool, Makefile line or vocabulary source loads an embedded
  vocabulary by name; they are reached only through `REQUIRES:` chains.

Three defects:

- **D1** `RESOLVE-DEPS` scanned each line over `start .. end + 40` (hex),
  i.e. the line and the next one, so a `REQUIRES:` was found twice and every
  dependency compiled twice.
- **D2** no already-present check: every dependency recompiled at all.
- **D3** only the first name on a `REQUIRES:` line loads (it stops at a space
  or `(`); later names never load. Harmless today: every such later name is
  embedded. Queued (§7).

## 2. Fix (owner-approved)

- **D2** `LOAD-VOCAB-INNER`, after `LOADING-PUSH`: `VOCAB-PRESENT?` walks the
  FORTH chain from FORTH's LATEST cell (0x28048): a header matches when it
  is not hidden, its length and name match, and its code field equals
  DOVOC's (`' CATALOG-RESOLVER @`), so a non-vocabulary word of the same name
  never suppresses a load. Kernel FIND is not used (it reads the word buffer,
  not its argument). A match prints `<NAME> present, skipped`, pops the
  loading stack and exits.
- **D1** `RESOLVE-DEPS` scans `start .. end` of each line.

## 3. The test (tests/test_vocab_dedup.py)

Headers are counted directly: the dictionary region 0x30000-0x80000 is
dumped through the QEMU monitor (`pmemsave`) and a name counts only with its
length byte (not hidden), a plausible link cell, and a code field (the
aligned cell after the name; `create_` aligns the absolute address) pointing
into the kernel image. Each step also measures HERE and counts the
`<NAME> present, skipped` lines: each `REQUIRES:` must resolve exactly once.

- Public cases (always): PCI-ENUM again (embedded); FIRSTBOOT (block-loaded
  in both the full and the free build; four one-name `REQUIRES:` lines, all
  embedded in both builds); FIRSTBOOT again. (SETTINGS was the first choice
  and is wrong for this: the free build embeds it.)
- Private cases (only when the private vocabulary sources are in the tree,
  else `SKIPPED ... 8 private checks not run`, exit 0): AHCI again; SURVEYOR;
  SURVEYOR again; INSTALL (REQUIRES SURVEYOR); each finds its words.
- 15 checks with the private vocabularies, 7 without.
- Boot setup: an image argument, else `build/combined.img`, else (public
  clone, where `make combined` has no private sources) `bmforth-free.img` +
  `blocks.img` concatenated into the combined layout (block N at LBA
  225 + 2N). The image is copied before booting.

## 4. Red

Committed build (master 175d223 with the committed private tree).

First version (AHCI/SURVEYOR/INSTALL only), predictions written first:
**3/12**, the three predicted passes. Getting there took three corrections
to the instrument, all mine: the loader's own name copies (cycle-guard stack,
`REQUIRES:` parse buffer) passed as headers until a code-field check was
added; the code-field offset assumed headers start aligned; and two counted
word names were wrong. Header counts (clean):

| | boot | +AHCI | +SURVEYOR | +SURVEYOR again |
|---|---|---|---|---|
| AHCI-INIT (= AHCI) | 1 | 2 | 4 | 6 |
| PCI-ADDR (= PCI-ENUM) | 1 | 3 | 7 | 11 |
| PARTITION-MAP (= SURVEYOR) | 0 | 0 | 1 | 2 |
| HARDWARE, NTFS, FAT32 and a word of each | 1 | 1 | 1 | 1 |
| HERE delta | | +19,588 | +55,156 | +55,156 |

Then INSTALL: `DICT FULL`. Two candidates had been written down for the
SURVEYOR step: A (one more AHCI compilation, from my reading of
RESOLVE-DEPS) and B (two, inferred from HERE deltas). B held; the second
copy is D1, which accounts for every count (one AHCI load: PCI-ENUM x2; one
SURVEYOR load: AHCI x2, PCI-ENUM x4).

Final version (§3): **2/15**, as predicted (PASS: boot, FIRSTBOOT loads
once). FIRSTBOOT again alone added +68,828 bytes.

Predicted effect on test-install (from the deltas): SURVEYOR's own code
= 55,156 - 2 x 19,588 = 15,980 B; INSTALL REQUIRES SURVEYOR (x2 by D1), so
INSTALL's own = 126,664 (boot to after INSTALL) - 2 x 55,156 = 16,352 B;
with the fix the chain costs ~32 KB instead of ~127 KB, so test-install's
margin before its test 38 ~109,000 B (before: 15,108).

## 5. Results

- test_vocab_dedup.py, private vocabularies present: **15/15**; HERE after
  every load: 103,988 B below the compiled-code ceiling 0x7F800.
- Public worktree of master + this change (no private sources; `make free
  blocks write-catalog`): **7/7**, `SKIPPED: ... 8 private checks not run`,
  exit 0. The first public run failed FIRSTBOOT because the test booted
  `blocks.img` alone (blocks start at 225 + 2N only in the combined layout);
  fixed by concatenating.
- Final run, private vocabularies present (test `3e377fcb…`, image
  `5b375358…`): **15/15**.
- test-install, HERE before its test 38 (instrumented copy, `val('HERE @')`
  before each test header): **0x65674, margin 106,892 B** below 0x7F800
  (before: 0x7C4FC, 15,108 B; predicted ~109,000: the estimate left out the
  fix's own ~500 B in the embedded resolver, boot HERE 0x5BDD4 vs 0x5BBE0).
- test-meta in full, alone: exit 0, 1,886 s; all six fixtures full
  (26/26, 11/11, 21/21, 20/20, 17/17, 19/19).
- make -k test: only test-xhci red (MAKE_TEST_EXIT=2, 2,863 s); suite
  census 429 across 27 suites (baseline 429); check-sync OK.

## 6. Known limitation: partial loads

A vocabulary whose load stopped part-way (an error, `DICT FULL`) has its
VOCABULARY word, so a later `LOAD-VOCAB` now skips it. Not a new risk: a
failed load already leaves a broken dictionary, and reloading only compiled
duplicates on top. A completion marker is queued.

## 7. Queued

- **D3**, red case: a fixture vocabulary (in a test block image) whose one
  `REQUIRES:` line names two public, block-loaded vocabularies, e.g.
  `\ REQUIRES: SHUTDOWN FIRSTBOOT`; after loading it, the direct header count
  shows FIRSTBOOT 0 today; gate 1, each name resolved exactly once.
- Completion marker for partial loads (§6).
