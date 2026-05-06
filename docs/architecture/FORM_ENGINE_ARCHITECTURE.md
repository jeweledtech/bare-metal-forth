# Form Engine Architecture

**Date:** 2026-05-06
**Status:** Draft for mentor review
**Primary source:** Mentor session 2026-05-06 (`mentor-notes/2026-05-06-mentor-architecture-notes.md`)
**Predecessor:** Architectural posture note (2026-05-05), existing form engine work in NOTEPAD
**Deliverable type:** Architecture document. No code changes.

---

## 0. References

### Primary mentor sources (in chronological order)

| Date | Artifact | Path | Key contribution |
|---|---|---|---|
| 2026-04-19 | Five planes of a digital system | `mentor-notes/2026-04-19-mentor-five-planes-of-digital-systems.md` | Five cooperating array planes: physical map, timing, address, data, code |
| 2026-04-20 | Form authoring pipeline | `mentor-notes/2026-04-20-mentor-form-authoring-pipeline.md` | Two-stage authoring (raw components + binding), compile-vs-interpret |
| 2026-04-21 | Vector UI + mouse input | `docs/references/2026-04-21-mentor-vector-ui-and-mouse-input.md` | Five-claim vector GUI spec: parameter records, line-segment rendering, hit-test dispatch |
| 2026-05-05 | Architectural posture | `docs/architecture/2026-05-05-architectural-posture.md` | Reduction thesis: ~40 panel types, form engine as foundation |
| **2026-05-06** | **Architecture notes** | **`mentor-notes/2026-05-06-mentor-architecture-notes.md`** | **Concrete architecture: boxes with common elements, d-word widget attributes, nested arrays, on-the-fly word creation, Qt Designer XML pipeline** |

### Project artifacts

| Artifact | Path | Role |
|---|---|---|
| Five-planes diagram | `docs/declarative_form_engine_five_planes.html` | SVG mapping five planes to form engine components |
| NTFS-to-form pipeline | `mentor-notes/forthos_ntfs_to_running_form_pipeline.html` | End-to-end pipeline diagram |
| Python schema example | `docs/references/python-form-schema-example.md` + `.txt` | Richer schema with FieldBinding, ValidationRule, master/detail |
| Forty-panel inventory | `docs/forty-panels-inventory.md` | 39 panels across 6 families, 5 shipped, 24 in-scope |
| Forty-panel hypothesis | `docs/VISION_FORTY_PANELS_INSERT.md` | Prose framing of the structural claim |
| UI-CORE | `forth/dict/ui-core.fth` | 9 widget types, VGA rendering, widget table, label pool, event ring |
| UI-PARSER | `forth/dict/ui-parser.fth` | `.def` tag parser (LABEL:, BUTTON:, DIVIDER:, INPUT:, etc.) |
| UI-EVENTS | `forth/dict/ui-events.fth` | FORM-RUN event loop, focus management, key dispatch |
| GUI-HARVEST | `forth/dict/gui-harvest.fth` | Widget registry: name-to-XT binding (64 slots) |
| NOTEPAD-FORM | `forth/dict/notepad-form.fth` | In-memory form definition (CREATE buffer + CATALOG-REGISTER) |
| NOTEPAD | `forth/dict/notepad.fth` | Application wiring: FORM-LOAD, FORM-WIRE, Chrome+Content mode switching |
| FILE-EDITOR | `forth/dict/file-editor.fth` | Content engine: FE-SET-REGION, direct VGA rendering |

---

## 1. Posture and Scope

From the 2026-05-06 mentor session:

> "Think about the software installed on your computer as a series of boxes. You have File operations that all use some kind of file tree display to choose the file location. You have a small pop up that lets you name the file. Each of these 'operations' have a specific box with repeated common elements. MS Word and Notepad both use the same basic file browser component."

This is the reduction thesis made concrete. The form engine is the layer that builds these boxes. It provides the common elements (tree, buttons, labels, inputs); applications provide the data and the logic that binds to them. NOTEPAD is the first box. The architecture this document describes is how the engine generalizes from one box to forty.

The 2026-05-05 posture note establishes this formally: the form engine is the architectural foundation of ForthOS under the reduction posture; the UBT pipeline is a research instrument, not a production source; NOTEPAD is the first instance, not a one-off.

**This document is architecture, not implementation.** It does not write Forth code, define concrete panel `.def` files, or implement new widgets. Those are downstream tasks.

---

## 2. Architectural Model

### The five planes

Any digital system factors into five cooperating array planes (per `mentor-notes/2026-04-19-mentor-five-planes-of-digital-systems.md`). The form engine is one instance, mapped in `docs/declarative_form_engine_five_planes.html`.

| Plane | Form engine instance |
|---|---|
| **Physical map** | The `.def` blueprint. UI-PARSER reads it; ADD-LABEL, ADD-BUTTON populate the widget table. |
| **Timing** | UI-EVENTS main loop. Focus cycle. EVT-HEAD / EVT-TAIL ring buffer. |
| **Address** | WT-BASE (0x200000), POOL-BASE (0x202000), EVT-BASE (0x207000), IV-BASE (0x20D000), WT-VARS (0x209000). |
| **Data** | Widget records (64 bytes each), label strings, event entries, input characters. |
| **Code** | WIDGET-REGISTER binds labels to XTs. FORM-WIRE connects them at runtime. Handler words execute on events. |

### The nested array model

The 2026-05-06 mentor session introduces a data model that deepens the five-plane address and data planes:

> "Base plus offset equals row. Could be an array of 16 words. Array size is defined by you, but if you understand how to set up row/column arrays, you can do wonderful things. Then add the nest: tag as first array layer and then the nested array is the detail array."

The outer array is indexed by category (e.g., "client", "product", "source"), each 16 cells apart. The inner array holds the detail for that category. This maps directly to the form engine's current structure:

- **Outer array** = widget table at WT-BASE. Each widget entry is 64 bytes (the "row"). Walking the table by `WT-ESIZE *` is the `base + offset` walk.
- **Inner array** = the detail data for each widget. For labels: pool string. For inputs: IV-BASE buffer. For buttons: XT + label. For future treeviews: the tree data source array.

The mentor's insight that you "can jump that outer array by doing an array cell location at current pointer, dup it, read it, and see if that is what you want" is exactly what FORM-WIRE does: it iterates widgets, reads the label from the pool (the inner array), and matches it against the registry to find the XT.

### Widget attributes as bit-field d-words

The 2026-05-06 session specifies a concrete attribute encoding:

> "We used to have widget attributes (a d-word) that had like 4 bits to set a color, 4 bits for font, 6 bits for other settings and the last 2 bits were 'visible' and 'enabled'."

On the original 8-bit systems, this was a single d-word (16 bits). On a 64-bit system: a d-word is 2x64 = 128 bits, providing ample space for rich attributes. Read via `DUP OVER XOR` pattern for bit masking.

The current `ui-core.fth` has a simpler model: WTO-FLAGS (1 byte, bit 0 = visible). The d-word attribute model is the target architecture. The 48 reserved bytes in each 64-byte widget entry (offsets 16-63) can accommodate a d-word attribute field plus additional state.

### Worked example: NOTEPAD on the five planes

| Plane | NOTEPAD instance |
|---|---|
| Physical map | `notepad-form.fth`: 24 `.def` lines defining 1 title, 4 dividers, 2 card groups, 9 buttons, 1 input, 1 status label |
| Timing | `NP-RUN`: BEGIN loop alternating form mode (FORM-RENDER + KEY + HANDLE-KEY) and editor mode (FE-REFRESH + FE-KEY). NP-EDIT-MODE flag selects. |
| Address | Widget table at WT-BASE. Input buffer at IV-BASE[NP-INPUT-IDX]. Editor buffer at FE-BUF (64KB). Editor region: rows 8-21. |
| Data | Widget entries: button labels/positions. IV-GET: typed filename. FE-BUF: file content. FE-CX/FE-CY/FE-TOP: cursor/scroll. |
| Code | NP-REGISTER-BUTTONS wires 9 labels to handler XTs. FORM-WIRE matches at runtime. NP-OPEN calls FE-OPEN; NP-SAVE calls FE-SAVE. |

### Worked example: mentor's file-ops box

From the 2026-05-06 session: "tree object, save/delete/open button (3 buttons), sort of information label usually at the top."

| Plane | File-ops instance |
|---|---|
| Physical map | `.def` with: 1 treeview, 3 buttons (Open/Save/Delete), 1 info label, 1 access-mode dropdown |
| Timing | Focus cycle between tree and buttons. Tree selection updates info label. |
| Address | Widget table at WT-BASE. Tree data: directory array from NTFS/FAT32 vocab. |
| Data | Tree array (outer: directory entries; inner: file metadata). Info label text. Access mode value. |
| Code | Button handlers dispatch to file-op logic primitives. Tree selection handler populates info label. |

### Known issue: address-plane leak

All form engine addresses are hardcoded CONSTANTs. This works for single-form operation but cannot support multiple concurrent panels. Flagged as open question in Section 9.

---

## 3. Panel-Type Taxonomy

The forty-panel hypothesis (documented in `docs/VISION_FORTY_PANELS_INSERT.md`, enumerated in `docs/forty-panels-inventory.md`) claims the total UI surface decomposes into approximately forty panel types. Current inventory: 39 panels, 6 families, 5 shipped, 24 in-scope.

### The six families

| Family | Description | Common elements | Example |
|---|---|---|---|
| **A: Document/data** | Text or data with optional editing | Content engine + chrome (menu, status) | editor (shipped) |
| **B: File/resource** | Navigate and operate on collections | Treeview + list + action buttons | file-browser |
| **C: Configuration** | Edit structured settings | Input fields + dropdowns + cards | settings |
| **D: Communication** | Short-form user-system interaction | Title + body + OK/Cancel | alert, progress |
| **E: Specialized entry** | Editor/grid for structured data | Grid + formula bar | spreadsheet, calculator |
| **F: Navigation** | Sub-panels inside applications | Single widget row | menu-bar (shipped) |

Full enumeration in `docs/forty-panels-inventory.md`.

### Chrome+Content pattern

Every Family A-C panel follows the pattern established by NOTEPAD:

- **Form engine** owns chrome: menu bar, buttons, inputs, dividers, cards, status bar.
- **Domain engine** owns content: renders directly to a VGA region via SET-REGION.
- **Mode switching** is explicit: a flag toggles between form mode and content mode.

The form engine is reusable across all panel families. Each domain engine is independently testable.

---

## 4. Widget Primitives

### The mentor's widget model

The 2026-04-21 note specifies: "A button had a data primitive with fill-in variables we passed that function." The 2026-05-06 session elaborates the attribute encoding: a d-word with bit fields for color (4 bits), font (4 bits), other settings (6 bits), visible (1 bit), enabled (1 bit).

The existing 64-byte widget entry in `ui-core.fth` already implements the parameter-record model. Each entry holds: type, position, dimensions, flags, label reference, execution token. The 48 reserved bytes per entry are available for the d-word attribute field and future state.

The mentor also specifies show/hide behavior:

> "You can have an open, edit or save button but only show the open & save dialogs. Edit is still there, just not showing."

This is the `visible` bit in the attribute d-word. The current WTO-FLAGS byte supports this (bit 0 = visible), but the d-word encoding expands it to include `enabled` (widget renders but does not accept input) as a separate state.

### Existing primitives

9 widget types in `ui-core.fth`:

| Type | Constant | Focusable | Data binding |
|---|---|---|---|
| Label | WT-LABEL (1) | No | Pool string to VGA |
| Button | WT-BUTTON (2) | Yes | Carries XT; activates on Enter |
| Dropbox | WT-DROPBOX (3) | Yes | Pool string label |
| List | WT-LIST (4) | -- | Declared but not implemented |
| Input | WT-INPUT (5) | Yes | IV-BASE buffer (64 bytes/slot) |
| Divider | WT-DIVIDER (6) | No | Decorative |
| Card-begin | WT-CARD-BEGIN (7) | No | Pool string title |
| Card-end | WT-CARD-END (8) | No | Closes card |
| Menu-button | WT-MENU-BUTTON (9) | No | Pool string label |

### Widget entry structure

64 bytes at `WT-BASE + (index * 64)`:

| Offset | Name | Size | Content |
|---|---|---|---|
| 0 | WTO-TYPE | 1 | Widget type (1-9) |
| 1 | WTO-X | 1 | Column position |
| 2 | WTO-Y | 1 | Row position |
| 3 | WTO-W | 1 | Width |
| 4 | WTO-H | 1 | Height |
| 5 | WTO-FLAGS | 1 | Visibility/state (target: d-word encoding) |
| 6 | WTO-LLEN | 2 | Label length |
| 8 | WTO-LOFF | 4 | Label pool offset |
| 12 | WTO-XT | 4 | Execution token |
| 16-63 | reserved | 48 | Future: d-word attributes, hotspot rect, relative coords |

Maximum 128 widgets (WT-MAX). Labels in shared pool at POOL-BASE.

### Missing primitives

From the forty-panel inventory's framework prerequisites:

| Primitive | Needed by | Notes |
|---|---|---|
| **widget-textarea** | editor, viewer, log-viewer | May be Chrome+Content domain engine rather than widget |
| **widget-treeview** | file-browser, device-manager | The mentor's "file tree display" -- first widget needed beyond NOTEPAD |
| **widget-grid** | spreadsheet, hex-viewer | Row/column with cell selection |
| **focus-model** | all panels | Currently single integer; needs sub-region focus |
| **clipboard** | editor, input panels | Cut/copy/paste buffer |
| **modal-stack** | file-dialog, alert | Push/pop for modal overlays |

### Data-binding contracts

**Button**: Carries XT. Emits: activation event (Enter, 1-9 shortcut, or future mouse click within bounding rect). Two attribute bits govern behavior: visible (renders or not), enabled (accepts events or not).

**Input**: Reads pool string as placeholder. Reads/writes IV-BASE buffer. Emits: character events. Owns per-widget value buffer.

**Treeview (proposed)**: Reads data source callback. Emits: selection-changed with path. Owns: expand/collapse state, scroll position. This widget corresponds directly to the mentor's "file tree display" from the file-ops box.

**Grid (proposed)**: Reads data source `( row col -- cell-value )`. Emits: cell-selected `( row col -- )`. The nested array model from the 2026-05-06 session (outer array = rows, inner array = cell values) is the natural data source for this widget.

---

## 5. Schema

### Four options evaluated

**Option 1: Keep and extend the current `.def` format.**

```
LABEL: 1 0 "ForthOS Notepad"
DIVIDER: 1
CARD: 0 2 39 "File"
BUTTON: 1 3 6 "New"
INPUT: 7 6 50 ""
```

Pros: Works. Simple. Block-friendly (64-char lines). Proven on bare metal.
Cons: No validation, no bindings, no authoring tool.

**Option 2: Adopt Qt `.ui` subset.**

Pros: Free authoring tool (Qt Designer). Mature format.
Cons: XML parsing in Forth. Format carries unneeded complexity.

**Option 3: Custom XML.**

Pros: Full control. Simpler than `.ui`.
Cons: No authoring tool.

**Option 4 (recommended): Extended `.def` with `.ui` import shim.**

Keep `.def` as the native schema. Extend for new primitives (TREEVIEW:, GRID:) and optional properties. A Python tool converts `.ui` files to `.def`.

The mentor explicitly authorized this path (2026-05-06):

> "If you used it to generate the xml templates or even built that into a .res lib for the words to use, you would still be in the spirit of forth."

The `.def` format maps to the mentor's description of how XML UI files work:

> "Once you have a xml UI file, you can have the tag-value pairs for form details that display and the values you will post will have a variable name to work with (firstname). That is the tag and you fill the <value> field from the program."

The `.def` is already tag-value pairs. Extending it to include variable bindings (BIND: widget-name variable-name) follows the pattern the mentor described.

### Why Option 4

Separation along the five planes. The `.def` is the physical-map plane. Bindings are the code plane. Attribute d-words are the data plane. Keeping them separate means each is independently editable.

### Worked example: file-ops panel

```
FORM: file-ops
LABEL: 1 0 "File Operations"
DIVIDER: 1
TREEVIEW: 1 2 38 18 "tree"
BUTTON: 1 21 8 "Open"
BUTTON: 10 21 8 "Copy"
BUTTON: 19 21 8 "Move"
LABEL: 1 23 "No file selected"
DROPBOX: 30 23 20 "Access: Read-only"
END-FORM:
```

Tree data source and button handlers wired via WIDGET-REGISTER at the code plane, not in the `.def`.

---

## 6. Logic Primitives

### What the mentor specified

The 2026-05-06 session gives the most concrete description of logic primitives to date:

> "In the same way, the code works like that too: file operations have to mount a drive, get the drive directory tree and return that as an array. The file navigation tree uses that array to populate the navigation. The setting that matters here is the file access mode (read/write/read&write/delete/edit). The actual edit process uses an editor proper for that file type, but the file name and index are passed to whatever it is that will actually process the file."

This describes three logic blocks chained together:

1. **File-mount**: `( drive-id -- array )` -- mount drive, walk directory, return as nested array
2. **Tree-populate**: `( array -- )` -- consume directory array, populate treeview widget
3. **File-dispatch**: `( filename index -- )` -- pass file name and index to the appropriate editor/viewer

These are plug/socket blocks. The tree widget is the socket; file-mount produces the plug (the array). File-dispatch is the output socket; the appropriate domain engine is the output plug.

### On-the-fly word creation

The mentor describes a critical capability:

> "On the fly word creation. Being able to build a word from a live compile as you pull in information. That gives you the ability to load a set up file, build a live dictionary from the settings and then run the word(s) from that dynamic file input."

This is CREATE DOES> applied to the form engine: load a `.def` file, build a live widget dictionary, run the form. The existing FORM-LOAD already does a version of this (parses `.def`, populates widget table). The architectural extension is making the dynamically-created words first-class dictionary entries rather than anonymous table entries.

### CODECs

> "That is very helpful for handling codecs and header portions of files."

CODECs are logic primitives that transform data between formats. The mentor positions them alongside arrays and on-the-fly word creation as core capabilities. Example: FILE-EDITOR's CRLF stripping (commit 7f7c8c8) is already a CODEC -- the architectural step is naming it as such and making it discoverable via the catalog.

### The hit-test dispatcher

The 2026-04-21 note specifies mouse input:

> "The most primitive level gui mouse interface looks at button states, x-y coordinates and on click, sends that to the processing loop to sort out what was clicked."

`HIT-TEST ( x y -- xt | 0 )` -- iterates active widgets, checks bounding rectangles, returns matching XT. This is the mouse analog of BUTTON-ACTIVATE in UI-EVENTS.

### Existing patterns

- **WIDGET-REGISTER / WIDGET-FIND**: Name-to-XT registry (64 slots in gui-harvest.fth). The prototype for logic-primitive binding.
- **FORM-WIRE**: Runtime binder connecting physical map to code plane.
- **Chrome+Content**: NP-EDIT-MODE flag selects between form engine and domain engine. Manual plug/socket.

### Categories

| Category | Stack signature pattern | Example |
|---|---|---|
| File operations | `( drive-id -- array )` | Mount, directory tree, access mode |
| Data transformation | `( array -- array )` | Sort, filter, aggregate |
| Format conversion (CODECs) | `( addr len -- addr len )` | CRLF strip, encoding conversion |
| Input dispatch | `( x y -- xt \| 0 )` | Hit-test, focus cycle |
| Network operations | `( -- )` | UDP/TCP via NE2000/RTL8168 |

---

## 7. Resource Library Packaging

### Current state

Form data: CREATE buffer in `notepad-form.fth`, registered as catalog type 3 via CATALOG-REGISTER. Found by name via CATALOG-FIND.

The CATALOG system already handles dependency resolution (REQUIRES: headers) and block-range management (write-catalog.py).

### The mentor's `.res` model

> "If you used it to generate the xml templates or even built that into a .res lib for the words to use, you would still be in the spirit of forth."

The `.res` library is a collection of `.def` files (panel definitions) plus attribute templates, packaged as a catalog-addressable resource. The mentor's nested array model (2026-05-06) maps naturally: the outer array indexes panels by name; the inner array holds widget definitions.

### Recommended direction

Use the existing CATALOG system (type 3 entries). NOTEPAD-FORM already proves this works. New panels register the same way. The catalog resolver finds them by name; FORM-LOAD parses them.

The nested array persistence model (2026-05-06: "we would write them to disk when we wanted to preserve them as a block write, that way we could pull them back into the platform fast") maps directly to block storage. A panel's `.def` data in block format is already a persisted array that loads into live memory.

### Open questions

- How should resource updates be distributed across ForthOS instances?
- Multiple versions of the same panel definition for gradual rollout?

---

## 8. Path from Current State

Eight milestones. One-sentence proof criteria. No time estimates.

**Milestone 1: Generalize NOTEPAD's `.def` to canonical engine schema.**
Proof: A second application (calculator) loads a form via FORM-LOAD / FORM-WIRE with zero NOTEPAD-specific code.

**Milestone 2: D-word widget attributes.**
Proof: Widgets support visible/enabled bit flags using the d-word encoding the mentor specified. A button can be hidden (`visible=0`) and re-shown without rebuilding the form.

**Milestone 3: Build the file-browser panel.**
Proof: Treeview renders NTFS directory contents as a nested array, navigable with keyboard. The three-block logic chain (file-mount -> tree-populate -> file-dispatch) demonstrated end-to-end.

**Milestone 4: Build the settings-dialog panel.**
Proof: Form with inputs, dropdowns, cards loads from `.def`. Validates taxonomy for Family C.

**Milestone 5: Mouse integration and hit-test dispatch.**
Proof: PS2-MOUSE events feed UI-EVENTS. Clicking a button activates it. The mentor authorized: "to do GUI input, you need mouse function."

**Milestone 6: `.ui` import shim.**
Proof: Qt Designer `.ui` file converts to `.def` via Python tool. Resulting `.def` renders correctly.

**Milestone 7: Resource-library packaging.**
Proof: Panel `.def` definitions load via CATALOG-FIND from block storage, not hardcoded CREATE buffers.

**Milestone 8: First composed application.**
Proof: Application assembled from panel definitions + logic primitives + form engine, with no hand-written rendering outside domain content engines.

Vector rendering (DRAW-LINE, DRAW-BOX as integer primitives per the 2026-04-21 specification) is a parallel track alongside milestones 3-5. Text-mode ships first; vector uses the same `.def` with a different renderer.

---

## 9. Open Questions for Mentor Review

1. **Schema choice.** Is Qt `.ui` the right source format for the import shim, or did you have a different XML format in mind? Recommendation: extended `.def` native + `.ui` import (Section 5, Option 4).

2. **Widget granularity.** Should a file-tree be its own primitive (WT-TREEVIEW), or compose from a list + indentation + expand/collapse? Current primitives are coarse-grained; should new ones follow?

3. **Address-plane allocation.** The engine hardcodes WT-BASE at 0x200000. Should it request memory from a kernel allocator for multi-panel support?

4. **Inter-panel communication.** How should panels communicate in composed applications? Shared variables? Event ring? The current NOTEPAD-calls-FILE-EDITOR pattern does not scale.

5. **D-word attribute layout.** The 2026-05-06 session described 4+4+6+2 bits on 8-bit systems. For the 64-bit d-word: what additional attributes should be encoded? Font selection, background color, border style, scroll state?

6. **Nested array size.** The 2026-05-06 session used 16-cell outer array elements. For widget tables with 64-byte entries: is the current 64 bytes the right "row size," or should entries grow to accommodate the full d-word attribute + inner array pointer?

7. **CODECs and the form engine.** Is a CODEC a logic primitive, a standalone subsystem, or both? How should the CODEC definition format relate to `.def`?

8. **Vector rendering integration.** The 2026-04-21 note captures a complete vector spec (relative coordinates, line segments, hit-test). Is text-mode a degenerate case that ships first while vector rendering develops in parallel -- or was the vector model intended as canonical from the start, with text-mode as transitional?

9. **On-the-fly word creation.** The 2026-05-06 session emphasized building live dictionaries from setup files. Should FORM-LOAD create named dictionary entries (one word per widget, discoverable via FIND) rather than anonymous table entries? This would make forms inspectable from the Forth prompt.
