\ ============================================
\ CATALOG: FILE-BROWSER
\ CATEGORY: app
\ PLATFORM: x86
\ SOURCE: hand-written
\ CONFIDENCE: medium
\ REQUIRES: UI-CORE
\ REQUIRES: UI-PARSER
\ REQUIRES: UI-EVENTS
\ REQUIRES: GUI-HARVEST
\ REQUIRES: FILE-EDITOR
\ REQUIRES: CATALOG-RESOLVER
\ REQUIRES: NTFS
\ ============================================
\
\ ForthOS File Browser: treeview panel.
\ Three-phase logic chain:
\   file-mount -> tree-populate -> file-dispatch
\
\ Usage:
\   USING FILE-BROWSER
\   FILE-BROWSER-RUN
\
\ ============================================

VOCABULARY FILE-BROWSER
FILE-BROWSER DEFINITIONS
ALSO UI-CORE
ALSO UI-EVENTS
ALSO UI-PARSER
ALSO GUI-HARVEST
ALSO FILE-EDITOR
ALSO CATALOG-RESOLVER
ALSO NTFS

HEX

\ ---- Memory layout constants ----
\ Map arrays at 16MB. Offsets sized for up
\ to 2M MFT records (~250K directories).
\ Trigger for HIGH-ALLOT: next panel needing
\ high memory builds a bump allocator here.
1000000 CONSTANT MAP-BASE

\ Region offsets (no overlap at any scale):
\ PARENT-OF: 8MB (4 bytes x 2M records)
\ DIR-LIST:  1MB (4 bytes x 250K dirs)
\ SORTED:    8MB (4 bytes x 2M records)
\ DIR-START: 1MB (4 bytes x 250K dirs)
\ DIR-COUNT: 1MB (4 bytes x 250K dirs)
\ FILL-CUR:  1MB (scratch cursor for fill)
: PARENT-OF  ( -- a ) MAP-BASE ;
: DIR-LIST   ( -- a ) MAP-BASE  800000 + ;
: SORTED     ( -- a ) MAP-BASE  900000 + ;
: DIR-START  ( -- a ) MAP-BASE 1100000 + ;
: DIR-COUNT  ( -- a ) MAP-BASE 1200000 + ;
: FILL-CUR   ( -- a ) MAP-BASE 1300000 + ;

DECIMAL

\ ---- Display/navigation constants ----
18 CONSTANT FB-ROWS
5  CONSTANT NTFS-ROOT
4  CONSTANT FB-CONTENT-Y
23 CONSTANT FB-STATUS-ROW

\ ---- State variables ----
VARIABLE FB-TOTAL
VARIABLE FB-MOUNTED
VARIABLE FB-CURSOR
VARIABLE FB-TOP
VARIABLE FB-CWD
VARIABLE FB-NCHILDREN
VARIABLE FB-TREE-MODE
VARIABLE FB-EDIT-MODE
VARIABLE FB-NDIRS

\ ---- Display buffers ----
\ 18 rows x 4 bytes = rec# per visible row
CREATE FB-VIEW 72 ALLOT
\ 18 bytes: 1=dir, 0=file per visible row
CREATE FB-ISDIR 18 ALLOT

HEX

\ ---- Defensive memory check ----
\ First write above 0x400000 in this project.
\ Returns TRUE (-1) if region is writable,
\ FALSE (0) if read-back fails.
: FB-MEM-OK? ( -- flag )
  DEADBEEF MAP-BASE !
  MAP-BASE @ DEADBEEF =
  0 MAP-BASE ! ;

\ ============================================
\ Phase 1: MFT-PARENT
\ ============================================
\ Extract parent directory rec# from the
\ $FILE_NAME attribute (type 0x30) of the
\ current MFT-BUF. Skips DOS namespace (2).
\ Parent ref is first 4 bytes of attr value
\ (lower 32 bits of the 48-bit MFT reference;
\ upper 16 bits are sequence number in bytes
\ 4-5, which we don't need).
\
\ Must call MFT-READ before this word.
\ Mirrors MFT-FILENAME (ntfs.fth:322-347)
\ but returns parent rec# instead of name.

: MFT-PARENT ( -- rec# | -1 )
  MFT-BUF 14 + W@
  MFT-BUF + >R
  BEGIN
    R@ @
    DUP ATTR-END = IF
      DROP R> DROP -1 EXIT
    THEN
    ATTR-FNAME = IF
      R@ 14 + W@ R@ +
      DUP 41 + C@
      2 <> IF
        @ R> DROP EXIT
      THEN
      DROP
    THEN
    R@ 4 + @
    DUP 0= IF
      DROP R> DROP -1 EXIT
    THEN
    R> + >R
  AGAIN ;

\ ============================================
\ Phase 1: FB-MOUNT (pass 1 — parent extract)
\ ============================================
\ Full MFT scan: for each valid in-use record,
\ extract parent ref into PARENT-OF[rec#].
\ Track directories in DIR-LIST.
\
\ MFT record flags (at MFT-BUF + 0x16):
\   bit 0 = in-use, bit 1 = is-directory

\ ---- Spinning indicator (Padma) ----
VARIABLE FB-SPIN-IDX
CREATE FB-SPIN-CHARS 4 ALLOT

DECIMAL
124 FB-SPIN-CHARS C!
47  FB-SPIN-CHARS 1+ C!
45  FB-SPIN-CHARS 2 + C!
92  FB-SPIN-CHARS 3 + C!

: FB-SPIN ( -- )
  FB-SPIN-IDX @ 1+ 3 AND FB-SPIN-IDX !
  FB-SPIN-CHARS FB-SPIN-IDX @ + C@
  EMIT 8 EMIT ;

HEX

\ ---- Helper predicates ----
: FB-IS-DIR? ( -- flag )
  MFT-BUF 16 + W@ 2 AND ;

: FB-IN-USE? ( -- flag )
  MFT-BUF 16 + W@ 1 AND ;

: FB-ADD-DIR ( rec# -- )
  FB-NDIRS @ 4 * DIR-LIST + !
  1 FB-NDIRS +! ;

\ ---- Per-record scan ----
\ Stack: ( i -- )
\ Stores parent at PARENT-OF[i*4].
\ On any failure path, stores -1.
: FB-SCAN-ONE ( i -- )
  DUP 10 < IF
    DUP 4 * PARENT-OF + -1 SWAP ! DROP EXIT
  THEN
  DUP MFT-READ 0= IF
    MFT-BUF @ FILE-SIG = IF
      FB-IN-USE? IF
        MFT-PARENT DUP -1 <> IF
          OVER 4 * PARENT-OF + !
          FB-IS-DIR? IF
            DUP FB-ADD-DIR
          THEN
          DROP EXIT
        ELSE DROP THEN
      THEN
    THEN
  THEN
  \ All failure paths converge here:
  DUP 4 * PARENT-OF + -1 SWAP ! DROP ;

\ ============================================
\ Phase 1b: Count-sort (Step 3e)
\ ============================================
\ Transforms PARENT-OF into SORTED/DIR-START/
\ DIR-COUNT triple. Three sub-passes: count,
\ prefix-sum, fill. FILL-CUR is a scratch
\ copy of DIR-START used as insertion cursor
\ during fill, leaving DIR-START immutable.

\ Linear search DIR-LIST for rec#.
: DIR-INDEX ( rec# -- idx | -1 )
  FB-NDIRS @ DUP 0= IF
    DROP DROP -1 EXIT
  THEN
  0 DO
    DUP I 4 * DIR-LIST + @ = IF
      DROP I UNLOOP EXIT
    THEN
  LOOP
  DROP -1 ;

\ Sub-pass A: zero DIR-COUNT, then tally
\ children per directory.
: FB-COUNT-PASS ( -- )
  DIR-COUNT FB-NDIRS @ 4 * ERASE
  FB-TOTAL @ DUP 0> IF
    0 DO
      I 4 * PARENT-OF + @
      DUP -1 <> IF
        DIR-INDEX DUP -1 <> IF
          4 * DIR-COUNT +
          DUP @ 1+ SWAP !
        ELSE DROP THEN
      ELSE DROP THEN
    LOOP
  ELSE DROP THEN ;

\ Sub-pass B: prefix-sum DIR-COUNT into
\ DIR-START. After this, DIR-START[j] is
\ the offset where dir j's children begin
\ in SORTED.
: FB-PREFIX-SUM ( -- )
  FB-NDIRS @ DUP 0> IF
    0 SWAP 0 DO
      DUP I 4 * DIR-START + !
      I 4 * DIR-COUNT + @ +
    LOOP
    DROP
  ELSE DROP THEN ;

\ Sub-pass C: copy DIR-START to FILL-CUR,
\ then walk PARENT-OF placing each child
\ at SORTED[cursor++]. Cursor mutation
\ leaves DIR-START intact.
: FB-FILL-PASS ( -- )
  FB-NDIRS @ DUP 0> IF
    0 DO
      I 4 * DIR-START + @
      I 4 * FILL-CUR + !
    LOOP
  ELSE DROP THEN
  FB-TOTAL @ DUP 0> IF
    0 DO
      I 4 * PARENT-OF + @
      DUP -1 <> IF
        DIR-INDEX DUP -1 <> IF
          4 * FILL-CUR +
          DUP @
          DUP 4 * SORTED +
          I SWAP !
          1+ SWAP !
        ELSE DROP THEN
      ELSE DROP THEN
    LOOP
  ELSE DROP THEN ;

\ Master count-sort.
: FB-SORT ( -- )
  FB-COUNT-PASS
  FB-PREFIX-SUM
  FB-FILL-PASS ;

DECIMAL

\ ---- Main mount word ----
\ Returns TRUE (-1) on success, FALSE (0) on
\ failure. Caller: FB-MOUNT IF ... ELSE ... THEN
: FB-MOUNT ( -- flag )
  FB-MEM-OK? 0= IF
    ." Mem check failed" CR 0 EXIT
  THEN
  ENSURE-AHCI
  NTFS-INIT
  MFT-COUNT DUP 0= IF
    DROP ." No MFT" CR 0 EXIT
  THEN
  FB-TOTAL !
  0 FB-NDIRS !
  NTFS-ROOT FB-ADD-DIR
  ." Scanning "
  FB-TOTAL @ . ." records" CR
  FB-TOTAL @ 0 DO
    I 1000 MOD 0= IF FB-SPIN THEN
    I FB-SCAN-ONE
  LOOP
  ." Found "
  FB-NDIRS @ . ." dirs" CR
  FB-SORT
  ." Sorted" CR
  -1 FB-MOUNTED !
  -1 ;

\ ============================================
\ Phase 2: Tree-populate + render
\ ============================================

HEX
70 CONSTANT ATTR-INV
DECIMAL

VARIABLE FB-DIRIDX
VARIABLE FB-ROW-TMP
VARIABLE FB-ATTR-TMP

\ Set up display state for FB-CWD.
: TREE-POPULATE ( -- )
  FB-CWD @ DIR-INDEX
  DUP -1 = IF
    DROP 0 FB-NCHILDREN ! EXIT
  THEN
  FB-DIRIDX !
  FB-DIRIDX @ 4 * DIR-COUNT + @
  FB-NCHILDREN !
  0 FB-TOP ! 0 FB-CURSOR ! ;

\ ---- Navigation helpers ----

: FB-UP ( -- )
  FB-CURSOR @ 0> IF
    -1 FB-CURSOR +!
  ELSE
    FB-TOP @ 0> IF
      -1 FB-TOP +!
    THEN
  THEN ;

: FB-DOWN ( -- )
  FB-NCHILDREN @ 0= IF EXIT THEN
  FB-CURSOR @ FB-TOP @ + 1+
  FB-NCHILDREN @ >= IF EXIT THEN
  FB-CURSOR @ FB-ROWS 1- < IF
    1 FB-CURSOR +!
  ELSE
    1 FB-TOP +!
  THEN ;

: FB-HOME ( -- )
  0 FB-TOP ! 0 FB-CURSOR ! ;

: FB-END ( -- )
  FB-NCHILDREN @ FB-ROWS -
  DUP 0> IF
    FB-TOP !
    FB-ROWS 1- FB-CURSOR !
  ELSE
    DROP 0 FB-TOP !
    FB-NCHILDREN @ 1-
    DUP 0< IF DROP 0 THEN
    FB-CURSOR !
  THEN ;

: FB-CURSOR-REC ( -- rec# )
  FB-CURSOR @ 4 * FB-VIEW + @ ;

\ Show message on VGA status row (row 23).
: FB-STATUS ( addr len -- )
  ATTR-NORM FB-STATUS-ROW VGA-CLR-ROW
  0 FB-STATUS-ROW ATTR-NORM DRAW-AT ;

\ Load resident file into FE-BUF for editing.
\ NTFS-READ-RESIDENT fills NTFS-SEC-BUF + FILE-SZ.
\ MAX-FILE (64KB) >> SEC-BUF (4KB), always fits.
: FB-OPEN-FILE ( rec# -- )
  MFT-READ DROP
  NTFS-READ-RESIDENT IF
    S" Non-resident file" FB-STATUS EXIT
  THEN
  FILE-SZ @ MAX-FILE MIN
  NTFS-SEC-BUF FE-BUF ROT CMOVE
  FILE-SZ @ MAX-FILE MIN FE-SIZE !
  FE-STRIP-ALL-CR
  0 FE-TOP ! 0 FE-CX ! 0 FE-CY !
  1 FB-EDIT-MODE !
  0 FB-TREE-MODE ! ;

: FB-ENTER ( -- )
  FB-CURSOR @ FB-ISDIR + C@ IF
    FB-CURSOR-REC
    FB-CWD ! TREE-POPULATE
  ELSE
    FB-CURSOR-REC FB-OPEN-FILE
  THEN ;

: FB-BACK ( -- )
  FB-CWD @ NTFS-ROOT = IF EXIT THEN
  FB-CWD @ 4 * PARENT-OF + @
  DUP -1 = IF DROP EXIT THEN
  FB-CWD ! TREE-POPULATE ;

: FB-ESC ( -- )
  0 FB-TREE-MODE ! ;

\ ---- Key dispatch ----

HEX

: TREE-KEY ( code type -- )
  IF
    DUP SC-UP = IF
      DROP FB-UP EXIT
    THEN
    DUP SC-DOWN = IF
      DROP FB-DOWN EXIT
    THEN
    DUP SC-HOME = IF
      DROP FB-HOME EXIT
    THEN
    DUP SC-END = IF
      DROP FB-END EXIT
    THEN
    \ HEX: 1C=Enter, 1=Esc, 0E=BS scancodes
    DUP 1C = IF
      DROP FB-ENTER EXIT
    THEN
    DUP 1 = IF
      DROP FB-ESC EXIT
    THEN
    DUP 0E = IF
      DROP FB-BACK EXIT
    THEN
    DROP
  ELSE DROP THEN ;

DECIMAL

\ ---- Row rendering ----
\ Render one visible row of the tree.
\ Uses VGA-CLR-ROW + DRAW-AT for display.

: FB-RENDER-ROW ( row -- )
  DUP FB-ROW-TMP !
  FB-CURSOR @ =
  IF ATTR-INV ELSE ATTR-NORM THEN
  FB-ATTR-TMP !
  FB-ATTR-TMP @
  FB-ROW-TMP @ FB-CONTENT-Y +
  VGA-CLR-ROW
  FB-ROW-TMP @ FB-TOP @ +
  DUP FB-NCHILDREN @ >= IF
    DROP EXIT
  THEN
  FB-DIRIDX @ 4 * DIR-START + @ +
  4 * SORTED + @
  DUP FB-ROW-TMP @ 4 * FB-VIEW + !
  MFT-READ DROP
  FB-IS-DIR? IF 1 ELSE 0 THEN
  DUP FB-ROW-TMP @ FB-ISDIR + C!
  IF
    S" [DIR] " 1
    FB-ROW-TMP @ FB-CONTENT-Y +
    FB-ATTR-TMP @ DRAW-AT
  THEN
  MFT-FILENAME
  DUP 0= IF 2DROP EXIT THEN
  73 MIN
  7 FB-ROW-TMP @ FB-CONTENT-Y +
  FB-ATTR-TMP @ DRAW-AT ;

\ ---- Full tree render ----

: TREE-RENDER ( -- )
  FB-ROWS 0 DO
    I FB-RENDER-ROW
  LOOP ;

\ ============================================
\ Phase 3: Edit mode + main loop
\ ============================================

\ Exit edit mode, return to tree view.
: FB-EXIT-EDIT ( -- )
  0 FB-EDIT-MODE !
  1 FB-TREE-MODE ! ;

\ Edit-mode key handler. ESC (scancode 1)
\ returns to tree mode. All other scancodes
\ go to the file-editor dispatcher.
: FB-EDITOR-KEY ( scancode -- )
  DUP 1 = IF
    DROP FB-EXIT-EDIT EXIT
  THEN
  FE-DISPATCH ;

\ ---- One iteration per mode ----
\ Factored out of the main loop to avoid
\ nested ELSE...IF...THEN THEN chains.

\ FE-KEY returns ( code type ).
\ type=1: scancode. type=0: ASCII char.
\ Edit mode: pass scancode to FB-EDITOR-KEY.
\ ASCII keys are silently consumed (2DROP).
: FB-LOOP-EDIT ( -- )
  FE-REFRESH FE-CURSOR FE-STATUS
  FE-KEY DUP 1 = IF
    DROP FB-EDITOR-KEY
  ELSE 2DROP THEN ;

\ Tree mode: pass both code+type to TREE-KEY
\ which handles scancodes and ASCII internally.
: FB-LOOP-TREE ( -- )
  TREE-RENDER
  FE-KEY TREE-KEY ;

\ Form mode: FE-KEY for PS/2 on bare metal.
\ type=0: ASCII char passed to HANDLE-KEY.
\ type=1: scancode (Esc=1 exits, rest ignored).
: FB-LOOP-FORM ( -- )
  FORM-RENDER
  FE-KEY IF
    1 = IF 1 QUIT-FLAG ! THEN
  ELSE
    HANDLE-KEY
  THEN ;

\ ---- Main loop ----

: FB-RUN ( -- )
  INIT-KEYMAP
  VGA-CLS
  FB-CONTENT-Y FB-ROWS FB-STATUS-ROW
  FE-SET-REGION
  0 QUIT-FLAG !
  0 FB-EDIT-MODE ! 1 FB-TREE-MODE !
  NTFS-ROOT FB-CWD !
  TREE-POPULATE
  0 NEXT-FOCUSABLE
  DUP 0< IF DROP 0 THEN FOCUS-IDX !
  BEGIN
    FB-EDIT-MODE @ IF FB-LOOP-EDIT
    ELSE FB-TREE-MODE @ IF FB-LOOP-TREE
    ELSE FB-LOOP-FORM
    THEN THEN
    NET-FLUSH QUIT-FLAG @
  UNTIL PAGE ;

\ ---- Entry point ----

: FILE-BROWSER-RUN ( -- )
  ." Loading File Browser..." CR
  S" FILE-BROWSER-FORM" CATALOG-FIND
  0= IF ." Form not found" CR EXIT THEN
  FORM-LOAD FORM-WIRE
  ." Mounting NTFS..." CR
  FB-MOUNT 0= IF
    ." Mount failed" CR EXIT
  THEN
  ." Ready" CR
  FB-RUN
  ." File Browser closed" CR ;

ONLY FORTH DEFINITIONS
DECIMAL
