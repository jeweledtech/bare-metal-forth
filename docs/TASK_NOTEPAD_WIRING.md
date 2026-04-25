# TASK: Wire NOTEPAD into a Working Text Editor

**Status as of 2026-04-25:** NOTEPAD form renders on HP (d95cef9).
This task is wiring work to make it functional.

**Depends on:** d95cef9 (NOTEPAD form renders on HP bare metal)
**Goal:** Button widgets fire actions (New/Open/Save/Exit), text area
accepts keyboard input with Shift/Ctrl, Open reads NTFS files, Save
writes them, Exit returns to the `ok` prompt.

---

## Bugs Blocking This Task

| # | Bug | File | Lines | Status |
|---|-----|------|-------|--------|
| B1 | RAW-SCAN discards Ctrl/Shift without tracking KB-MODS | file-editor.fth | 110-118 | **OPEN** — blocks all keyboard testing |
| B2 | FILE-READ clamps to 8 sectors (4 KB) | ntfs.fth | 608-609 | **DEFERRABLE** — Open works for files < 4 KB |
| B3 | ~~NTFS-WRITE-FILE passes unclamped count to AHCI-WRITE~~ | file-editor.fth | 462 | **DONE** — FE-SAVE has 4 KB guard |
| B4 | ~~No AHCI/NTFS init in NOTEPAD-RUN~~ | notepad.fth | 203 | **DONE** — AHCI-INIT/NTFS-INIT/NTFS-ENABLE-WRITE in NOTEPAD-RUN |

### B1 Detail — Dead Code in RAW-SCAN

```
Line 110: DUP 80 >= IF DROP 0 0 EXIT THEN  \ catches ALL >= 0x80
Line 114: DUP 9D = ...   \ Ctrl release  — DEAD (0x9D >= 0x80)
Line 117: DUP AA = ...   \ LShift release — DEAD (0xAA >= 0x80)
Line 118: DUP B6 = ...   \ RShift release — DEAD (0xB6 >= 0x80)
```

Break codes (>= 0x80) are filtered before modifier-release checks
run. KB-UPDATE-MODS never sees them. Ctrl/Shift get stuck "pressed."

**Fix:** Insert `DUP KB-UPDATE-MODS` *before* the `>= 0x80` filter.
Add `ALSO PS2-KEYBOARD` to FILE-EDITOR so KB-UPDATE-MODS and
KB-MODS are in scope. Remove dead lines. Do NOT duplicate state
with new SK-* variables — use the kernel-tracked KB-MODS directly.

### B3 Detail — SEC-BUF Overflow

AHCI-WRITE (ahci.fth:241-242) does:
```
WR-BUF @ SEC-BUF  RD-CNT @ 200 * CMOVE
```
SEC-BUF is 0x1000 bytes (4 KB). If count > 8, CMOVE writes past
SEC-BUF into whatever follows in physical memory.

### Reference: KB-UPDATE-MODS and KB-SHIFT-MAP

Both live in `ps2-keyboard.fth` and must be in scope via
`ALSO PS2-KEYBOARD`.

**KB-UPDATE-MODS** `( scan -- )` — sets/clears KB-MODS bits:
- Bit 0: Shift  (make 0x2A/0x36, break 0xAA/0xB6)
- Bit 1: Ctrl   (make 0x1D, break 0x9D)
- Bit 2: Alt    (make 0x38, break 0xB8)

Handles both left and right variants. Consumes the scancode.

**KB-SHIFT-MAP** — `CREATE` array, 0x3A bytes, scancode-indexed.
Uppercase letters + shifted symbols (!@#$%^&*()_+{}|:"<>?~).
Same format as SC-ASC — used as `KB-SHIFT-MAP scancode + C@`.

---

## Completed Steps

### ~~Step 0 — Verify Baseline~~ DONE

Form renders on HP bare metal. Tab cycles focus, buttons fire
stubs, Escape exits. Confirmed in milestone commit d95cef9.

### ~~Step 3 — Add AHCI/NTFS Init to NOTEPAD-RUN~~ DONE

Already in notepad.fth:203 — `AHCI-INIT NTFS-INIT NTFS-ENABLE-WRITE`.
ALSO NTFS and ALSO AHCI in vocabulary header (lines 33-34).

### ~~Step 6 — FE-SAVE 4 KB Guard~~ DONE

file-editor.fth:462 — `FE-SIZE @ 1000 > IF` guard prevents
SEC-BUF overflow. Chunked write (Option B) deferred.

---

## Remaining Steps

### Step 1 — Fix RAW-SCAN: Track Modifiers via KB-MODS

**Fixes:** B1 (blocks ALL keyboard testing)
**Scope:** `forth/dict/file-editor.fth`, `forth/dict/notepad.fth`
**Commit template:** `fix(file-editor): track Shift/Ctrl in RAW-SCAN via KB-MODS`

**1a.** Add `ALSO PS2-KEYBOARD` to FILE-EDITOR vocabulary header
(after line 29, alongside ALSO NTFS / ALSO AHCI / ALSO HARDWARE).

**1b.** Rewrite RAW-SCAN (lines 97-120):
```forth
: RAW-SCAN ( -- scancode type )
    BEGIN
        KB-RING-COUNT @ 0=
    WHILE
    REPEAT
    KB-RING-BUF KB-RING-TAIL @ + C@
    RS-CODE !
    KB-RING-TAIL @
    1+ DUP 10 >= IF DROP 0 THEN
    KB-RING-TAIL !
    -1 KB-RING-COUNT +!
    RS-CODE @
    DUP KB-UPDATE-MODS
    DUP 80 >= IF DROP 0 0 EXIT THEN
    DUP 1D = IF DROP 0 0 EXIT THEN
    DUP 2A = IF DROP 0 0 EXIT THEN
    DUP 36 = IF DROP 0 0 EXIT THEN
    DUP 38 = IF DROP 0 0 EXIT THEN
    1
;
```

Changes from original:
- `DUP KB-UPDATE-MODS` inserted before `>= 0x80` filter so
  break codes (Ctrl release 0x9D, Shift release 0xAA/0xB6)
  update KB-MODS before being filtered out.
- Dead lines removed (0x9D, 0xAA, 0xB6 — unreachable after
  the `>= 0x80` check, but now handled by KB-UPDATE-MODS).
- Alt make (0x38) added to modifier filter list.

**1c.** Gate Ctrl+S / Ctrl+Q in FE-DISPATCH on KB-MODS bit 1:
```forth
KB-MODS @ 2 AND IF
  DUP 1F = IF DROP FE-SAVE EXIT THEN
  DUP 10 = IF DROP 1 FE-QUIT ! EXIT THEN
THEN
```

**1d.** Add Shift-aware keymap lookup in FE-DISPATCH.
When `KB-MODS @ 1 AND` is true, use `KB-SHIFT-MAP` from
PS2-KEYBOARD instead of `SC-ASC`:
```forth
DUP 80 < IF
  KB-MODS @ 1 AND IF KB-SHIFT-MAP ELSE SC-ASC THEN
  + C@  ...
```

KB-SHIFT-MAP is a `CREATE` array in ps2-keyboard.fth,
scancode-indexed, same format as SC-ASC. Contains uppercase
letters and shifted symbols.

**1e.** Gate Ctrl+Q in NP-EDITOR-KEY (notepad.fth):
```forth
DUP SC-CTRL-Q = KB-MODS @ 2 AND AND IF
  DROP NP-EXIT-EDIT EXIT THEN
```

**1f.** Delete `VARIABLE SK-CTRL` (file-editor.fth line 125) —
no longer needed; KB-MODS replaces it.

**Verify (QEMU):**

Optional before/after probe (add temporarily after INIT-KEYMAP,
remove after verification):
```forth
: RAWSCAN-PROBE ( -- )
  ." Type keys. Ctrl+Q exits." CR
  BEGIN
    RAW-SCAN DUP 1 = IF
      DROP
      ." SC=" DUP .H2
      ."  MODS=" KB-MODS @ .H2 CR
      DUP 10 = KB-MODS @ 2 AND AND
      IF DROP EXIT THEN
      DROP
    ELSE 2DROP THEN
  AGAIN ;
```

With net console (`-serial udp:127.0.0.1:6666`), type:
`s`, `q`, Shift+S, Ctrl+S, Ctrl+Q.

Expected after fix:
```
SC=1F MODS=00     <- s, no modifier
SC=10 MODS=00     <- q, no modifier
SC=1F MODS=01     <- Shift+S, Shift tracked
SC=1F MODS=02     <- Ctrl+S, Ctrl tracked
SC=10 MODS=02     <- Ctrl+Q exits, Ctrl tracked
```

Then test in NOTEPAD:
```
USING NOTEPAD
NOTEPAD-RUN
\ Press New (button 1)
\ Type: "squat"  — all 5 letters appear
\ Type: Shift+H, e, l, l, o — "Hello" appears
\ Press Ctrl+Q — exits to form mode
\ Plain 'q' does NOT exit
```

**Pass (QEMU):** 's'/'q' type as chars. Shift = uppercase.
Only Ctrl+S saves, only Ctrl+Q exits.

**Pass (HP):** Same behavior on real keyboard. Timing-sensitive
modifier tracking works with physical PS/2 controller.

---

### Step 2 — Test NP-OPEN End-to-End (Small File)

**Scope:** Verification step — no code changes expected. If bugs
surface, fix before proceeding.
**Commit template:** (no commit unless fixes needed)

**Setup:** QEMU disk image with NTFS partition containing a
test file < 4 KB. Create via host mount before QEMU launch.

**Verify (QEMU):**
```
USING NOTEPAD
NOTEPAD-RUN
\ Tab to filename input field
\ Type: test.txt
\ Tab to Open button, press Enter
\ — or press key 2 (Open is 2nd button)
```

**Pass (QEMU):**
- File content appears in editor area (rows 8-21).
- Status bar shows filename, Ln 1, Col 1.
- Arrow keys move cursor within file content.
- Typing inserts characters (visible in editor area).
- Dirty indicator `*` appears after first edit.

**Pass (HP):** Open a known NTFS file on HP disk. Content
displays. Cursor navigates. Save round-trips.

**If it fails:** Check IV-GET returns typed filename. Add
`.` prints at each stage of FE-OPEN call chain.

---

### Step 3 — Clean Mode Transitions

**Scope:** `forth/dict/notepad.fth` (NP-EXIT-EDIT, NP-RUN)
**Commit template:** `fix(notepad): clean form/editor mode transitions`

The NP-RUN loop already calls FORM-RENDER when NP-EDIT-MODE
is 0, so form chrome should redraw fully. Verify and fix if
artifacts appear.

**Check list:**
1. New -> type text -> Esc -> form redraws with buttons visible.
2. New -> type text -> Esc -> New again -> buffer still there.
3. Open file -> Esc -> Open same file -> content still there.
4. Exit button (or Escape in form mode) -> clean `ok` return.
5. No VGA artifacts in rows 0-7 during editor mode.

**Verify (QEMU):** Run check list. If form chrome (rows 0-7)
bleeds into editor, add a row-range clear in NP-EXIT-EDIT.

**Pass (QEMU):** All 5 checks pass. No visual artifacts.

**Pass (HP):** Same 5 checks on real VGA output.

---

### Step 4 — Status Bar and Form Polish

**Scope:** `forth/dict/notepad-form.fth` — update or remove
`"Text area (future)"` placeholder label at row 8.
**Commit template:** `feat(notepad): remove placeholder label, polish status bar`

In editor mode, FE-STATUS renders at FE-SB-ROW (row 23). The
form's Exit button is also at row 23. Verify coexistence:
- Editor mode: status bar overwrites row 23 (Exit hidden).
- Form mode: FORM-RENDER restores Exit button and status label.

**Verify (QEMU):**
```
NOTEPAD-RUN
\ Press New
\ Type text, move cursor
\ Status bar shows: filename  Ln X  Col Y  *
\ Press Esc
\ Exit button visible at row 23
```

**Pass (QEMU):** Dynamic Ln/Col in editor. Dirty `*` after
first keystroke. Form chrome restores on exit.

**Pass (HP):** Same behavior on real VGA.

---

### Step 5 — Multi-Sector Read for Files > 4 KB (DEFERRABLE)

**Fixes:** B2 (FILE-READ 4 KB clamp)
**Scope:** `forth/dict/file-editor.fth` (FE-OPEN)
**Commit template:** `feat(file-editor): chunked NTFS read for files > 4 KB`

**This step is NOT required for a working editor.** NP-OPEN
works for files < 4 KB without any changes. Defer until the
basic editor workflow (Steps 1-4) is solid.

Replace the single-shot copy (line 451) with a chunked read
loop using PARSE-RUN for multiple data runs (fragmented files).

**Key NTFS internals (ntfs.fth):**
- `PARSE-RUN ( -- more? )` — advances PR-PTR, sets PR-LEN
  (cluster count) and PR-OFF (relative cluster offset).
- Absolute cluster = `PR-OFF @ RUN-PREV @ +`.
- Absolute LBA = `(abs_cluster * SEC/CLUS) + PART-LBA`.
- Outer loop iterates PARSE-RUN; inner loop chunks each run
  into 8-sector AHCI-READ calls.

**Verify (QEMU):**
- Open a file > 4 KB in NOTEPAD.
- PgDn past line 60 (4 KB boundary at ~64 chars/line).

**Pass (QEMU):** Content beyond 4 KB visible. TOTAL-LINES
reflects full file. No corruption at 4 KB boundary.

**Pass (HP):** Same with real NTFS partition files.

---

### Step 6 — HP Bare-Metal Validation

**Scope:** None. Flash USB, boot HP 15-bs0xx.
**Commit template:** (no commit — validation only)

**Procedure:**
1. Verify PXE image matches current build.
2. Boot to `ok` prompt.
3. `USING NOTEPAD` / `NOTEPAD-RUN`
4. Tab through buttons. Open a known NTFS file on HP disk.
5. Type text (lowercase, uppercase, symbols).
6. Save. Reopen. Verify round-trip.
7. Exit cleanly.

**Pass (HP):** All Steps 1-4 behaviors reproduce on real
hardware. Keyboard timing, AHCI DMA, and VGA output match.

**Pass criteria:** All of Step 0-8 behaviors reproduce on real
hardware. Keyboard timing, AHCI DMA, and VGA output match QEMU.

---

## Deferred (Separate Tasks)

These are related but out of scope for this wiring task:

- **Kernel S" interpret-mode bug** — S" in interpret mode leaks
  post-quote source bytes to console at top level. Exact mechanism
  in src/kernel/forth.asm TBD — likely fails to advance >IN past
  closing quote, or fails to allocate transient buffer. See commit
  4d47a47 for workaround precedent. Fix in forth.asm, then revert
  colon-def workarounds in notepad.fth and notepad-form.fth, and
  confirm clean boot.

- **.gitignore audit** — Untracked list includes mentor notes,
  copyrighted reference material, product photos, and design docs.
  Add patterns to prevent accidental commit to public repo.

- **Memory map sanity check** — Kernel grew from 66 KB to 98 KB.
  Verify nothing in `src/kernel/forth.asm` hardcodes a 64 KB ceiling.

- **Chunked NTFS write (Option B)** — If Step 6 ships with the
  4 KB guard, add chunked writes as a follow-up for full-size
  file editing.

- **Mouse input** — PS2-MOUSE driver tested (14/14) but not wired
  to the form event loop. Future: click-to-focus, button clicks.

- **Cut/Copy/Paste/Undo** — Stubs in notepad.fth. Clipboard buffer
  + undo stack are future work.
