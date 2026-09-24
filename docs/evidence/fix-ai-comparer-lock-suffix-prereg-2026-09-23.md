# (ai) The comparer routes an unknown by its sentinel, suffix or not: pre-registration (2026-09-23)

**Written before the change. An honesty item, not a coverage item**
(owner ruling). The row count and the denominator do not change; the only
thing that moves is which class 450 rows sit in. Outcomes go BELOW the line.

## The defect, read from source (rule 31)

`compare_operands.py:classify()` routes our side's sentinels by **exact
equality**: `om == 'INVALID'` (line 288) and `om == '???'` (line 290).
`dump_starts.c:129` appends `.LOCK` to any LOCK-prefixed decode, so an
unknown carrying LOCK prints `???.LOCK`, fails both tests, and falls
through to the mnemonic comparison. It is then published as "we named it
wrong" when the truth is "we did not name it at all."

**Measured on today's 16 dumps:** `.LOCK` is the **only** suffix that
appears on an unknown (450 `???.LOCK` against 67,242 bare `???`). No
`INVALID` row carries a suffix (1 bare `INVALID`). In the published
`mnemonic` class, the oracle has the 450 as CMPXCHG.LOCK 274, XADD.LOCK 168,
BTS.LOCK 5 and BTR.LOCK 3.

**A correction to the figure the ruling quoted.** The ruling predicted
`mnemonic` 535 → 85, from my report's 535. That 535 was a raw
`classify()` count. The comparer's own published class is **534**, because
today's `pseudo_op` class already moved the fixture's CMPEQPS row out of it.
So the prediction below is written against the published 534.

## The change

**One predicate:** strip the decoded-prefix suffix before testing the
sentinels, so that `???.X` routes as `???` and `INVALID.X` as `INVALID`.
The `INVALID` half has 0 rows today. It is included because it is the same
exposure on the other sentinel, and leaving it would re-open the defect the
first time a LOCK-prefixed refusal occurs. Nothing else changes: no alias,
no canonicaliser, and the alias and pseudo-op hashes are unchanged.

**The comparer has no suite in `make test`**, so its red is a **banked
control pair** (`measure/comparer-controls/`), run before and after, as the
pseudo-op controls were:
- ours `???.LOCK` against oracle `CMPXCHG.LOCK`: expected `undecoded`
  after, `mnemonic` before;
- ours `INVALID.LOCK`: expected `invalid_at_start` after, `mnemonic`
  before;
- ours bare `???`: `undecoded` both times;
- **a guard against over-absorption:** ours `NOP.LOCK` (a *named* wrong
  answer) against oracle `CMPXCHG.LOCK` stays `mnemonic` both times.

## Predictions (over the 16 differential inputs, today's dumps)

| # | prediction |
|---|---|
| H1 | `mnemonic` **534 → 84**; `undecoded` **5,284 → 5,734**; per input, the move equals that input's `???.LOCK` count (ACPI 161, usbxhci 111, storport 94, HDAudBus 33, pci 31, HP serial 10, i8042prt 6, disk 2, nmap 1, ReactOS serial 1) |
| H2 | **every other figure is identical**: `ghidra` 512,000, `denominator` 511,143, `operand_ok` 473,542, `mnem_ok` 506,135 (both classes are outside it), `invalid_at_start` 0, and every other class; score and decided unchanged; alias and pseudo-op hashes unchanged |
| H3 | exactly the 450 rows change class, `mnemonic` → `undecoded`, and **no row outside them changes class** |
| H4 | controls: before, rows 1 and 2 read `mnemonic`; after, `undecoded` and `invalid_at_start`; rows 3 and 4 identical both times |
| H5 | `make test` unchanged (410 tests, 12 reds); the comparer is not linked into any suite |

---

## Outcome

*(below this line, from the artefact only)*

**Inputs hashed:** `compare_operands.py` `7ff727bbc6428e47` (before
`5ec8fc7bf8493de6`). Alias hash `02101788edd2` and pseudo-op hash
`6ceb47ffeefb` are unchanged. Dumps: today's 16, unchanged, so only the
comparer differs.

| # | predicted | observed |
|---|---|---|
| H1 | `mnemonic` 534 → 84; `undecoded` 5,284 → 5,734; per-input moves as listed | **held exactly**: the only changed totals are `mnemonic` (534, 84) and `undecoded` (5,284, 5,734). Per input: ACPI 161, usbxhci 111, storport 94, HDAudBus 33, pci 31, HP serial 10, i8042prt 6, disk 2, nmap 1, ReactOS serial 1 |
| H2 | every other figure identical | **held**: `ghidra`, `denominator`, `operand_ok`, `mnem_ok`, `invalid_at_start` and every other class unchanged; score and decided unchanged on all 16 inputs |
| H3 | exactly the 450 change, `mnemonic` → `undecoded`; nothing else | **held**: 450 row transitions, all of that one kind, computed with both comparers imported side by side |
| H4 | controls: before, rows 1–2 `mnemonic`; after, `undecoded` / `invalid_at_start`; rows 3–4 unchanged | **held, row for row.** The `NOP.LOCK` guard stays `mnemonic`: a named wrong answer is not absorbed. Controls banked in `measure/comparer-controls/` with a README |
| H5 | `make test` unchanged | **held**: 410 tests across 27 suites, 12 reds |

**What the published error breakdown now says.** The `mnemonic` class,
"we named it and named it wrong", is **84 rows**, not 534. The other 450
were never names; they were unknowns wearing a prefix. The agreement score
itself never moved, because both classes are disagreements. **What was
wrong was the composition of the disagreement, and that is the part of the
instrument a reader uses to decide what to fix next.**
