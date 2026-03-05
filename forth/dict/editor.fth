\ ============================================
\ CATALOG: EDITOR
\ CATEGORY: system
\ PLATFORM: x86
\ SOURCE: hand-written
\ CONFIDENCE: high
\ ============================================
\
\ Vi-like block editor.
\ Operates on 16x64 char block screens.
\ Uses serial KEY for input.
\
\ Usage:
\   USING EDITOR
\   3 EDIT
\   h/j/k/l=move i=insert x=del
\   dd=del-line yy=yank p=paste
\   u=undo :w=save :q=quit
\   Esc=back to command mode
\
\ ============================================

VOCABULARY EDITOR
EDITOR DEFINITIONS
HEX

\ ---- Constants (defined in HEX) ----
10 CONSTANT BLK-LINES
40 CONSTANT BLK-COLS
50 CONSTANT VGA-COLS
B8000 CONSTANT VGA-BASE
11 CONSTANT STATUS-ROW

\ ---- Editor state ----
VARIABLE ED-BLK
VARIABLE ED-ROW
VARIABLE ED-COL
VARIABLE ED-MODE
VARIABLE ED-DIRTY
VARIABLE ED-QUIT
VARIABLE ED-D-FLAG
CREATE ED-YANK 40 ALLOT
CREATE ED-UNDO 400 ALLOT

\ ---- Block buffer helpers ----
: ED-BUF ( -- addr )
    ED-BLK @ BLOCK
;

: ED-LINE ( row -- addr )
    BLK-COLS * ED-BUF +
;

: ED-CHAR@ ( col row -- char )
    ED-LINE + C@
;

: ED-CHAR! ( char col row -- )
    ED-LINE + C!
    1 ED-DIRTY !
;

\ ---- Undo (single level) ----
: ED-SAVE-UNDO ( -- )
    ED-BUF ED-UNDO 400 CMOVE
;

: ED-UNDO! ( -- )
    ED-UNDO ED-BUF 400 CMOVE
    1 ED-DIRTY !
;

\ ---- VGA text output ----
: VGA-AT ( col row -- addr )
    VGA-COLS * + 2 * VGA-BASE +
;

: VGA-PUTC ( char attr col row -- )
    VGA-AT
    ROT OVER C!
    SWAP 1+ C!
;

\ ---- Clear one VGA row ----
VARIABLE CLR-ROW
: VGA-CLR ( attr row -- )
    CLR-ROW !
    VGA-COLS 0 DO
        20 OVER I CLR-ROW @ VGA-PUTC
    LOOP
    DROP
;

\ ---- Draw one block line to VGA ----
VARIABLE DL-LINE
: ED-DRAW-LINE ( line# -- )
    DUP DL-LINE !
    ED-LINE
    BLK-COLS 0 DO
        DUP I + C@
        07 I DL-LINE @ VGA-PUTC
    LOOP
    DROP
;

\ ---- Status bar ----
: ED-STATUS ( -- )
    70 STATUS-ROW VGA-CLR
    \ "B" + block number via serial
    42 70 0 STATUS-ROW VGA-PUTC
    3A 70 1 STATUS-ROW VGA-PUTC
    \ Mode indicator
    ED-MODE @ 0= IF
        43 70 A STATUS-ROW VGA-PUTC
        4D 70 B STATUS-ROW VGA-PUTC
        44 70 C STATUS-ROW VGA-PUTC
    THEN
    ED-MODE @ 1 = IF
        49 70 A STATUS-ROW VGA-PUTC
        4E 70 B STATUS-ROW VGA-PUTC
        53 70 C STATUS-ROW VGA-PUTC
    THEN
    \ Dirty flag
    ED-DIRTY @ IF
        2B 70 F STATUS-ROW VGA-PUTC
    THEN
;

\ ---- Refresh all 16 lines + status ----
: ED-REFRESH ( -- )
    BLK-LINES 0 DO
        I ED-DRAW-LINE
    LOOP
    ED-STATUS
;

\ ---- Hardware cursor ----
: ED-CURSOR ( -- )
    ED-ROW @ VGA-COLS * ED-COL @ +
    DUP FF AND
    0F 3D4 OUTB 3D5 OUTB
    8 RSHIFT
    0E 3D4 OUTB 3D5 OUTB
;

\ ---- Movement ----
: ED-LEFT
    ED-COL @ 0 > IF -1 ED-COL +! THEN
;
: ED-RIGHT
    ED-COL @ BLK-COLS 1- < IF
        1 ED-COL +!
    THEN
;
: ED-UP
    ED-ROW @ 0 > IF -1 ED-ROW +! THEN
;
: ED-DOWN
    ED-ROW @ BLK-LINES 1- < IF
        1 ED-ROW +!
    THEN
;
: ED-HOME 0 ED-COL ! ;
: ED-END BLK-COLS 1- ED-COL ! ;

\ ---- Delete char at cursor ----
: ED-DEL-CHAR ( -- )
    ED-SAVE-UNDO
    ED-ROW @ ED-LINE ED-COL @ +
    DUP 1+ SWAP
    BLK-COLS ED-COL @ - 1-
    DUP 0> IF
        CMOVE
    ELSE
        DROP 2DROP
    THEN
    20 BLK-COLS 1- ED-ROW @ ED-CHAR!
    ED-ROW @ ED-DRAW-LINE
;

\ ---- Delete line (dd) ----
VARIABLE DD-I
: ED-DEL-LINE ( -- )
    ED-SAVE-UNDO
    ED-ROW @ ED-LINE
    ED-YANK BLK-COLS CMOVE
    ED-ROW @ DD-I !
    BEGIN
        DD-I @ BLK-LINES 2 - <=
    WHILE
        DD-I @ 1+ ED-LINE
        DD-I @ ED-LINE
        BLK-COLS CMOVE
        1 DD-I +!
    REPEAT
    BLK-LINES 1- ED-LINE
    BLK-COLS 20 FILL
    1 ED-DIRTY !
    ED-REFRESH
;

\ ---- Yank line (yy) ----
VARIABLE YY-FLAG
: ED-YANK-LINE ( -- )
    ED-ROW @ ED-LINE
    ED-YANK BLK-COLS CMOVE
;

\ ---- Paste below (p) ----
: ED-PASTE ( -- )
    ED-SAVE-UNDO
    BLK-LINES 2 - DD-I !
    BEGIN
        DD-I @ ED-ROW @ >
    WHILE
        DD-I @ ED-LINE
        DD-I @ 1+ ED-LINE
        BLK-COLS CMOVE
        -1 DD-I +!
    REPEAT
    ED-YANK
    ED-ROW @ 1+ ED-LINE
    BLK-COLS CMOVE
    1 ED-DIRTY !
    ED-ROW @ BLK-LINES 2 - < IF
        1 ED-ROW +!
    THEN
    ED-REFRESH
;

\ ---- Insert char at cursor ----
: ED-INS-CHAR ( char -- )
    ED-COL @ BLK-COLS 1- >= IF
        DROP EXIT
    THEN
    ED-SAVE-UNDO
    ED-ROW @ ED-LINE
    DUP BLK-COLS + 1-
    DUP 1-
    BLK-COLS ED-COL @ - 1-
    DUP 0> IF
        CMOVE>
    ELSE
        DROP 2DROP
    THEN
    ED-COL @ ED-ROW @ ED-CHAR!
    1 ED-COL +!
    ED-ROW @ ED-DRAW-LINE
;

\ ---- Backspace ----
: ED-BS ( -- )
    ED-COL @ 0= IF EXIT THEN
    -1 ED-COL +!
    ED-DEL-CHAR
;

\ ---- Save ----
: ED-SAVE ( -- )
    ED-DIRTY @ IF
        UPDATE SAVE-BUFFERS
        0 ED-DIRTY !
        ED-STATUS
    THEN
;

\ ---- Ex-mode (:w :q) ----
: ED-EX ( -- )
    KEY
    DUP 77 = IF
        DROP ED-SAVE
        0 ED-MODE ! EXIT
    THEN
    DUP 71 = IF
        DROP 1 ED-QUIT !
        0 ED-MODE ! EXIT
    THEN
    DROP 0 ED-MODE !
;

\ ---- Command mode ----
: ED-CMD ( char -- )
    DUP 68 = IF DROP ED-LEFT  EXIT THEN
    DUP 6A = IF DROP ED-DOWN  EXIT THEN
    DUP 6B = IF DROP ED-UP    EXIT THEN
    DUP 6C = IF DROP ED-RIGHT EXIT THEN
    DUP 30 = IF DROP ED-HOME  EXIT THEN
    DUP 24 = IF DROP ED-END   EXIT THEN
    DUP 69 = IF
        DROP 1 ED-MODE ! EXIT
    THEN
    DUP 78 = IF
        DROP ED-DEL-CHAR EXIT
    THEN
    DUP 64 = IF
        DROP ED-D-FLAG @ IF
            ED-DEL-LINE
            0 ED-D-FLAG !
        ELSE
            1 ED-D-FLAG !
        THEN EXIT
    THEN
    DUP 79 = IF
        DROP YY-FLAG @ IF
            ED-YANK-LINE
            0 YY-FLAG !
        ELSE
            1 YY-FLAG !
        THEN EXIT
    THEN
    DUP 70 = IF
        DROP ED-PASTE EXIT
    THEN
    DUP 75 = IF
        DROP ED-UNDO! ED-REFRESH EXIT
    THEN
    DUP 3A = IF
        DROP 2 ED-MODE ! ED-EX EXIT
    THEN
    DROP
    0 ED-D-FLAG !
    0 YY-FLAG !
;

\ ---- Insert mode ----
: ED-INSERT ( char -- )
    DUP 1B = IF
        DROP 0 ED-MODE ! EXIT
    THEN
    DUP 08 = IF
        DROP ED-BS EXIT
    THEN
    DUP 0D = IF
        DROP
        ED-ROW @ BLK-LINES 1- < IF
            1 ED-ROW +! 0 ED-COL !
        THEN EXIT
    THEN
    DUP 20 < IF DROP EXIT THEN
    ED-INS-CHAR
;

\ ---- Main loop ----
: ED-LOOP ( -- )
    BEGIN
        ED-CURSOR ED-STATUS
        KEY
        ED-MODE @ 0= IF
            ED-CMD
        ELSE
            ED-MODE @ 1 = IF
                ED-INSERT
            THEN
        THEN
        ED-QUIT @
    UNTIL
;

\ ---- Entry point ----
: EDIT ( blk# -- )
    ED-BLK !
    ED-BUF DROP
    0 ED-ROW ! 0 ED-COL !
    0 ED-MODE ! 0 ED-DIRTY !
    0 ED-QUIT ! 0 ED-D-FLAG !
    0 YY-FLAG !
    ED-SAVE-UNDO
    ED-REFRESH
    ED-LOOP
;

FORTH DEFINITIONS
DECIMAL
