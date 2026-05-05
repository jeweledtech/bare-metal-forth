\ ============================================
\ CATALOG: FILE-EDITOR
\ CATEGORY: system
\ PLATFORM: x86
\ SOURCE: hand-written
\ REQUIRES: NTFS AHCI HARDWARE
\ CONFIDENCE: medium
\ ============================================
\
\ Text file editor for NTFS files.
\ Reads file into 64KB buffer, edits with
\ VGA direct writes, saves back via AHCI.
\
\ Usage:
\   USING FILE-EDITOR
\   NTFS-ENABLE-WRITE
\   S" hello.txt" FILE-EDIT
\
\ Arrow keys, Home, End, PgUp, PgDn.
\ Ctrl+S = save, Ctrl+Q = quit.
\ Insert/delete/backspace/Enter.
\
\ ============================================

VOCABULARY FILE-EDITOR
FILE-EDITOR DEFINITIONS
ALSO NTFS
ALSO AHCI
ALSO HARDWARE
ALSO PS2-KEYBOARD
HEX

\ ============================================
\ Constants
\ ============================================

B8000 CONSTANT FE-VGA
50 CONSTANT VCOLS
18 CONSTANT VROWS
10000 CONSTANT MAX-FILE
0A CONSTANT LF-CHAR
20 CONSTANT SPC-CHAR

\ PS/2 scancodes for special keys
48 CONSTANT SC-UP
50 CONSTANT SC-DOWN
4B CONSTANT SC-LEFT
4D CONSTANT SC-RIGHT
47 CONSTANT SC-HOME
4F CONSTANT SC-END
49 CONSTANT SC-PGUP
51 CONSTANT SC-PGDN
53 CONSTANT SC-DEL

\ Ctrl key scancodes
13 CONSTANT SC-CTRL-S
10 CONSTANT SC-CTRL-Q

\ ============================================
\ Buffers and state
\ ============================================

CREATE FE-BUF MAX-FILE ALLOT
VARIABLE FE-SIZE
VARIABLE FE-CX
VARIABLE FE-CY
VARIABLE FE-TOP
VARIABLE FE-DIRTY
VARIABLE FE-QUIT
CREATE FE-NAME 100 ALLOT
VARIABLE FE-NLEN

\ ---- Sub-region support -------------------
\ Allows editor to render in a screen sub-area
\ (e.g. rows 8-21 inside NOTEPAD form).
VARIABLE FE-RGN-Y    \ first screen row
VARIABLE FE-RGN-H    \ visible row count
VARIABLE FE-SB-ROW   \ status bar screen row

: FE-SET-REGION ( y h sb-row -- )
  FE-SB-ROW ! FE-RGN-H ! FE-RGN-Y ! ;

: FE-INIT-FULL ( -- )
  0 VROWS VROWS FE-SET-REGION ;

FE-INIT-FULL

\ ============================================
\ Raw keyboard input
\ ============================================
\ KEY silently discards scancodes 0x40+.
\ RAW-SCAN reads directly from the ring
\ buffer to get arrow keys, etc.

VARIABLE RS-CODE
VARIABLE RS-TYPE

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

\ Translate scancode to ASCII or special
\ Returns: ( char 0 ) for ASCII
\          ( scancode 1 ) for special key

: FE-KEY ( -- code type )
    BEGIN
        RAW-SCAN
        DUP 0= IF 2DROP ELSE EXIT THEN
    AGAIN
;

\ ============================================
\ Line utilities
\ ============================================

VARIABLE LS-OFF

: LINE-START ( line# -- offset )
    0 LS-OFF !
    DUP 0= IF DROP 0 EXIT THEN
    FE-SIZE @ 0= IF DROP 0 EXIT THEN
    0 DO
        LS-OFF @
        FE-SIZE @ >= IF
            FE-SIZE @ LS-OFF !
            LEAVE
        THEN
        BEGIN
            LS-OFF @
            FE-SIZE @ >= IF LEAVE THEN
            FE-BUF LS-OFF @ + C@
            1 LS-OFF +!
            LF-CHAR =
        UNTIL
    LOOP
    LS-OFF @
;

: FE-LINE-LEN ( line# -- n )
    LINE-START DROP
    0
    BEGIN
        LS-OFF @ FE-SIZE @ >= IF
            EXIT
        THEN
        FE-BUF LS-OFF @ + C@
        LF-CHAR = IF EXIT THEN
        1 LS-OFF +!
        1+
    AGAIN
;

: TOTAL-LINES ( -- n )
    FE-SIZE @ 0= IF 1 EXIT THEN
    1
    FE-SIZE @ 0 DO
        FE-BUF I + C@ LF-CHAR = IF
            1+
        THEN
    LOOP
;

\ ============================================
\ VGA display
\ ============================================

: VGA-AT ( col row -- addr )
    VCOLS * + 2 * FE-VGA +
;

: VGA-PUTC ( ch attr col row -- )
    VGA-AT
    ROT OVER C!
    SWAP 1+ C!
;

: VGA-CLR-ROW ( attr row -- )
    VCOLS 0 DO
        SPC-CHAR OVER I 3 PICK VGA-PUTC
    LOOP
    2DROP
;

: FE-SHOW-LINE ( rel-row -- )
    DUP FE-TOP @ +
    DUP TOTAL-LINES >= IF
        DROP                    \ ( rr )
        FE-RGN-Y @ +           \ rr -> abs-row
        07 SWAP VGA-CLR-ROW EXIT
    THEN
    DUP LINE-START SWAP FE-LINE-LEN
    ROT FE-RGN-Y @ +           \ rr -> abs-row
    07 OVER VGA-CLR-ROW
    OVER VCOLS MIN 0 DO
        FE-BUF 3 PICK I + + C@
        07 I 3 PICK VGA-PUTC   \ 3 PICK = ar
    LOOP
    DROP 2DROP
;

: FE-REFRESH ( -- )
    FE-RGN-H @ 0 DO
        I FE-SHOW-LINE
    LOOP
;

\ ---- Status bar (row 24) ----
VARIABLE SB-COL

: SB-EMIT ( char -- )
    70 SB-COL @ FE-SB-ROW @ VGA-PUTC
    1 SB-COL +!
;

: SB-STR ( addr len -- )
    0 DO
        DUP I + C@ SB-EMIT
    LOOP
    DROP
;

: SB-NUM ( n -- )
    DUP 0< IF 2D SB-EMIT NEGATE THEN
    DUP 0= IF DROP 30 SB-EMIT EXIT THEN
    0 SWAP
    BEGIN DUP WHILE
        DUP A MOD 30 + -ROT
        A / SWAP 1+ SWAP
    REPEAT
    DROP
    0 DO SB-EMIT LOOP
;

: FE-STATUS ( -- )
    70 FE-SB-ROW @ VGA-CLR-ROW
    0 SB-COL !
    FE-NAME FE-NLEN @ SB-STR
    SPC-CHAR SB-EMIT SPC-CHAR SB-EMIT
    4C SB-EMIT 6E SB-EMIT
    FE-CY @ FE-TOP @ + 1+
    DECIMAL SB-NUM HEX
    SPC-CHAR SB-EMIT
    43 SB-EMIT 6F SB-EMIT 6C SB-EMIT
    FE-CX @ 1+
    DECIMAL SB-NUM HEX
    FE-DIRTY @ IF
        SPC-CHAR SB-EMIT
        2A SB-EMIT
    THEN
;

\ ---- Hardware cursor ----
: FE-CURSOR ( -- )
    FE-CY @ FE-RGN-Y @ + VCOLS * FE-CX @ +
    DUP FF AND
    0F 3D4 OUTB 3D5 OUTB
    8 RSHIFT
    0E 3D4 OUTB 3D5 OUTB
;

\ ============================================
\ Cursor movement
\ ============================================

: FE-LINE# ( -- n )
    FE-CY @ FE-TOP @ +
;

: CUR-FE-LINE-LEN ( -- n )
    FE-LINE# FE-LINE-LEN
;

: FE-CLAMP-X ( -- )
    FE-CX @ CUR-FE-LINE-LEN >= IF
        CUR-FE-LINE-LEN
        DUP 0> IF 1- THEN
        FE-CX !
    THEN
;

: FE-UP ( -- )
    FE-CY @ 0> IF
        -1 FE-CY +! FE-CLAMP-X EXIT
    THEN
    FE-TOP @ 0> IF
        -1 FE-TOP +! FE-REFRESH
        FE-CLAMP-X
    THEN
;

: FE-DOWN ( -- )
    FE-LINE# 1+ TOTAL-LINES >= IF
        EXIT
    THEN
    FE-CY @ FE-RGN-H @ 1- < IF
        1 FE-CY +! FE-CLAMP-X EXIT
    THEN
    1 FE-TOP +! FE-REFRESH
    FE-CLAMP-X
;

: FE-LEFT ( -- )
    FE-CX @ 0> IF -1 FE-CX +! THEN
;

: FE-RIGHT ( -- )
    FE-CX @ CUR-FE-LINE-LEN 1- < IF
        1 FE-CX +!
    THEN
;

: FE-HOME ( -- ) 0 FE-CX ! ;

: FE-EEND ( -- )
    CUR-FE-LINE-LEN
    DUP 0> IF 1- THEN
    FE-CX !
;

: FE-PGUP ( -- )
    FE-TOP @ FE-RGN-H @ >= IF
        FE-RGN-H @ NEGATE FE-TOP +!
    ELSE
        0 FE-TOP !
    THEN
    FE-CLAMP-X FE-REFRESH
;

: FE-PGDN ( -- )
    FE-TOP @ FE-RGN-H @ + TOTAL-LINES < IF
        FE-RGN-H @ FE-TOP +!
        FE-CLAMP-X FE-REFRESH
    THEN
;

\ ============================================
\ Editing operations
\ ============================================

\ Buffer offset for cursor position
: CUR-OFF ( -- offset )
    FE-LINE# LINE-START FE-CX @ +
;

\ Insert byte at offset, shift right
: BUF-INS ( char offset -- )
    FE-SIZE @ MAX-FILE 1- >= IF
        2DROP EXIT
    THEN
    DUP FE-BUF +
    DUP 1+
    FE-SIZE @ OVER FE-BUF - -
    DUP 0> IF
        CMOVE>
    ELSE
        DROP 2DROP
    THEN
    FE-BUF + C!
    1 FE-SIZE +!
    1 FE-DIRTY !
;

\ Delete byte at offset, shift left
: BUF-DEL ( offset -- )
    FE-SIZE @ 0= IF DROP EXIT THEN
    DUP FE-SIZE @ >= IF
        DROP EXIT
    THEN
    DUP FE-BUF + 1+
    OVER FE-BUF +
    FE-SIZE @ OVER FE-BUF - 1+ -
    DUP 0> IF
        CMOVE
    ELSE
        DROP 2DROP
    THEN
    DROP
    -1 FE-SIZE +!
    1 FE-DIRTY !
;

: FE-INSERT ( char -- )
    CUR-OFF BUF-INS
    1 FE-CX +!
    FE-REFRESH
;

: FE-DELETE ( -- )
    CUR-OFF
    DUP FE-SIZE @ >= IF
        DROP EXIT
    THEN
    BUF-DEL FE-REFRESH
;

: FE-BACKSPACE ( -- )
    FE-CX @ 0= IF
        FE-LINE# 0= IF EXIT THEN
        FE-UP FE-EEND
        FE-CX @ 1+ FE-CX !
        CUR-OFF BUF-DEL
        FE-REFRESH EXIT
    THEN
    -1 FE-CX +!
    CUR-OFF BUF-DEL
    FE-REFRESH
;

: FE-ENTER ( -- )
    LF-CHAR CUR-OFF BUF-INS
    0 FE-CX !
    FE-DOWN
    FE-REFRESH
;

\ ============================================
\ File I/O
\ ============================================

\ Strip CR bytes when followed by LF (CRLF->LF)
VARIABLE CR-I
: FE-STRIP-CR ( -- )
    0 CR-I !
    BEGIN
        CR-I @ FE-SIZE @ 1- <
    WHILE
        FE-BUF CR-I @ + DUP C@
        D = IF
            DUP 1+ C@ A = IF
                DUP DUP 1+
                SWAP
                FE-SIZE @
                CR-I @ - 1-
                CMOVE
                DROP
                -1 FE-SIZE +!
            ELSE
                DROP 1 CR-I +!
            THEN
        ELSE
            DROP 1 CR-I +!
        THEN
    REPEAT ;

: FE-OPEN ( na nl -- )
    DUP FE-NLEN !
    FE-NAME SWAP CMOVE
    FE-BUF MAX-FILE 0 FILL
    0 FE-SIZE !
    FE-NAME FE-NLEN @
    FILE-READ IF
        ." Open err" CR EXIT
    THEN
    SEC-BUF FE-BUF 1000 CMOVE
    FILE-SZ @ 1000 MIN FE-SIZE !
    FE-STRIP-CR
;

: FE-SAVE ( -- )
    FE-DIRTY @ 0= IF EXIT THEN
    FE-SIZE @ 1000 > IF
        ." File too large (>4KB)" CR
        EXIT
    THEN
    FE-BUF FE-SIZE @
    FE-NAME FE-NLEN @
    NTFS-WRITE-FILE IF
        ." Save err" CR EXIT
    THEN
    0 FE-DIRTY !
    ." Saved" CR
;

\ ============================================
\ Key dispatch
\ ============================================

\ Scancode-to-ASCII (basic, for typing)
CREATE SC-ASC 80 ALLOT
: INIT-KEYMAP ( -- )
    SC-ASC 80 0 FILL
    \ Row 0: Esc=1B, 1-9,0,-,=, BS=08, Tab
    1B 1 SC-ASC + C!
    31 2 SC-ASC + C!
    32 3 SC-ASC + C!
    33 4 SC-ASC + C!
    34 5 SC-ASC + C!
    35 6 SC-ASC + C!
    36 7 SC-ASC + C!
    37 8 SC-ASC + C!
    38 9 SC-ASC + C!
    39 0A SC-ASC + C!
    30 0B SC-ASC + C!
    2D 0C SC-ASC + C!
    3D 0D SC-ASC + C!
    08 0E SC-ASC + C!
    \ Row 1: q-p,[,], Enter
    71 10 SC-ASC + C!
    77 11 SC-ASC + C!
    65 12 SC-ASC + C!
    72 13 SC-ASC + C!
    74 14 SC-ASC + C!
    79 15 SC-ASC + C!
    75 16 SC-ASC + C!
    69 17 SC-ASC + C!
    6F 18 SC-ASC + C!
    70 19 SC-ASC + C!
    5B 1A SC-ASC + C!
    5D 1B SC-ASC + C!
    0D 1C SC-ASC + C!
    \ Row 2: a-l,;,',`
    61 1E SC-ASC + C!
    73 1F SC-ASC + C!
    64 20 SC-ASC + C!
    66 21 SC-ASC + C!
    67 22 SC-ASC + C!
    68 23 SC-ASC + C!
    6A 24 SC-ASC + C!
    6B 25 SC-ASC + C!
    6C 26 SC-ASC + C!
    3B 27 SC-ASC + C!
    27 28 SC-ASC + C!
    60 29 SC-ASC + C!
    \ Row 3: \,z-m,.,/
    5C 2B SC-ASC + C!
    7A 2C SC-ASC + C!
    78 2D SC-ASC + C!
    63 2E SC-ASC + C!
    76 2F SC-ASC + C!
    62 30 SC-ASC + C!
    6E 31 SC-ASC + C!
    6D 32 SC-ASC + C!
    2C 33 SC-ASC + C!
    2E 34 SC-ASC + C!
    2F 35 SC-ASC + C!
    \ Space
    20 39 SC-ASC + C!
;

: FE-DISPATCH ( scancode -- )
    DUP SC-UP    = IF DROP FE-UP     EXIT THEN
    DUP SC-DOWN  = IF DROP FE-DOWN   EXIT THEN
    DUP SC-LEFT  = IF DROP FE-LEFT   EXIT THEN
    DUP SC-RIGHT = IF DROP FE-RIGHT  EXIT THEN
    DUP SC-HOME  = IF DROP FE-HOME   EXIT THEN
    DUP SC-END   = IF DROP FE-EEND   EXIT THEN
    DUP SC-PGUP  = IF DROP FE-PGUP   EXIT THEN
    DUP SC-PGDN  = IF DROP FE-PGDN   EXIT THEN
    DUP SC-DEL   = IF DROP FE-DELETE EXIT THEN
    \ Ctrl+S / Ctrl+Q (only when Ctrl held)
    KB-MODS @ 2 AND IF
      DUP 1F = IF DROP FE-SAVE EXIT THEN
      DUP 10 = IF
        DROP 1 FE-QUIT ! EXIT
      THEN
    THEN
    \ Backspace
    DUP 0E = IF
        DROP FE-BACKSPACE EXIT
    THEN
    \ Enter
    DUP 1C = IF
        DROP FE-ENTER EXIT
    THEN
    \ Printable: translate scancode to ASCII
    DUP 80 < IF
        KB-MODS @ 1 AND IF
            KB-SHIFT-MAP
        ELSE SC-ASC THEN
        + C@
        DUP 0<> IF
            DUP 08 = IF
                DROP FE-BACKSPACE EXIT
            THEN
            DUP 0D = IF
                DROP FE-ENTER EXIT
            THEN
            DUP 1B = IF
                DROP EXIT
            THEN
            DUP 20 < IF
                DROP EXIT
            THEN
            FE-INSERT EXIT
        THEN
        DROP EXIT
    THEN
    DROP
;

\ Exposes Ctrl-held state to NOTEPAD without
\ forcing PS2-KEYBOARD onto its search order
: FE-CTRL? ( -- flag ) KB-MODS @ 2 AND ;

\ ============================================
\ Main loop
\ ============================================

: FE-LOOP ( -- )
    0 FE-QUIT !
    BEGIN
        FE-CURSOR FE-STATUS
        FE-KEY
        DUP 1 = IF
            DROP FE-DISPATCH
        ELSE
            2DROP
        THEN
        FE-QUIT @
    UNTIL
;

\ ============================================
\ Entry point
\ ============================================

: FE-CLEANUP ( -- )
    PAGE
;

: FILE-EDIT ( na nl -- )
    FE-INIT-FULL INIT-KEYMAP
    2DUP FE-OPEN
    0 FE-CX ! 0 FE-CY !
    0 FE-TOP ! 0 FE-DIRTY !
    FE-REFRESH
    FE-LOOP
    FE-CLEANUP
;

ONLY FORTH DEFINITIONS
DECIMAL
