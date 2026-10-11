# TASK: RELOAD-VOCAB, recompile an edited vocabulary in place

Status: FIXED, uncommitted (2026-10-10); results in §7. Owner rulings
2026-10-10: plan and red first; Q1 P1, Q2 embed, Q3 restore; the
freed-region pointer check (§6).

## 1. Why

Since the de-dup task (`c152f36`), `LOAD-VOCAB` of a vocabulary already in
the dictionary prints `<NAME> present, skipped` and compiles nothing. That
is right for dependencies, but it removes the edit-and-reload loop: after
editing a vocabulary's blocks, `LOAD-VOCAB` keeps the old code. Reloading
has to be asked for explicitly.

## 2. What the source gives (read, not run)

- A vocabulary word is a header in the chain of whatever was CURRENT when
  `VOCABULARY` ran (FORTH, for every vocabulary in the tree), then a code
  field DOVOC and one cell, the vocabulary's own LATEST.
- The search order (`VAR_SEARCH_ORDER`, 8 cells, depth at 0x28040) and
  CURRENT (0x28044) hold addresses of LATEST cells. `ONLY` resets both to
  FORTH's cell 0x28048. `USING X` pushes X's cell.
- There is no FORGET or MARKER. Undoing a definition means setting HERE and
  every LATEST cell that points at or above it back by hand.
- `VOCAB-PRESENT?` (catalog-resolver) already finds a vocabulary's header in
  the FORTH chain by name and code field.

## 3. Design (for the owner)

`S" NAME" RELOAD-VOCAB`:

1. Find NAME's vocabulary header V (as `VOCAB-PRESENT?`). Not present:
   behave as `LOAD-VOCAB`.
2. **Refuse** unless nothing was compiled after the vocabulary except its
   own words: FORTH's LATEST must be V itself, and every other vocabulary's
   LATEST (each DOVOC word in the FORTH chain) must be below V. Print
   `NAME: RELOAD-VOCAB refused, <word> compiled after it` and change
   nothing.
3. Take NAME's LATEST cell (V's code field + 4) out of the search order and
   out of CURRENT (FORTH in its place), remembering where it was.
4. Truncate: FORTH LATEST := V's link; HERE := V.
5. `LOAD-VOCAB` NAME (dependencies are below V and stay; they print
   `present, skipped`).
6. The new VOCABULARY word lands at V again (same HERE, same name), so its
   LATEST cell has the same address: put the remembered search-order and
   CURRENT entries back. If the load failed or the cell moved, leave FORTH
   and say so.

Owner decisions:

- **Q1 policy.** P1 (above): refuse unless it is the newest. P2: FORGET
  semantics, everything compiled after it goes too, with a list of what was
  dropped. Recommendation: P1. P2 silently breaks whatever was built on
  top, and the refusal names the word in the way.
- **Q2 placement.** The placement rule says block-load words nobody calls
  at boot. But under P1 a block-loaded RELOAD-VOCAB defeats itself: loading
  its own vocabulary after NAME makes NAME no longer the newest. So:
  embed it in catalog-resolver, next to `LOAD-VOCAB` (embedded stream cost
  to be measured at build; 6,124 B of pad left). Recommendation: embed.
- **Q3 search order.** Restore it as in step 6 (recommended), or drop NAME
  from it and leave `USING` to the user.

Limits (stated, not handled): a vocabulary defined while CURRENT is not
FORTH is not found; data allotted after NAME's last word with no header
would be dropped; the partial-load case of the de-dup task (§6 there) is
exactly what RELOAD-VOCAB repairs when NAME is the newest.

## 4. Red (tests/test_reload_vocab.py)

The fixture `RV-FIX` (`VOCABULARY RV-FIX RV-FIX DEFINITIONS 1 CONSTANT RV
FORTH DEFINITIONS`) goes into a copy of forth/dict, packed with
write-catalog into a copy of blocks.img behind the current kernel, all
under `build/reload-vocab.d/`. The host patches its `1` to `2` in the IDE
image. Headers are counted directly (pmemsave), as in test_vocab_dedup.

Checks, with predictions on today's image (`5fdfb315…` kernel), written
before the run:

1. first load: `RV .` = 1, one RV-FIX, one RV: **PASS**
2. control: after `EMPTY-BUFFERS` the guest reads the edited byte: **PASS**
3. `LOAD-VOCAB` after the edit: `RV-FIX present, skipped`, HERE unchanged:
   **PASS** (D2; stays a pass after the fix)
4. `RELOAD-VOCAB` defined: **FAIL**
5. after `RELOAD-VOCAB`: `RV .` = 2, one RV-FIX, one RV, HERE equal to
   after the first load: **FAIL**
6. with `: AFTER-RV RV ;` compiled after it: refused with a message, HERE
   unchanged, AFTER-RV intact: **FAIL**
7. DEPTH 0: **PASS** (the undefined word's abort clears the stack)

Predicted: **4/7**.

## 5. Red result

### First run: 3/7, prediction MISSED on check 7

Checks 1-3 PASS and 4-6 FAIL as predicted; check 7 FAILED (DEPTH 3). Two
causes, both mine: check 4 sent `' RELOAD-VOCAB 0<> .`, and `'` of an
undefined word pushes nothing, so `0<>` read one cell below the empty
stack (it printed -1; DEPTH -1), the underflow class of bug #35, which an
instrument must not do; and an undefined word does not clear the stack,
so each `S" RV-FIX" RELOAD-VOCAB` left its two cells (-1 + 2 + 2 = 3).
Check 4 now counts RELOAD-VOCAB headers in the dump instead.

Re-registered, before the rerun: checks 1-3 PASS, 4-7 FAIL, **3/7**, with
DEPTH **4** (two leftover `S"` pairs), which observes the second cause
directly.

### Rerun: 3/7, as re-registered

Kernel `f45e5c24…` (build/bmforth.img of `5fdfb315…`), fixture image
`4bb03b6c…`, test `3ce1f759…`, catalog-resolver `8127352f…`. RV-FIX at
block 1118. Checks 1-3 PASS; 4 FAIL (0 RELOAD-VOCAB headers); 5 FAIL (`RV`
still 1 after `RELOAD-VOCAB ?`; one RV-FIX, one RV); 6 FAIL (no refusal:
`RELOAD-VOCAB ?`); 7 FAIL, DEPTH **4**. No QEMU left.

Two of today's PASSes are vacuous for the gate and say so in their
conditions: check 5's HERE equality holds because nothing happened, which
is why it is joined with `RV . = 2`; check 6's "HERE unchanged" likewise
is joined with the refusal message.

## 6. Owner rulings (2026-10-10) and the pointer check

Q1 P1 (refuse unless NAME is the newest; name the blocker). Q2 embed in
catalog-resolver; report stream and pad cost against 6,124 B. Q3 restore
the search order automatically. Added: before cutting, refuse if any known
global pointer or IDT entry points into the region to be freed,
[NAME's header, HERE); name it in the refusal.

### 6.1 Every cell checked (read from the source)

A value v blocks the reload when V <= v < HERE (V = NAME's header).

Kernel (src/kernel/forth.asm):

1. `BLK_WRITE_VEC` 0x2809C (`BLK-WRITER@`), executed by `blk_flush_one`.
2. `BLK_READ_VEC` 0x280A0 (`BLK-READER@`), executed by `PBLK-READ`.
3. `ISR_HOOK_TABLE` 0x29C00, 16 cells, written by HARDWARE's
   `IRQ-CONNECT` (the kernel does not dispatch through it yet; checked).
4. IDT 0x29400, 256 entries x 8 B; handler = bytes 0-1 | bytes 6-7 << 16.
5. KEY, EMIT and every other kernel word are direct DEFCODEs: the kernel
   has no other execution vector. The kernel's `execute_xt` callers are
   exactly 1 and 2.
6. Search order and CURRENT hold LATEST-cell addresses: handled by
   step 3/6 of §3 (removed, restored), not a refusal.

catalog-resolver (embedded):

7. Loading stack: `LOADING-DEPTH` must be 0 (no load in progress);
   `LOADING-NAMES` holds name copies, no pointers.
8. In-memory catalog registry: `CR-ADDRS` cells 0 .. `CR-COUNT`-1.
9. `'RESOLVE-DEPS`.

Other vocabularies, looked up by name at run time (catalog-resolver is
embedded before them); an absent vocabulary has nothing to check:

10. FILE-STREAM `'FILE-SINK` (executed by file-stream).
11. FILE-EDITOR `FE-SAVE-XT`, `FE-OPEN-XT` (executed by
    file-editor-core).
12. GUI-HARVEST widget registry: `REG-XTS` cells 0 .. `REG-COUNT`-1.
13. UI-CORE widget table: the XT field (`WTO-XT`) of entries 0 ..
    `WT-COUNT`-1 (executed by UI-EVENTS).
14. INSTALL `SEC-WRITE-VEC`, `SEC-READ-VEC` (block-loaded).
15. FIRSTBOOT `WZ-SPACE-XT` (block-loaded).

Not checked: a vector inside NAME itself (freed with it); vectors in
vocabularies loaded after NAME (P1 already refuses: they are newer).

### 6.2 Red cases added

- Fixture RV-VEC (one block): `BLK-WRITER@ CONSTANT RV-OLDW`,
  `: RV-W 2DROP 1 ;`, `' RV-W BLK-WRITER!`. Its RELOAD-VOCAB must refuse
  naming the block-writer vector, leave HERE unchanged and RV-VEC intact
  (one RV-W, the vector still RV-W). After `RV-OLDW BLK-WRITER!` the same
  reload must go through (the refusal was the vector, not P1).
- DEPTH 0 after each refusal, and after a reload.

### 6.3 Re-registered prediction (before the run)

| # | check | today |
|---|---|---|
| 1 | first load: RV 1, one RV-FIX, one RV | PASS |
| 2 | control: edited block visible | PASS |
| 3 | LOAD-VOCAB after edit: skipped, HERE unchanged | PASS |
| 4 | RELOAD-VOCAB defined | FAIL |
| 5 | reload: RV 2, one RV-FIX, one RV, HERE as before | FAIL |
| 6 | DEPTH 0 after the reload | FAIL |
| 7 | AFTER-RV compiled after: refused naming AFTER-RV, HERE same, AFTER-RV intact | FAIL |
| 8 | DEPTH 0 after that refusal | FAIL |
| 9 | RV-VEC loads; the writer vector is RV-W (control) | PASS |
| 10 | RV-VEC reload refused naming the block-writer vector, HERE same, intact | FAIL |
| 11 | DEPTH 0 after that refusal | FAIL |
| 12 | writer restored: RV-VEC reload goes through, HERE same, one RV-W | FAIL |
| 13 | final DEPTH 0 | FAIL |

Predicted: **4/13**.

### 6.4 Red result: 4/13, as predicted

Test `3d47600f…`, fixture image `060765f4…`, kernel `f45e5c24…`. PASS 1,
2, 3, 9; FAIL 4-8 and 10-13 (`RELOAD-VOCAB ?`; DEPTH grows by 2 per call:
2, 4, 6, 8). No QEMU left.

## 7. Fix and results

catalog-resolver.fth:

- `VOCAB-PRESENT?` now returns the vocabulary's header (nonzero) instead
  of TRUE; its one caller tests it with IF, unchanged.
- New (CATALOG-RESOLVER vocabulary): `RL-IN?`, `RL-BLOCK` (first blocker
  wins), `RL-CHK`, `RL-NAMEOF`, `HDR-FIND` (a name in one chain),
  `VOC-WORD` / `VOC-CONST` (a word of a vocabulary, found at run time),
  `RL-VAR`, `RL-TABLE`, `RL-W@`, `RL-IDT`, `RL-WIDGETS`, `RL-VECTORS` (the
  cells of §6.1), `RL-NEWEST` (P1), `RL-SAY`, `RL-UNPLUG` / `RL-REPLUG`
  (search order and CURRENT, §3 steps 3 and 6).
- New in FORTH: `RELOAD-VOCAB ( addr len -- )`. It copies the name into
  its own buffer first (an interpret-mode `S"` string may sit at HERE,
  which the reload frees), and consumes its arguments on every path.
- Refusal text, as printed by the guest:
  `RV-FIX: RELOAD-VOCAB refused, AFTER-RV compiled after it` and
  `RV-VEC: RELOAD-VOCAB refused, BLK-WRITER@ vector points into it`.
- Lint: 0 errors; 45 warnings (26 before), the 19 new ones the existing
  base-tracking note on the hex system-variable literals.

**Cost (Q2):** token stream 89,679 -> **92,925 B (+3,246)**; kernel
content 108,564 -> 111,809 of 114,688; **pad left 6,124 -> 2,879 B**.

**Reload test: 13/13** (catalog-resolver `4ad21de5…`, kernel
`3a0eb957…`, image `c33f0d3a…`, test `a6e50453…`).

**Gates** (image `c33f0d3a…`): test_vocab_dedup.py **15/15**; make
test-install exit 0, 337 s, **454/454**; make -k test: **only test-xhci
red** (MAKE_TEST_EXIT=2, 2,863 s), kill traps 31/31, census 429 across 27
suites (baseline 429), check-sync OK. Extra, test-meta in full: exit 0,
1,905 s, all six counts unchanged; DICT MARGIN smallest **35,468 B**
(test_meta_boot; was 39,204), 35,492 in four, 62,652 in
test_metacompiler: the embedded code took 3,736 B of dictionary. The
Makefile comment above test-meta carries the new numbers. No QEMU left.
