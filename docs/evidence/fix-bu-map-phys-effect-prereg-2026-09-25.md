# (bu) MAP-PHYS stack effect: pre-registration (2026-09-25)

**Written before the fix.** Owner ruling 2026-09-25: *"Emit ( phys size
-- virt ) and say in the emitted comment that the Windows protection
argument is dropped. Own red."* Outcomes go BELOW the line.

**The defect.** `SEM_API_TABLE` gives both `MmMapIoSpace` and
`MmMapIoSpaceEx` 3 arguments and 1 return, both as `MAP-PHYS`
(`semantic.c:56,60`). `stack_effect_for_hal` (`forth_codegen.c`) has no
3-argument case, so it falls through to `( -- )`.

**One wording change to the ruling, flagged here.** The third Windows
argument is **not** always the protection:
- `MmMapIoSpaceEx(PhysicalAddress, NumberOfBytes, Protect)`
- `MmMapIoSpace(PhysicalAddress, NumberOfBytes, CacheType)`

These are the WDK signatures, cited, not measured. Both map to `MAP-PHYS`,
and the codegen sees only the Forth word. So the comment names both
possibilities: **`drops Windows arg 3 (protect / cache type)`**. If the
owner wants the API told apart, that is a bridge field, and is not
taken here.

**The design.** An explicit `MAP-PHYS` case returns `( phys size -- virt )`,
and the note is appended at the two places a HAL call is emitted:
- **Single-call word:** `: <NAME>  ( phys size -- virt )  \ drops Windows
  arg 3 (protect / cache type)`. The body `    MAP-PHYS` is unchanged.
- **Multi-call line:** `    MAP-PHYS  \ ( phys size -- virt ) drops
  Windows arg 3 (protect / cache type)`.
- Words with recorded accesses already drop their MAP-PHYS calls, since
  (bt). **Named, not taken:** `UNMAP-PHYS` prints the generic
  `( x1 x2 -- )`.

**Counted from the input** (build `5b813601891fa1f0`, `-t forth -S`,
1,338 inputs):
- **212** single-call words, each with header `( -- )` and body exactly
  `    MAP-PHYS`;
- **302** multi-call lines, exactly `    MAP-PHYS  \ ( -- )`;
- **232** files contain one or the other;
- no other `MAP-PHYS` text outside the REQUIRES header lists, which this
  change does not touch.

**The exact after-state is predicted for every file.** The two rewrites
above, applied to today's outputs as text (`predict.py`, independent of
the code), give a per-file sha256 table. That table's own sha256 is
**`a6f7995cc642fe5b…`**. It predicts **232 moved and 1,106 unchanged**.

**The red:** `bu_RED_map_phys_stack_effect`, in `test_mmio_consumer.c`.
- **i8042prt** `MMIO-FN-1C0012A70` (stage 1's function, single-call):
  header `: MMIO-FN-1C0012A70  ( phys size -- virt )  \ drops Windows arg
  3 (protect / cache type)`.
- **ACPI** `MMIO-FN-1C00B0844` (multi-call): both of its MAP-PHYS lines
  read `    MAP-PHYS  \ ( phys size -- virt ) drops Windows arg 3
  (protect / cache type)`.

| # | prediction |
|---|---|
| U1 | the gate fires on **exactly** `bu_RED_map_phys_stack_effect`; tests 425 → 426; reds 12 → 13 → 12 |
| U2 | every one of the 1,338 `-t forth` outputs equals its predicted sha256: **232 moved, 1,106 byte-identical** |
| U3 | nothing else moves: `-t report` is identical on 1,338 (this is a codegen change); every other test is unchanged |

---

## Outcome

*(below this line, from the artefact only)*

### First build (`8e4e1bfbdfaaedc4`): U1 and U2 held, U3 failed

| # | observed |
|---|---|
| U1 | **held:** the gate fired on exactly `bu_RED_map_phys_stack_effect` (`fix-bu-xpass-gate-2026-09-25.log`) |
| U2 | **held:** 1,338 of 1,338 outputs equal their predicted sha256; 232 moved |
| U3 | **FAILED.** `-t report` was identical on 1,338, but **another test moved**. After the red was retired, `test-all` reached `test_beep_validation`, which the gate run never reached because it stopped at the XPASS: `line_length_block_safe FAIL: line 76 is 84 chars (max 64): : MMIO-FN-11879  ( phys size -- virt )  …` |

**The design broke a product constraint I did not read.** Block loading
truncates a line past column 64. The single-call header with its note ran
to 84 characters.

**The same measurement found a defect in (bt), which is closed:**
- (bt)'s `\ map … walk stopped at 0x…` lines are **over 64 characters**:
  **4 lines**, in Dell `hdaudbus` (×2), Newer ASUS `errdev` and Older ASUS
  `fvevol`. **None** of the 10 drivers (bt) moved had a long line before
  it.
- No test reads them: the only line-length check is on the beep fixture.
- **Minted (bw).** It gets its own red, after (bu) closes.
- **Named, not taken:** 94 long lines existed before both letters. They
  are StorPort and IALPSS helper names and STRIP lines in 27 files, an
  older and separate class.

### Corrective (pre-registered here, before it was built)

**The design, restated in full:**
- MAP-PHYS is `( phys size -- virt )`.
- The note moves to **its own comment line**: `    \ Windows arg 3
  (protect / cache type) dropped`. That is **50 characters**, whatever the
  word's name.
- **Single-call:** `: <NAME>  ( phys size -- virt )`, then the note line,
  then `    MAP-PHYS`.
- **Multi-call:** `    MAP-PHYS  \ ( phys size -- virt )` followed by the
  note line, for each call.

**The red is restated to this text.** The committed red (`c813d8e`)
asserts the first design's one-line note. It goes back into
`xfail_names[]` with the new expected text before the corrective is
built, and this edit is the only change to it.

**The exact after-state, predicted as text** (`bu_predict2.py`, from the
same inputs as U2): **232 moved**, and the per-file table's sha256 is
**`62d2c00ac16d276e…`**. The longest new or changed line is **50** and
**none is over 64**.

| # | prediction |
|---|---|
| C1 | the gate fires on exactly `bu_RED_map_phys_stack_effect` again |
| C2 | 1,338 of 1,338 outputs equal `bu_pred2.tsv`; 232 moved |
| C3 | `test-all` exits 0 **including** `line_length_block_safe`; 426 tests, 12 reds after retiring; `-t report` identical on 1,338 |

### Corrective outcome

**Inputs hashed:** `forth_codegen.c` `d3dd62bc830b353a`,
`test_mmio_consumer.c` `c582a5c3f3f78f66`, and build `bin/translator`
`cfa43f46783de0ec`.

| # | observed |
|---|---|
| C1 | **held:** the gate fired on exactly `bu_RED_map_phys_stack_effect` (`fix-bu-corrective-xpass-gate-2026-09-25.log`) |
| C2 | **held:** 1,338 of 1,338 outputs equal `bu_pred2.tsv`; 232 moved; `-t report` identical on 1,338 |
| C3 | **held:** `test-all` exits 0 with 426 tests across 27 suites and 12 reds; the union matches. All four `line_length_block_safe` checks pass, including beep's (120 lines, all ≤ 64) |

**(bu) is closed.** `MAP-PHYS` prints `( phys size -- virt )`, and a
line of its own says the Windows third argument (protection or cache type)
is dropped. The rule taken from this: **a gate run that stops at the
XPASS has not run the later suites. U3-type predictions are read from
the post-retirement `test-all`, never from the gate run.**
