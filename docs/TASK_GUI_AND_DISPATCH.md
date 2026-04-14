# TASK: Phase 7 — GUI Vocabulary, Stub Dispatch & Form Engine

# STATUS: QUEUED — do not start until pipeline items 1-4 are complete

**Project:** ForthOS / bare-metal-forth
**Session date:** April 2026
**Queued after:**

1. ARM64 Phase C-F — boot stub, QEMU raspi3b, real Pi hardware
2. DISK-SURVEY Phase 2 — CAB/MSI/ZIP archive extraction
3. UBT pipeline integration — disk survey → translator on real hardware
4. Cortex-M33 / picoZ80 RP2350B target

---

## What Has Been Built (as of this queue date)

- Bare-metal Forth-83 OS, 66KB kernel, 178-word dictionary
- AHCI disk driver, NTFS/FAT32 filesystem readers
- RTL8168 gigabit network driver with UDP console
- AUTO-DETECT zero-typing PXE boot
- DISK-SURVEY: 97,624 binaries cataloged on real HP hardware
- UBT pipeline: 268 tests, 18 real-world drivers validated
- Metacompiler: self-hosting proven, standalone bootable kernel
- ARM64 cross-compile: 79 primitives, code generation verified
- Combined image for single-file PXE delivery
- Commercial infrastructure: landing page, Shopify tiers, repo split

---

## Why Phase 7 Is Queued (Not Started)

The GUI/Form Engine is valuable and design-complete, but the pipeline items
above have external timeline pressure (ARM64 → Pi hardware, Cortex-M33 →
picoZ80 commercialization). Phase 7 is self-contained and can slot in cleanly
after the pipeline clears. Nothing in this plan will be invalidated by the
pipeline work.

---

## Full Design Reference

See these files (already in repo):
- `docs/TASK_MENTOR_SESSION_GUI_AND_DISPATCH.md` — complete spec with all word
  signatures, memory layout, widget table format, .def file format, forthmon.c
  full source, test matrix, 10-step implementation order
- `docs/get_graphics_elements_and_stub_dispatch.html` — visual architecture
  diagram (harvesting pipeline + stub dispatch table)

---

## Mentor Principles (April 2026 session)

> *"When it looks complex, reduce it to its simplest components. Build the
> framework first, then make it fancy."*

> *"If you can make a word called GET-GRAPHICS-ELEMENTS, you can scrape the
> libs in that library and instantly have the look and feel of the existing
> software — no extra code needed."*

> *"All OOP models in modern programming languages are built on the same model.
> Most AI uses one of four models at its base. Most printers use the same
> primary models. Look for the simplest elements and you have the gold."*

> *"We all built a TRACE word that watched program execution — and when it
> called a subroutine with an empty definition, we knew he kept the OS's 16
> stubs but left them empty so software wouldn't run."*

---

## Architectural Proof (add to CLAUDE.md when Phase 7 starts)

Modern GUI libraries are parameter tables passed to rendering subroutines.
`CreateWindow()`, `gtk_button_new_with_label()`, `QPushButton()` — all take:

```
type | label | x | y | width | height | style-flags | parent | callback
```

That is a tag/value matrix. A Forth word with the right stack signature IS the
DLL call — no OS, no HAL, no registry. The `.def` file describes the form.
`FORM-LOAD` parses it and pushes parameters. The widget word executes.
Complete GUI pipeline. No compile step. No restart.

---

## Claude Code's Verified Implementation Plan

Claude Code explored the codebase before planning and found 6 missing-word
traps. All have clean workarounds. The plan below is ready to execute as-is.

### Critical Gaps — Corrections Mandatory

| Spec assumes | Reality | Fix |
|---|---|---|
| `CASE/OF/ENDOF/ENDCASE` | Not in kernel | Nested `IF/ELSE/THEN` chains |
| `COMPARE` | Not in kernel | Reuse `STR=` from `CATALOG-RESOLVER` |
| `COUNT` | Not in kernel | Use `addr+len` pairs directly |
| `3DROP / 4DROP` | Not in kernel | `DROP DROP DROP` etc. |
| `>NUMBER` | Not in kernel | Manual digit parser loop |
| `EXIT-XT` constant | Not in kernel | `['] EXIT` (bracket-tick at line 1389) |
| `ONLY FORTH DEFINITIONS` | Wrong convention | `FORTH DEFINITIONS` then `DECIMAL` |
| Hardcoded block numbers | Dynamic allocation | `write-catalog.py` assigns them |
| `FIND ( c-addr -- ... )` | Simplified form | Use `'` (TICK) instead |

**What DOES exist:** `>BODY`, `EXIT`, `UNLOOP`, `CELLS`, `CELL+`, `[']`,
`CMOVE`, `TYPE`, `KEY`, `EMIT`, `CR`, `SPACE`, `INB/OUTB/INW/OUTW/INL/OUTL`

**Memory 0x90000-0x99FFF confirmed free.** Highest existing kernel structure is
`ISR_HOOK_TABLE` at 0x29C00. Dictionary starts at 0x30000. No collision.

**`STR=` exists** in `catalog-resolver.fth` line 53 — reuse via
`ALSO CATALOG-RESOLVER` instead of reimplementing `COMPARE`.

---

### Step 1: `stub-dispatch.fth`

File: `forth/dict/stub-dispatch.fth`
Depends on: Kernel only

```forth
\ STUB? simplifies to one line using ['] EXIT
: STUB? ( xt -- flag )  >BODY @ ['] EXIT = ;
```

Dispatch table at `0x9A000`: 2-cell entries (stub-xt, new-xt), max 16.
- `ROUTE-ADD ( stub-xt new-xt -- )` — register replacement pair
- `ROUTE-CALL ( xt -- )` — execute, routing stubs to replacements
- `ROUTE-DUMP ( -- )` — list pairs

Test: `tests/test_stub_dispatch.py` — 6 tests (empty word → STUB? TRUE,
real word → STUB? FALSE, ROUTE-ADD + ROUTE-CALL routing verified)

---

### Step 2: `ui-core.fth`

File: `forth/dict/ui-core.fth`
Depends on: Kernel only

Widget type constants: `WT-LABEL(1)` `WT-BUTTON(2)` `WT-DROPBOX(3)`
`WT-LIST(4)` `WT-INPUT(5)` `WT-DIVIDER(6)` `WT-CARD-BEGIN(7)`
`WT-CARD-END(8)` `WT-MENU-BUTTON(9)`

Memory layout:
- Widget table: `0x90000`, 64 bytes/entry, max 128
- Label string pool: `0x92000` (8KB)
- Event ring: `0x97000`

Core words:
- `VGA-CLS ( -- )` — clear VGA text buffer at `0xB8000`
- `CURSOR-AT ( col row -- )` — CRTC register writes (0x3D4/0x3D5)
- `HLINE ( col row len -- )` — horizontal dash line
- `UI-LABEL ( x y addr len -- )` — `AT-XY TYPE`
- `UI-BUTTON ( x y w addr len -- )` — render `[label]`
- `UI-DIVIDER ( y -- )` — full-width dashes at row
- `MENU-BUTTON ( addr len -- )` — menu bar item
- `RENDER-WIDGET ( entry-addr -- )` — IF/THEN chain on type byte
- `EVENT-PUSH`, `EVENT-POP`

Test: `tests/test_ui_core.py` — 8 tests (constants, VGA-CLS no crash,
CURSOR-AT no crash, UI-LABEL renders, event push/pop round-trip)

---

### Step 3: `gui-harvest.fth`

File: `forth/dict/gui-harvest.fth`
Depends on: UI-CORE, CATALOG-RESOLVER (for STR=)

Widget registry — parallel arrays:
- `WIDGET-NAME-TABLE` at `0x9B000` (32 bytes/entry, 64 max)
- `WIDGET-XT-TABLE` at `0x9C000`
- `WIDGET-TYPE-TABLE` at `0x9C200`

Words:
- `WIDGET-REGISTER ( name-a name-l type xt -- )`
- `WIDGET-FIND ( name-a name-l -- xt | 0 )` — uses STR= for comparison
- `WIDGETS-LIST ( -- )` — dump registry
- `GET-GRAPHICS-ELEMENTS` — stub/placeholder; full implementation requires
  UBT `SEM_CAT_GUI` (private repo, separate session)

MENU-STANDARD words (`MENU-FILE`, `MENU-EDIT`, `MENU-VIEW`, `MENU-PRINT`,
`MENU-HELP`, `MENU-BAR`) defined here after MENU-BUTTON is available via
`ALSO UI-CORE`.

Test: `tests/test_gui_harvest.py` — 5 tests (WIDGET-REGISTER 3 items,
WIDGET-COUNT=3, WIDGET-FIND by name, WIDGETS-LIST no crash)

---

### Step 4: `ui-parser.fth`

File: `forth/dict/ui-parser.fth`
Depends on: UI-CORE, CATALOG-RESOLVER (for STR=)

Tag/value `.def` parser. Each line: `TAG: value...`

Utility words (implement here, kernel lacks them):
- `SKIP-SPACES ( addr len -- addr' len' )`
- `NEXT-TOKEN ( addr len -- tok-a tok-l rest-a rest-l )`
- `PARSE-QUOTED ( addr len -- str-a str-l )`
- `PARSE-INT ( addr len -- n )` — manual digit loop
- `TAG-IS? ( addr len tag-addr tag-len -- flag )` — wraps STR=

Tag dispatch: `DISPATCH-TAG` is an IF/THEN chain calling `BUILD-LABEL`,
`BUILD-BUTTON`, `BUILD-DIVIDER`, `BUILD-CARD`, etc.

`FORM-LOAD ( blk-start blk-end -- )` — iterate blocks, 16 lines/block
(64 chars each), strip padding, call `DISPATCH-TAG`.

Test: `tests/test_ui_parser.py` — embed `disk-survey.def` as blocks,
call FORM-LOAD, check WT-COUNT matches expected widget count.

---

### Step 5: `ui-events.fth`

File: `forth/dict/ui-events.fth`
Depends on: UI-CORE, UI-PARSER

- `FORM-RENDER ( -- )` — iterate widget table, RENDER-WIDGET for each
- `FOCUS-NEXT ( -- )` — advance focus among buttons
- `ACTIVATE-FOCUS ( -- )` — execute focused widget's action-xt
- `HANDLE-KEY ( key -- )` — route digit keys 1-9 to button activation
- `FORM-RUN ( -- )` — BEGIN/AGAIN: FORM-RENDER, KEY, IF/THEN dispatch
  on q/ESC/TAB/ENTER/digits. No CASE.
- `EVENT-FLUSH ( -- )` — write event ring to block 200

Test: `tests/test_ui_events.py` — FORM-RUN starts and 'q' exits cleanly,
FORM-RENDER no crash, EVENT-PUSH + EVENT-FLUSH writes block.

---

### Step 6: `forthmon.c` + `disk-survey.def`

Files: `tools/forthmon.c`, `forms/disk-survey.def`

The `forthmon.c` source is fully written in
`docs/TASK_MENTOR_SESSION_GUI_AND_DISPATCH.md` — ~300 lines, POSIX only,
zero external dependencies. Corrections needed from spec version:
- CARD tag parser: align sscanf with `.def` format `CARD: name x y w h "title"`
- Add `--help` flag
- Clean compile: `gcc -O2 -Wall -Wextra -o tools/forthmon tools/forthmon.c`

Add Makefile target:
```makefile
forthmon: tools/forthmon.c
	gcc -O2 -Wall -o tools/forthmon tools/forthmon.c
```

What it does: reads the same `.def` file ForthOS uses, renders an ANSI
terminal mirror of the running form, bridges keyboard → UDP events → ForthOS,
displays ForthOS output in list widgets. Same `.def` file, two renderers —
bare-metal VGA on the HP, terminal window on the dev machine.

---

### Step 7: Tests + Makefile integration

New test files:
- `tests/test_stub_dispatch.py` — 6 tests
- `tests/test_ui_core.py` — 8 tests
- `tests/test_gui_harvest.py` — 5 tests

Add to Makefile test-vocabs loop. Add `forthmon` build target.

Verification gate: `make clean && make && make test` — all existing 151+
new tests pass. Zero regression.

---

### Private Repo Work (separate session, after public work)

In `forthos-vocabularies` (private repo):
- `semantic.h`: add `gui_widget_type_t` enum, `stub_type_t` enum
- `semantic.c`: add `SEM_CAT_GUI` category, 24 GUI API table entries
  (`CreateWindowEx`, `MessageBox`, `DrawMenuBar`, etc.), `sem_classify_stub()`
- `forth_codegen.c`: emit `\ STUB: minimal` comments, emit
  `WIDGET-REGISTER` calls in generated vocab output
- Tests for GUI classification

---

### Files Created (Public Repo)

```
forth/dict/stub-dispatch.fth  — STUB? ROUTE-ADD ROUTE-CALL
forth/dict/ui-core.fth        — widget types, VGA rendering, event buffer
forth/dict/gui-harvest.fth    — WIDGET-REGISTER GET-GRAPHICS-ELEMENTS MENU-BAR
forth/dict/ui-parser.fth      — FORM-LOAD .def tag parser
forth/dict/ui-events.fth      — FORM-RENDER FORM-RUN event loop
tools/forthmon.c              — ANSI terminal form monitor (C, POSIX only)
forms/disk-survey.def         — sample form definition
tests/test_stub_dispatch.py   — 6 tests
tests/test_ui_core.py         — 8 tests
tests/test_gui_harvest.py     — 5 tests
```

---

### Implementation Rules (do not skip)

1. 64-char line limit — hard. Split everything.
2. No `CASE` — `IF/THEN` chains everywhere
3. No `COMPARE` — use `STR=` via `ALSO CATALOG-RESOLVER`
4. No `COUNT` — use `addr+len` pairs directly
5. `FORTH DEFINITIONS` + `DECIMAL` at end of every vocab file
6. Never hardcode block numbers — `write-catalog.py` assigns them
7. `make write-catalog && make test` after each step before proceeding
8. Zero regression — all existing tests must stay green at every step
9. `pkill -f "[q]emu.*PORT"` bracket trick for QEMU cleanup
10. If a step takes 3+ QEMU cycles without green tests — stop, flag, do not loop

---

*"Look for the simplest elements and you have the gold."*
*— Mentor, April 2026*
