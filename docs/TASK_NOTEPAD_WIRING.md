# TASK: Wire NOTEPAD into a Working Text Editor

**Status:** NOT STARTED
**Depends on:** d95cef9 (NOTEPAD form renders on HP bare metal)
**Goal:** Button widgets fire actions (New/Open/Save/Exit), text area
accepts keyboard input with Shift/Ctrl, Open reads NTFS files, Save
writes them, Exit returns to the `ok` prompt.

---

## Bugs Blocking This Task

| # | Bug | File | Lines | Impact |
|---|-----|------|-------|--------|
| B1 | RAW-SCAN discards Ctrl/Shift without tracking KB-MODS | file-editor.fth | 110-118 | Can't type 's' or 'q'; no uppercase/symbols |
| B2 | FILE-READ clamps to 8 sectors (4 KB) | ntfs.fth | 608-609 | Files > 4 KB silently truncated on open |
| B3 | NTFS-WRITE-FILE passes unclamped count to AHCI-WRITE | ntfs.fth | 724-727 | SEC-BUF overflow on files > 4 KB (memory corruption) |
| B4 | No AHCI/NTFS init in NOTEPAD-RUN | notepad.fth | 172-179 | File ops fail without manual pre-init |

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

## Steps

### Step 0 — Verify Baseline

**Change:** None.
**Test (QEMU):**
```
USING NOTEPAD
NOTEPAD-RUN
```
- Tab cycles focus across buttons and input field.
- Enter on a focused button prints its stub message.
- Pressing Escape returns to `ok` prompt.
- Editor sub-region (rows 8-21) is blank after pressing New.

**Pass criteria:** Form renders, focus works, no crash.

---

### Step 1 — UDP Probe for RAW-SCAN Before/After Evidence

**Change:** `forth/dict/file-editor.fth` — add temporary probe word.

Add after INIT-KEYMAP:
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

**Test (QEMU with net console):**
```
Host:  nc -u -l 6666 > /tmp/rawscan_before.txt
QEMU:  -serial udp:127.0.0.1:6666

USING FILE-EDITOR
RAWSCAN-PROBE
```

Type these keys in order: `s`, `q`, Shift+S, Ctrl+S, Ctrl+Q.

**Expected output (before fix):**
```
SC=1F MODS=00     <- s key, no Ctrl tracked
SC=10 MODS=00     <- q key, no Ctrl tracked
SC=1F MODS=00     <- Shift+S, Shift not tracked
SC=1F MODS=00     <- Ctrl+S, Ctrl not tracked
SC=10 MODS=00     <- Ctrl+Q exits (but MODS=00)
```

**Pass criteria:** Probe runs, captures to file. MODS column is
always 00 (proving modifiers aren't tracked). Save file as the
"before" baseline. This probe word stays in for Step 2; remove
after Step 2 passes.

---

### Step 2 — Fix RAW-SCAN: Track Modifiers via KB-MODS

**Change:** `forth/dict/file-editor.fth` and `forth/dict/notepad.fth`

**2a.** Add `ALSO PS2-KEYBOARD` to FILE-EDITOR vocabulary header
(after line 29, alongside ALSO NTFS / ALSO AHCI / ALSO HARDWARE).

**2b.** Rewrite RAW-SCAN (lines 97-120):
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

**2c.** Gate Ctrl+S / Ctrl+Q in FE-DISPATCH (lines 548-552):
```forth
\ Old:
DUP 1F = IF DROP FE-SAVE EXIT THEN
DUP 10 = IF DROP 1 FE-QUIT ! EXIT THEN

\ New:
KB-MODS @ 2 AND IF
  DUP 1F = IF DROP FE-SAVE EXIT THEN
  DUP 10 = IF DROP 1 FE-QUIT ! EXIT THEN
THEN
```

**2d.** Add Shift-aware keymap lookup in FE-DISPATCH (lines 562-578).
When `KB-MODS @ 1 AND` is true, use `KB-SHIFT-MAP` from
PS2-KEYBOARD instead of `SC-ASC`:
```forth
\ Old:
DUP 80 < IF  SC-ASC + C@  ...

\ New:
DUP 80 < IF
  KB-MODS @ 1 AND IF KB-SHIFT-MAP ELSE SC-ASC THEN
  + C@  ...
```

KB-SHIFT-MAP is a `CREATE` array in ps2-keyboard.fth (line 114),
scancode-indexed, same format as SC-ASC. Contains uppercase
letters and shifted symbols. Verified present.

**2e.** Gate Ctrl+Q in NP-EDITOR-KEY (notepad.fth line 145):
```forth
\ Old:
DUP SC-CTRL-Q = IF DROP NP-EXIT-EDIT EXIT THEN

\ New:
DUP SC-CTRL-Q = KB-MODS @ 2 AND AND IF
  DROP NP-EXIT-EDIT EXIT THEN
```

**2f.** Delete `VARIABLE SK-CTRL` (file-editor.fth line 125) —
no longer needed; KB-MODS replaces it.

**Test (QEMU with net console):**
```
Host:  nc -u -l 6666 > /tmp/rawscan_after.txt

USING FILE-EDITOR
RAWSCAN-PROBE
```

Type same sequence: `s`, `q`, Shift+S, Ctrl+S, Ctrl+Q.

**Expected output (after fix):**
```
SC=1F MODS=00     <- s, no modifier
SC=10 MODS=00     <- q, no modifier
SC=1F MODS=01     <- Shift+S, Shift tracked
SC=1F MODS=02     <- Ctrl+S, Ctrl tracked
SC=10 MODS=02     <- Ctrl+Q exits, Ctrl tracked
```

**Diff rawscan_before.txt vs rawscan_after.txt** = proof.

Then test editing:
```
USING NOTEPAD
NOTEPAD-RUN
\ Press New (button 1)
\ Type: "squat"  — all 5 letters appear
\ Type: Shift+H, e, l, l, o — "Hello" appears
\ Press Ctrl+Q — exits to form mode
\ Plain 'q' does NOT exit
```

**Pass criteria:** 's' and 'q' type as characters. Shift produces
uppercase. Only Ctrl+S saves, only Ctrl+Q exits editor. Remove
RAWSCAN-PROBE after this step passes.

---

### Step 3 — Add AHCI/NTFS Init to NOTEPAD-RUN

**Change:** `forth/dict/notepad.fth`

**3a.** Add `ALSO NTFS` and `ALSO AHCI` to vocabulary header
(alongside existing ALSO lines at lines 27-32).

**3b.** Add init calls at the top of NOTEPAD-RUN:
```forth
: NOTEPAD-RUN ( -- )
  ." Loading NOTEPAD..." CR
  AHCI-INIT NTFS-INIT NTFS-ENABLE-WRITE
  S" NOTEPAD-FORM" CATALOG-FIND
  ...
```

AHCI-INIT and NTFS-INIT are idempotent — safe to call if already
initialized. NTFS-ENABLE-WRITE sets the write-enable flag.

**Test (QEMU):**
```
USING NOTEPAD
NOTEPAD-RUN
```

**Pass criteria:** Init messages appear (AHCI port found, NTFS
partition found, write enabled). Form renders normally after.
No crash if AHCI/NTFS were already initialized.

---

### Step 4 — Test NP-OPEN End-to-End (Small File)

**Change:** None expected — this is a verification step. If bugs
surface, fix them before proceeding.

**Setup:** The QEMU disk image must contain an NTFS partition with
a small test file (< 4 KB). Create one via host mount before
QEMU launch.

**Test (QEMU):**
```
USING NOTEPAD
NOTEPAD-RUN
\ Tab to filename input field
\ Type: test.txt
\ Tab to Open button, press Enter
\ — or press key 2 (Open is 2nd button)
```

**Pass criteria:**
- File content appears in editor area (rows 8-21).
- Status bar shows filename, Ln 1, Col 1.
- Arrow keys move cursor within file content.
- Typing inserts characters (visible in editor area).
- Dirty indicator `*` appears after first edit.

**If it fails:** Check that CATALOG-FIND and FORM-WIRE ran before
NP-OPEN. Check that IV-GET returns the typed filename. Add
`.` prints at each stage of the FE-OPEN call chain.

---

### Step 5 — Multi-Sector Read for Files > 4 KB

**Fixes:** B2 (FILE-READ 4 KB clamp)
**Change:** `forth/dict/file-editor.fth` (FE-OPEN)

Replace the single-shot copy (line 451) with a chunked read loop
that handles **multiple data runs** (fragmented files).

**Key NTFS internals (ntfs.fth):**
- `PARSE-RUN ( -- more? )` — advances PR-PTR, sets PR-LEN
  (cluster count) and PR-OFF (signed relative cluster offset).
  Returns -1 if run parsed, 0 if end of run list.
- `PR-OFF` is relative to previous run. Accumulate in RUN-PREV:
  `PR-OFF @ RUN-PREV @ +` gives the absolute cluster.
- `SEC/CLUS @` converts clusters to sectors.
- `PART-LBA @` is the partition's start LBA.
- Absolute LBA = `(absolute_cluster * SEC/CLUS) + PART-LBA`.
- `MFT-DATA-RUNS` (line 406) only parses the FIRST run —
  do not use it. Set up PR-PTR from the $DATA attribute directly.

**Sketch:**
```forth
: FE-OPEN ( na nl -- )
    DUP FE-NLEN !  FE-NAME SWAP CMOVE
    FE-BUF MAX-FILE 0 FILL  0 FE-SIZE !
    FE-NAME FE-NLEN @
    MFT-FIND 0= IF ." Not found" CR EXIT THEN
    FOUND-REC !
    FOUND-REC @ MFT-READ IF ." MFT err" CR EXIT THEN
    \ Locate $DATA attribute, set PR-PTR
    ATTR-DATA MFT-ATTR
    DUP 0= IF ." No $DATA" CR EXIT THEN
    DUP 8 + C@ 0= IF DROP ." Resident" CR EXIT THEN
    DUP 20 + W@ + PR-PTR !
    DROP
    0 RUN-PREV !
    0  ( buf-offset )
    BEGIN
        PARSE-RUN
    WHILE
        PR-OFF @ RUN-PREV @ + DUP RUN-PREV !
        SEC/CLUS @ * PART-LBA @ +  ( lba )
        PR-LEN @ SEC/CLUS @ *      ( lba secs )
        \ Inner loop: read 8 sectors at a time
        0 DO                        ( lba buf-off )
            OVER I +                ( lba buf-off cur-lba )
            I J - 8 MIN             ( lba buf-off cur-lba cnt )
            AHCI-READ IF 2DROP UNLOOP EXIT THEN
            SEC-BUF
            OVER FE-BUF +           ( lba buf-off src dest )
            I J - 8 MIN 200 *       ( ... bytes )
            CMOVE
            I J - 8 MIN +           ( lba buf-off' )
        8 +LOOP
        SWAP DROP                   ( buf-off )
        DUP MAX-FILE >= IF LEAVE THEN
    REPEAT
    200 * MAX-FILE MIN FE-SIZE !
    \ Scan for NUL to get actual text length
    FE-SIZE @ 0 DO
        FE-BUF I + C@ 0= IF
            I FE-SIZE ! LEAVE
        THEN
    LOOP
;
```

Note: the inner DO..LOOP index arithmetic needs careful testing.
The sketch above is directional — implementation will adjust
based on stack-depth constraints. The critical invariant is:
**outer loop iterates PARSE-RUN; inner loop chunks each run
into 8-sector AHCI-READ calls.**

**Test (QEMU):**
- Create or find a file > 4 KB on the NTFS partition.
- Open it in NOTEPAD.
- PgDn past line 60 (4 KB boundary at ~64 chars/line).

**Pass criteria:** Content beyond 4 KB is visible. TOTAL-LINES
reflects the full file. No corruption at the 4 KB boundary.

**Risk:** Fragmented files on a used NTFS partition will have
multiple data runs. Test with both contiguous and fragmented
files if possible.

---

### Step 6 — Fix FE-SAVE: Guard and Chunked Write

**Fixes:** B3 (AHCI-WRITE SEC-BUF overflow)
**Change:** `forth/dict/file-editor.fth` (FE-SAVE) and optionally
`forth/dict/ntfs.fth` (NTFS-WRITE-FILE).

**Option A — Guard only (v1, recommended):**
Add a size check to FE-SAVE:
```forth
: FE-SAVE ( -- )
    FE-DIRTY @ 0= IF EXIT THEN
    FE-SIZE @ 1000 > IF
        ." >4KB: save disabled" CR EXIT
    THEN
    FE-BUF FE-SIZE @
    FE-NAME FE-NLEN @
    NTFS-WRITE-FILE IF
        ." Save err" CR EXIT
    THEN
    0 FE-DIRTY !
    ." Saved" CR ;
```

**Option B — Chunked write (v2, deferred):**
Same PARSE-RUN loop pattern as Step 5 but calling AHCI-WRITE in
8-sector chunks. Requires modifying NTFS-WRITE-FILE or adding a
parallel write word. Also need to update MFT $DATA attribute
sizes (real_size, initialized_size) after the write — the
existing NTFS-WRITE-FILE already does this (ntfs.fth:710-716).

**Test (QEMU):**
```
USING NOTEPAD
NOTEPAD-RUN
\ Press New
\ Type: "Hello from ForthOS"
\ Tab to input, type: test.txt
\ Press Save As (button 4)
\ Observe: "Saved" message
\ Press Ctrl+Q -> form mode
\ Re-open test.txt (type name, press Open)
\ Observe: "Hello from ForthOS" reappears
```

**Pass criteria:** Round-trip verified: type -> save -> reopen ->
same content. For files > 4 KB, the guard message appears (no
silent corruption).

---

### Step 7 — Clean Mode Transitions

**Change:** `forth/dict/notepad.fth` (NP-EXIT-EDIT, NP-RUN)

Verify that form-to-editor and editor-to-form transitions are
clean. The NP-RUN loop already calls FORM-RENDER (which does
VGA-CLS) when NP-EDIT-MODE is 0, so the form chrome should
redraw fully.

**Check list:**
1. New -> type text -> Esc -> form redraws with buttons visible.
2. New -> type text -> Esc -> New again -> previous buffer visible.
3. Open file -> Esc -> Open same file -> content still there.
4. Exit button (or Escape in form mode) -> clean return to `ok`.
5. No VGA artifacts in rows 0-7 during editor mode.

**Test (QEMU):**
Run through the check list above. If form chrome (rows 0-7)
bleeds into editor rendering, add a row-range clear in
NP-EXIT-EDIT.

**Pass criteria:** All 5 checks pass. No visual artifacts.

---

### Step 8 — Status Bar and Form Polish

**Change:** `forth/dict/notepad-form.fth` — update or remove the
`"Text area (future)"` placeholder label at row 8.

In editor mode, FE-STATUS renders at FE-SB-ROW (row 23). The
form's Exit button is also at row 23. Verify they coexist:
- Editor mode: status bar overwrites row 23 (Exit button hidden).
- Form mode: FORM-RENDER restores Exit button and status label.

**Test (QEMU):**
```
NOTEPAD-RUN
\ Press New
\ Type text, move cursor
\ Status bar shows: filename  Ln X  Col Y  *
\ Press Esc
\ Exit button visible at row 23
```

**Pass criteria:** Dynamic Ln/Col in editor mode. Dirty `*`
appears after first keystroke. Form chrome restores on exit.

---

### Step 9 — HP Bare-Metal Validation

**Change:** None. Flash USB, boot HP 15-bs0xx.

**Procedure:**
1. Verify PXE image matches current build.
2. Boot to `ok` prompt.
3. `USING NOTEPAD` / `NOTEPAD-RUN`
4. Tab through buttons. Open a known NTFS file on the HP disk.
5. Type text (lowercase, uppercase, symbols).
6. Save. Reopen. Verify round-trip.
7. Exit cleanly.

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
