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

---

## Outcome

*(below this line, from the artefact only)*
