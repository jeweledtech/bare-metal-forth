# (bt) codegen emits the recorded accesses: pre-registration (2026-09-25)

**Written before the fix.** Rulings (owner, 2026-09-25) are quoted in the
design. Outcomes go BELOW the line.

**The defect.** Stage 2's accesses live in
`sem_function_t.mapped_regions[].accesses`. The glue in `translator.c`
(`generate_forth_output`) copies only `hal_calls` and port ops into
`forth_gen_function_t`, which has no field for them. HDAudBus `1c0022510`
emits two bare `MAP-PHYS` calls and none of its 14 reads.

## The design

**Plumbing.** Codegen-side bridge structs (`forth_access_t` and
`forth_region_t`) are added to `forth_gen_function_t`, in the same bridge
pattern as `forth_hal_call_t`. `generate_forth_output` fills them from
`mapped_regions`. The codegen never includes `semantic.h`.

**A function is affected** when at least one of its mapped regions has at
least one recorded access. Every other function's word, and every driver
with no such function, is emitted exactly as before.

**For an affected function:**
1. **Accessor words (ruling 1)**: one `( base -- x )` word per distinct
   (offset, width) read of the function's region. They are sorted by
   offset, then width, and placed directly before the function word under
   the comment line
   `\ registers of the region mapped at 0x<call>, parked at 0x<park>`.
   - **Name:** `<VOCAB>-R<park>+<off>-<fetch>`, with `<park>` and `<off>`
     in uppercase hex without `0x`. The `-` before the fetch keeps
   `+3-C@` distinct from `+3C-@`. Nothing in the name is a spec register
   name.
   - **Body:** `<off> + <fetch> ;`, and just `<fetch> ;` at offset 0.
   - **Fetch by width:** 1 `C@`, 2 `W@` (one 16-bit load, confirmed), 4 `@`.
   - An offset whose first hex digit is a letter is written with a leading
     `0`, so it cannot be read as a word.
   - An accessor name already emitted in the vocabulary is not emitted
     again.
2. **Which accesses get an accessor:** a read that is not indexed, is
   determined, has a non-negative offset and has width 1, 2 or 4.
   - **Writes, indexed accesses and undetermined accesses get a comment
     and no word (ruling 4).**
3. **Two or more regions with accesses in one function (ruling 3):** no
   accessor words. The function word says so in its access lines. **The
   run is not refused.**
4. **The function word (ruling 2):**
   - Header: `: <NAME>  ( -- )  \ <N> recorded accesses`, plus `, <M> HAL
     call(s)` when calls other than MAP-PHYS remain.
   - Then **one `\ map` line per mapped region**, standing in for the
     MAP-PHYS calls, which are dropped. Each line gives the call site, the
     API and the park. A stopped walk adds `, walk stopped at 0x<a>`.
   - Then **one `\ access` line per recorded access, in the report's
     order.** Each shows the access site, kind, width and offset, and
     either `-> <accessor>` or why there is no word.
   - Then the remaining HAL calls, unchanged.

**What 1c0022510 must emit**, exactly (the red asserts this text):

```
\ registers of the region mapped at 0x1C0022671, parked at 0x58
: HDAUDBUS-R58+0-W@  ( base -- x )  W@ ;
: HDAUDBUS-R58+2-C@  ( base -- x )  2 + C@ ;
: HDAUDBUS-R58+3-C@  ( base -- x )  3 + C@ ;
: HDAUDBUS-R58+4-W@  ( base -- x )  4 + W@ ;
: HDAUDBUS-R58+6-W@  ( base -- x )  6 + W@ ;
: HDAUDBUS-R58+8-@  ( base -- x )  8 + @ ;
: HDAUDBUS-R58+14-W@  ( base -- x )  14 + W@ ;

: MMIO-FN-1C0022510  ( -- )  \ 14 recorded accesses
    \ map 0x1C0022671 (MmMapIoSpaceEx), parked at 0x58
    \ map 0x1C0022697 (MmMapIoSpaceEx), parked at 0x60
    \ access 0x1C00226D2: read 4 at +0x8 -> HDAUDBUS-R58+8-@
    \ access 0x1C00226E2: read 2 at +0x0 -> HDAUDBUS-R58+0-W@
    \ access 0x1C00226EA: read 2 at +0x0 -> HDAUDBUS-R58+0-W@
    \ access 0x1C00226F1: read 2 at +0x0 -> HDAUDBUS-R58+0-W@
    \ access 0x1C00227D0: read 2 at +0x0 -> HDAUDBUS-R58+0-W@
    \ access 0x1C0022865: read 1 at +0x3 -> HDAUDBUS-R58+3-C@
    \ access 0x1C002286D: read 1 at +0x2 -> HDAUDBUS-R58+2-C@
    \ access 0x1C0022981: read 2 at +0x0 -> HDAUDBUS-R58+0-W@
    \ access 0x1C0022994: read 2 at +0x0 -> HDAUDBUS-R58+0-W@
    \ access 0x1C00229A4: read 2 at +0x0 -> HDAUDBUS-R58+0-W@
    \ access 0x1C0022C02: read 2 at +0x14 -> HDAUDBUS-R58+14-W@
    \ access 0x1C0022C7D: read 2 at +0x0 -> HDAUDBUS-R58+0-W@
    \ access 0x1C0022CBD: read 2 at +0x4 -> HDAUDBUS-R58+4-W@
    \ access 0x1C0022D0F: read 2 at +0x6 -> HDAUDBUS-R58+6-W@
;
```

The reason texts for accesses with no word are `write, no word`,
`indexed, no word`, `two regions, no word`, and
`access undetermined at 0x<a> (reload 0x<r>), no word`.

## Counted from the input, before any code

Reports from build `57d9b73ebdd13337` (`-t report -S`), for all 1,338
inputs, with 0 empty and 0 unparseable. Only kept (hardware) functions
emit words. **No scaffolding or unclassified function has a recorded
access.**

| quantity | count |
|---|---|
| kept functions with recorded accesses | **11**, on **10** drivers |
| recorded accesses, which is the number of `\ access` lines | **62** |
| accessor words (single-region functions) | **26**: HP / Newer ASUS / Older ASUS `hdaudbus` 7 each, Dell `hdaudbus` 4 (its walk stops after 7 accesses), Older ASUS `fvevol` 1 |
| functions with two or more regions with accesses | **3** (Newer ASUS `errdev`; Older ASUS `iaStorAC` ×2), with **6** access lines marked `two regions` and **6** accessors withheld |
| write lines | **6** (`mlx4_bus` ×3 machines, 2 indexed writes each) |
| indexed reads, undetermined accesses, negative offsets, other widths | **0** each |
| `\ map` lines = MAP-PHYS calls dropped | **19** = **19** |
| map lines carrying `walk stopped` | **4** |
| map lines for a region that is not parked | **1** (`fvevol`) |
| other HAL calls kept (all `UNMAP-PHYS`) | **10** |

**8** of the 11 functions have exactly one region with accesses. The 26
accessors are their distinct (offset, width) fetchable reads, which is
how the counting script defines them. After the fix, T3 checks that
count in the emitted vocabulary.

**The red:** `bt_RED_codegen_emits_recorded_accesses` in
`test_mmio_consumer.c`. It asserts the text above for HP HDAudBus, and
that the word contains no executable `MAP-PHYS` line.

| # | prediction |
|---|---|
| T1 | the gate fires on **exactly** `bt_RED_codegen_emits_recorded_accesses`; tests 424 → 425; reds 12 → 13 → 12 |
| T2 | HP HDAudBus emits the block above byte for byte |
| T3 | **corpus totals** over the 1,338 `-t forth` outputs: 26 accessor definitions; 62 `\ access` lines; 19 `\ map` lines, of which 4 carry `walk stopped`; 6 `two regions, no word`; 6 `write` lines; and no MAP-PHYS call left in any of the 11 words |
| T4 | **should move:** exactly **10** drivers change, and within them exactly the **11** function words above change (plus their accessor blocks) |
| T5 | **must not move:** the other **1,328** drivers are byte-identical. In the 10, every word of a function without accesses, and every line outside the 11 words and their accessor blocks, is byte-identical |
| T6 | nothing else moves: `-t report` is byte-identical on 1,338 of 1,338 (this is a codegen change); every other test is unchanged |

---

## Outcome

*(below this line, from the artefact only)*

**Inputs hashed:** `translator.c` `8f6db6cc2a08134f`, `forth_codegen.c`
`5d20f7c0e1d93d33`, `forth_codegen.h` `c8fd9f2f48d1ec83`,
`test_mmio_consumer.c` `a91a8505ab5d8bf4`, and build `bin/translator`
`5b813601891fa1f0`. The build before the fix was `57d9b73ebdd13337`, and
its `-t forth` hashes equal (bs)'s after-sweep.

### The gate run also failed (bs)'s test, and the check was the suspect

**The gate fired on exactly `bt_RED_codegen_emits_recorded_accesses`.**
The same run (`fix-bt-xpass-gate-2026-09-25.log`, verbatim) also **failed
`bs_RED_f_emits_only_the_named_function`**: "the no-flag vocabulary has no
MMIO-FN-1C0022510".

**Read before touching:**
- The (bs) test's `cut_to_word` takes a definition to run from a `: ` line
  to a `;` line. (bt)'s accessors are **one-line** definitions (`: … ;`).
  So the parser ran from the first accessor to the word's `;`, treated all
  of it as one block named after that accessor, and never found the word.
- **The product was right.** `-f 1C0022510` emits the function's accessor
  group and its word, and drops only other functions' blocks.

**(bt) changed the format that the (bs) test reads, so (bt) owns that
reader (rule 24).**
- The parser now attaches a `\ registers of the region` group (its header,
  one-line definitions and one blank line) to the word that follows it. A
  group with no word after it fails the cut.
- **Nothing it asserts was loosened:** it still demands byte equality with
  the cut.
- **Checked independently of the test:** for **all 396** kept functions in
  the 10 moved drivers, CLI `-f <address>` equals the no-flag output cut
  with the same group rule, **396 of 396**.

### The predictions

| # | predicted | observed |
|---|---|---|
| T1 | the gate fires on exactly the (bt) red; 425 tests; reds 12 → 13 → 12 | **held**, with the (bs) reader failure above, which was read, resolved and recorded. After retiring the red: `test-all` exits 0, 425 tests across 27 suites, 12 reds, and the union matches |
| T2 | HP HDAudBus emits the pre-registered block byte for byte | **held**: the block is present verbatim |
| T3 | 26 accessors, 62 access lines, 19 map lines (4 `walk stopped`), 6 `two regions`, 6 writes, no MAP-PHYS left | **held exactly**: 26 / 62 / 19 (4) / 6 / 6, and no MAP-PHYS call left in any word with accesses |
| T4 | exactly 10 drivers, exactly 11 words | **held**: the moved set is the 10 predicted drivers, and the changed words are the 11 predicted functions |
| T5 | 1,328 drivers byte-identical; within the 10, everything else identical | **held**: 1,328 identical. In the 10, the head and tail of every file are identical, and every other word is identical |
| T6 | `-t report` identical on 1,338; nothing else moves | **held**: 1,338 of 1,338 |

**What the translator now emits for HDAudBus `1c0022510`** is seven
`( base -- x )` words for the registers read by hand on the HP today:
`+0 W@` (GCAP), `+2 C@` (VMIN), `+3 C@` (VMAJ), `+4 W@`, `+6 W@`, `+8 @`
(GCTL) and `+14 W@`. The spec names come from the spec check, not from
the codegen. **Finding the base (`PCI-FIND-CLASS` plus BAR) is the next
letter; it was not in (bt).**
