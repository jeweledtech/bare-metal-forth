# (bh) The import sort, built to its exit: pre-registration (2026-09-23)

**Written before any code.** The target is `import-sort-exit-2026-09-23.md`,
X1 and X2 as written, with the §5 amendments. Owner ruling: build to the exit
as written, with the independent scanner as the check on X2 and `unsorted` as
its own printed value. Outcomes go BELOW the line.

**X3 is not built in this step.** Its exit gives the HAL names' categories to
"act 2's own pre-registration, from the DDK". No DDK or WDK header is on disk,
and headers carry prototypes, not categories, so the per-name categories for
all 81 uncovered names have no pinned source. That is taken to the owner as a
question, with a proposal. It is not guessed, and it is not claimed.

## The change

1. **X1.** A function `sem_category_name()` covering every `sem_category_t`
   value. The report prints `"category": "<NAME>"`, where the name is the
   enum suffix (`PORT_IO`, `IRP`, `SYNC`, …). That is the same spelling as the
   Ghidra oracle's fixtures, so the two share a vocabulary.
   - Value 0 prints **`UNCLASSIFIED`**, meaning "not in the vocabulary", which
     is what 0 is.
   - An out-of-range value prints `INVALID_CATEGORY`, never hex.
   - **Readers enumerated first (rule 24):** nothing in the tree parses our
     `category`. The three validation suites read the Ghidra fixtures' field,
     not ours.
2. **X2.** A top-level report field, `"import_family"`, taking one of six
   values:
   - `storage-class`, `audio-port-class`, `wdf`, `hal-residue`: the first of
     CLASSPNP / portcls / WDFLDR / HAL imported, with the DLL name compared
     case-insensitively;
   - `unsorted`: a kernel driver that imports none of the four;
   - **`out-of-scope`**: not a kernel driver by the exit's byte definition
     (Subsystem ≠ NATIVE, or no import directory, or an import from
     `ntdll.dll`), and every non-PE input.

   **`out-of-scope` is new here and moves no X2 count**, since all 1,322 are
   in scope by construction. It exists so that the sort's absence on an
   application does not print as `unsorted`, which would claim the file is a
   driver. It needs the PE optional header's `Subsystem` field. The loader's
   header structs (`pe_format.h`) carry that field, but the loader does not
   copy it out, so `pe_context_t` gains
   `subsystem` and `sem_result_t` gains `pe_subsystem` (0 = not a PE). Both
   are plumbing with no other reader.
3. **Reds first**, in `test_semantic.c` under the new letter **(bh)**. The two
   new struct fields land with the reds, inert, so that the reds compile and
   fail rather than fail to build.
   - `sem_RED_bh_import_category_printed_as_name`: one import of every enum
     value; the JSON carries no `"category": "0x` and carries each name.
   - `sem_RED_bh_import_family_by_dll_set`: nine cases. CLASSPNP+HAL →
     storage-class; portcls+WDFLDR+HAL → audio-port-class; WDFLDR+HAL → wdf;
     HAL alone → hal-residue; ntoskrnl alone → unsorted; mixed-case
     `CLASSPNP.SYS` → storage-class; GUI subsystem → out-of-scope; an ntdll
     import → out-of-scope; no imports → out-of-scope.

## Predictions

| # | prediction |
|---|---|
| B1 | the XPASS gate fires on **exactly** the two `(bh)` names and nothing else moves. Tests 410 → 412; reds 12 → 14 while open, then back to 12 |
| B2 | **X1:** over the 1,322 distinct kernel drivers, **0 of 128,142** import entries print a hex category, and the report's import count equals the byte count on **1,322 of 1,322** (unchanged) |
| B3 | **X2:** `import_family` equals `kdrv_scan.py`'s answer on **1,322 of 1,322**, with counts storage-class 17, audio-port-class 15, wdf 360, hal-residue 266, unsorted 664 |
| B4 | on the excluded PE files (4,324 MZ files: 1,616 GUI, 2,448 console, 244 native with no import directory, 11 native importing ntdll, 5 boot applications), **every report emitted prints `out-of-scope`**. The number of reports emitted is **counted, not predicted**: files the translator refuses are listed by reason, not read as passes |
| B5 | on the HP eight, the report differs from the before-reading **only** in `category` values and the one added `import_family` line. The function lists, summary and call-graph figures are byte-identical |
| B6 | `-t uir` and the differential are untouched: 0 of 12 UIR files and 0 of 16 dumps change. This is a report-only change |

---

## Outcome

*(below this line, from the artefact only)*

**Inputs hashed:** `bin/translator` before `11f51761d4ad5d7a`, after
`03c1e890068a86f7`, built from private `7b3d67f` (red `1fdf84f`), mirror
identical. `dump_starts` `f4cee936de91769a` in both. `kdrv_scan.py`
`437b218a…`. Before-reading `77719b09…`, after-reading
`import-sort-report-after-2026-09-23.tsv` `2ee9a695…`, both in
`~/corpus/tools-2026-09-23/SHA256SUMS`.

| # | predicted | observed |
|---|---|---|
| B1 | the gate fires on exactly the two `(bh)` names; tests 410 → 412; reds 12 → 14 → 12 | **held**: the gate fired on exactly `sem_RED_bh_import_category_printed_as_name` and `sem_RED_bh_import_family_by_dll_set` (`fix-bh-xpass-gate-2026-09-23.log`), and nothing else. After removal: 412 tests across 27 suites, 12 reds, register union matches |
| B2 | X1: 0 of 128,142 hex; import count equals bytes on 1,322 of 1,322 | **held exactly**: **0 of 128,142** print a hex category (before: 128,142 of 128,142). The count equals the bytes on **1,322 of 1,322** |
| B3 | X2: 1,322 of 1,322 agree with the scanner; 17 / 15 / 360 / 266 / 664 | **held exactly**: **1,322 of 1,322** agree, 0 disagree. storage-class **17**, audio-port-class **15**, wdf **360**, hal-residue **266**, unsorted **664** |
| B4 | every report emitted on the 4,324 excluded PEs prints `out-of-scope`; the emitted count is counted, not predicted | **held**: **3,835 reports emitted, 3,835 `out-of-scope`, 0 anything else**. **489 not emitted**, each by the translator's own refusal and none read as a pass: **481** "No .text section found in PE" (resource-only images: 333 `.mui`, the rest resource DLLs) and **8** timeouts at 300 s (6 GUI, 2 console). Per reason: GUI 1,252 of 1,616 emitted, console 2,324 of 2,448, native with no imports 243 of 244, native importing ntdll 11 of 11, boot applications 5 of 5 |
| B5 | on the HP eight, only `category` values and the one `import_family` line differ | **held**, on all 12 snapshot inputs: each report changed in exactly **(imports + 1)** lines (ACPI 273 = 272 + 1, … the ELF fixture 1 = 0 + 1). Removing `category` and `import_family` lines leaves **0** differing lines |
| B6 | 0 of 12 UIR files and 0 of 16 dumps change | **held**: **0 of 12** and **0 of 16** |

**The families on the snapshot inputs** match the exit's §4. disk →
storage-class, HDAudBus → audio-port-class, usbxhci → wdf; ACPI, i8042prt,
pci, serial and storport → **hal-residue**; nmap and the ELF fixture →
**out-of-scope**. The two 32-bit ReactOS controls (native, importing `hal`)
also → hal-residue.

**Found on the way, not a prediction:** the census baseline
(`tests/suite_census.tsv`) carried `test_x86_decoder.c` at **14** registered
reds after `(bf)` and `(bg)` had closed; the live count was 12. The count
column was right and the red column was stale. `--update` corrected it in the
red commit, and the diff shows it.

**X3 is still open**, as stated at the top. The exit is two of three.
