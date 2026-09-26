# (bw) (bt)'s lines are not block-safe: the red (2026-09-25)

**Written before any fix. The design is the owner's**, so no fix is
pre-registered yet. Outcomes go BELOW the line.

**Found by** (bu)'s first build: its U3 failure was a line past column 64.
Measuring (bt)'s own lines then showed the same class. Block loading
truncates a line past column 64 (the project's standing constraint;
`line_length_block_safe` checks it on four fixtures, and none of them has
a recorded access).

**Counted** (build `cfa43f46783de0ec`, the 10 drivers (bt) moved,
`-t forth -S`). Every line (bt) emits was measured: the registers header,
the `( base -- x )` accessors, and the map and access lines.
- **4 lines are over 64:** 83, 83, 83 and 84 characters. **All four are
  `\ map … walk stopped at 0x…` lines**: Dell `hdaudbus` (×2), Newer ASUS
  `errdev` and Older ASUS `fvevol`.
- **None** of the 10 drivers had a long line before (bt).
- **The format has no margin.** The longest line that fits is exactly 64:
  `\ registers of the region mapped at 0x1C00BA329, parked at 0x270`
  (`fvevol`). The HP access line `… -> HDAUDBUS-R58+14-W@` is 63. A longer
  vocabulary name, park or offset would cross the limit.

**The red:** `bw_RED_access_words_block_safe` (`test_mmio_consumer.c`).
Every (bt) line in Dell `hdaudbus`, Newer ASUS `errdev` and Older ASUS
`fvevol` must be ≤ 64. **Before any fix it XFAILs on exactly the 4 lines
above.**

**For the owner** (not taken):
- The four fail only on `walk stopped`, which could move to its own line.
  That alone would not give the margin back.
- A length-guaranteed format would shorten the map, access and header
  lines, for example by dropping the `0x` prefixes or the API name. That
  **changes the text (bt)'s red pinned for HP HDAudBus**, so it is a
  ruling on (bt)'s format, not a local fix.

## Ruling (owner, 2026-09-25) and the fix, pre-registered before it is built

**Ruling:** put `walk stopped` on its own comment line. The check covers
**all 10** drivers (bt) moved, not only the beep fixture. There is no
guaranteed-length reformat, and the 94 older long lines become their own
letter later.

**The red is restated to that scope.** It checks all 10 drivers, and its
line matcher also takes the new `    \ walk stopped ` line. Before the fix
it still XFAILs on **exactly the same 4 lines**.

**The design:** a map line whose walk stopped becomes two lines:
`    \ map 0x<call> (<api>), <park>`, then `    \ walk stopped at
0x<a>`. Nothing else changes.

**The exact after-state, predicted as text** (`bw_predict.py`, from build
`cfa43f46783de0ec`'s 1,338 outputs):
- **3 files move** (Dell `hdaudbus`, Newer ASUS `errdev`, Older ASUS
  `fvevol`), with **4 lines split**.
- The longest (bt) line is then **64**, `fvevol`'s registers header,
  which does not change. **None is over 64.**
- The per-file table's sha256 is **`bbecec16ba110378…`**.

| # | prediction |
|---|---|
| W1 | the gate fires on exactly `bw_RED_access_words_block_safe`; tests stay 427; reds 13 → 12 |
| W2 | 1,338 of 1,338 outputs equal `bw_pred.tsv`; 3 moved |
| W3 | read from the **post-retirement** `test-all`: exit 0, 427 tests, 12 reds, every `line_length_block_safe` passing; `-t report` identical on 1,338 |

---

## Outcome

*(below this line, from the artefact only)*

**Inputs hashed:** `forth_codegen.c` `7f5a39b56ebbc014`,
`test_mmio_consumer.c` `15575a21d0d90319`, and build `bin/translator`
`da984e6aa401b953`.

| # | observed |
|---|---|
| W1 | **held:** the gate fired on exactly `bw_RED_access_words_block_safe` (`fix-bw-xpass-gate-2026-09-25.log`) |
| W2 | **held:** 1,338 of 1,338 outputs equal `bw_pred.tsv`; 3 moved |
| W3 | **held**, read from the post-retirement `test-all`: exit 0, 427 tests across 27 suites, 12 reds, the union matches, all 4 `line_length_block_safe` checks pass; `-t report` identical on 1,338 |

**(bw) is closed.** Every line (bt) emits, on all 10 drivers it touches,
is at most 64 characters. The longest is exactly 64, so the format still
has no margin, as recorded above.
