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
