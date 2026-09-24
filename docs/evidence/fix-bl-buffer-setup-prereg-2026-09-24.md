# (bl) the MDL routines leave the hardware block: pre-registration (2026-09-24)

**Written before the edit.** The owner confirmed the edit at 133 emptied
drivers (`bl-criterion-read-2026-09-24.md`). Outcomes go BELOW the line.

## The criterion: a standard created 2026-09-24, as the owner tightened it

> **"Hardware" means the function issues a hardware access:** it reads or
> writes a port, MMIO, a device register, or **a structure at a
> hardware-defined layout that the device itself consumes** (a descriptor
> ring, a command block, a doorbell record), where getting the bytes wrong
> breaks the device. **An MDL is OS bookkeeping.** The device never reads the
> MDL; it reads the buffer the MDL describes, and the physical addresses
> reach it through the DMA adapter, not through the MDL routine.
> **Participation is not access.**

**Recorded as tightened.** The owner's first wording, "*or a structure the
device itself reads*", could be read to pull MDLs back in, since an MDL
describes a buffer a device will DMA into. The owner tightened it after
seeing where it was ambiguous. This is the version that decides. Nobody
knows the original author's rule; this one is ours.

## The change

- A new scaffolding value, **`SEM_CAT_BUFFER_SETUP` (0x8C)**, report name
  `BUFFER_SETUP`, drop reason `BUFFER-SETUP`. It is **appended** to
  `SEM_SCAF_LIST`, since the order is frozen, append only. That makes **14
  of 16** entries. The header gets a line saying the ceiling is two away.
- `IoAllocateMdl`, `IoFreeMdl` and `MmBuildMdlForNonPagedPool` in
  `SEM_API_TABLE`: DMA → `BUFFER_SETUP`. Nothing else in the table changes.
  Their `forth_equiv` strings are left as they are; no reader uses a
  scaffolding entry's `forth_equiv` (`translator.c:192` reads it only for
  hardware categories).
- **The vocabulary hash changes.** Its readers: **0** in tests and scripts,
  **1** header comment (the precedence note, updated to the new hash) and
  **6** evidence documents. Per the owner's condition, **each of the 6 keeps
  `b48923e8…`** and gains: *frozen at `b48923e8…` until 2026-09-24; superseded
  by `<new>`*. They are made correct, not made current.

## The red

`sem_RED_bl_mdl_routines_are_buffer_setup` (`test_semantic.c`) fails today
with "an MDL routine still prints a hardware category". Pass state:
- all three print `BUFFER_SETUP` with `is_hardware` false;
- a function whose only call is `IoAllocateMdl` is not hardware, and its drop
  reason is `BUFFER-SETUP`.

## Predictions

**Replication**, from the dry run of this same edit (a scratch build,
`5e99e7af…`, with MEMORY_MGR standing in). These are **scored as a
replication, not as predictions**: the real edit must reproduce them.

| # | the dry run's figure |
|---|---|
| R1 | **433** drivers change buckets |
| R2 | hardware **−3,998**, scaffolding **+4,732**, unclassified **−734** |
| R3 | **133** drivers emptied of every hardware function |
| R4 | HP eight hardware **320 → 266**: disk 3 → 0, storport 85 → 59, usbxhci 58 → 33, the other five unchanged. **"317" was my error in `bl-criterion-read`**: it counted disk.sys alone. It is corrected there |

**Predictions the dry run never measured**, which are genuinely unknown:

| # | prediction | instrument |
|---|---|---|
| P1 | report bytes change on **exactly the 441** drivers that import any of the three names (pefile, from the bytes), and **881 are identical**. The import list's category string changes even where no bucket does | population report hashes |
| P2 | X1 **0** hex (BUFFER_SETUP has a name); X2 `import_family` unchanged **1,322 of 1,322**; X3 four-DLL (DLL, name, category, source) sets unchanged **1,322 of 1,322** (the three names are ntoskrnl imports) | same run |
| P3 | the three names' `category_source` **stays `vocabulary-uncited`**: the criterion is a created standard, not a citation | same run |
| P4 | park census: sites **12 / 172 / 171 / 184** unchanged, and **0 of 539** outcomes change (the park walk reads mapping calls, not other imports' categories) | census harness |
| P5 | stage 2: the HP eight reports' **`mapped_regions` sections byte-identical** (the 14 accesses unchanged) | extracted from the snapshot reports |
| P6 | snapshot: UIR **0 of 12**; dumps **0 of 16**; reports change on **exactly 3 of 12** (HP disk, storport, usbxhci) | snapshot |
| P7 | the gate fires on **exactly** `sem_RED_bl_mdl_routines_are_buffer_setup`; the domain guard prints **`[accepted=14]`**; `(bk)` stays red; 419 tests; reds 14 → 13 | suites |

**Independent checks: four.**
- The suites.
- The population report run, which carries R1–R4 and P1–P3 as one
  instrument.
- The census harness.
- The snapshot, with P5 extracted from its reports.

---

## Outcome

*(below this line, from the artefact only)*

**Inputs hashed:** `bin/translator` before `60df7c753af56625`, after
`3fc5a848860d4d25`, built from private `dfffb8c` (red `a3d0dfb`), mirror
identical. **Vocabulary extraction sha256 `cd4278dbe28353ec472e73f7cfb22a6fa6ad805c61dbca8b5737c5a191955453`**
(was `b48923e8…`). Readings are `bl-reports-post.tsv`,
`bl-park-census-post.json` and `bl-importers3.txt` in
`~/corpus/tools-2026-09-24/SHA256SUMS`. 0 empty outputs.

**Replication: exact.** The real edit's buckets equal the dry run's on
**1,322 of 1,322** drivers.

| # | dry run | real edit |
|---|---|---|
| R1 | 433 drivers change buckets | **433** |
| R2 | hw −3,998, scaf +4,732, uncl −734 | **−3,998, +4,732, −734** |
| R3 | 133 emptied | **133** |
| R4 | HP 320 → 266 | **320 → 266** |

**Predictions the dry run never measured: seven of seven held.**

| # | predicted | observed |
|---|---|---|
| P1 | bytes change on exactly the 441 importers; 881 identical | **held as an exact set**: the changed set **equals** the 441 importers; 0 non-importers changed |
| P2 | 0 hex; X2 and X3 unchanged | **0**; `import_family` **1,322 of 1,322**; four-DLL sets **1,322 of 1,322** |
| P3 | the three stay `vocabulary-uncited` | **held**: `BUFFER_SETUP`, `vocabulary-uncited`, `is_hardware` false (read on HP disk.sys) |
| P4 | census sites unchanged; 0 of 539 outcomes change | **held**: 12 / 172 / 171 / 184; 0 appear or vanish; **0** outcomes changed |
| P5 | HP `mapped_regions` byte-identical | **held**: **8 of 8** |
| P6 | UIR 0 of 12; dumps 0 of 16; reports change on exactly HP disk, storport, usbxhci | **held**: 0; 0; exactly those three |
| P7 | the gate fires on exactly the (bl) red; `[accepted=14]`; (bk) red; 419 tests; 13 reds | **held** (`fix-bl-xpass-gate-2026-09-24.log`) |

**The hash's readers, handled per the owner's condition.**
- The header's precedence note now names both hashes.
- The **five** evidence documents citing `b48923e8…` keep it and gain *frozen
  until 2026-09-24; superseded by `cd4278db…`*: `vocab-freeze-tier1-prereg`,
  `import-sort-exit`, `fix-bj-values-prereg`, `x3-sourcing-prereg`, and the
  register.
- **The sixth reader is a log**, `vocab-widen-sibling-2026-09-20.log`: a
  verbatim gate output, **left untouched by design**. A banked log records
  what was run.
- "6 evidence documents" in `bl-criterion-read` was that directory count,
  5 documents and 1 log.

**Independent checks: four**, as pre-registered. The replication is reported
separately and is not counted as a prediction.

**What (bl) leaves open.** The criterion now exists. `(bi)`'s 18
hardware-typed, imported names can be adjudicated against it, and 3 of the 18
(the MDL routines) are done by this edit. The HP-eight "320 hardware
functions" is now **266**. Stage 2's figures are unchanged (P5).
