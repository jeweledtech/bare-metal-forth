\ ============================================
\ CATALOG: MIRROR
\ CATEGORY: system
\ PLATFORM: x86
\ SOURCE: hand-written
\ CONFIDENCE: high
\ ============================================
\
\ Execution context serialization.
\ MIRROR saves the complete Forth environment
\ (dictionary, variables, stacks) to ATA
\ block storage. LOOKINGGLASS restores it.
\
\ Patterned after the VROOM mobile OS swap
\ technique (mentor design, Brenden Brown).
\
\ Usage:
\   USING MIRROR
\   900 MIRROR         \ Save to block 900+
\   ( power off, reboot, reload MIRROR )
\   900 LOOKINGGLASS   \ Restore environment
\
\ Saves: dictionary, kernel vars, search
\ order, data stack. Restores environment
\ to exact state, returns to interpreter.
\
\ ============================================

VOCABULARY MIRROR
MIRROR DEFINITIONS
HEX

\ ---- Magic and Version ----
464F5254 CONSTANT MIR-MAGIC
1 CONSTANT MIR-VER

\ ---- System variable addresses ----
\ These are kernel EQU addresses from
\ forth.asm — fixed memory locations.
28000 CONSTANT V-STATE
28004 CONSTANT V-HERE
28008 CONSTANT V-LATEST
2800C CONSTANT V-BASE
28018 CONSTANT V-BLK
2801C CONSTANT V-SCR
28020 CONSTANT V-SORDER
28040 CONSTANT V-SDEPTH
28044 CONSTANT V-CURRENT
28048 CONSTANT V-FLATEST
30000 CONSTANT DICT-BASE

\ ---- Header layout (offsets) ----
\ Block 0 of snapshot: 104-byte header
\ then stack data (depth * 4 bytes).
\
\ 00: Magic (4)
\ 04: Version (4)
\ 08: Source block# (4)
\ 0C: Tick count (4)
\ 10: HERE (4)
\ 14: LATEST (4)
\ 18: STATE (4)
\ 1C: BASE (4)
\ 20: Stack depth in cells (4)
\ 24: Dict size in bytes (4)
\ 28: Dict base address (4)
\ 2C: Search depth (4)
\ 30: Search order (8 * 4 = 20 hex)
\ 50: CURRENT (4)
\ 54: FORTH_LATEST (4)
\ 58: BLK (4)
\ 5C: SCR (4)
\ 60: Num dict blocks (4)
\ 64: Reserved (4)
\ 68: Stack data starts here

68 CONSTANT HDR-SZ
\ Max stack cells in header block
\ (400 hex - 68 hex) / 4 = 230 dec
E6 CONSTANT MAX-STK

\ ---- Staging buffer ----
\ One 1KB buffer for building/reading
\ header blocks before block I/O.
CREATE MIR-BUF 400 ALLOT

\ ---- Helper: clear staging buffer ----
: MIR-CLR  ( -- )
    MIR-BUF 400 0 FILL
;

\ ---- Helper: write cell to buffer ----
: MIR!  ( val offset -- )
    MIR-BUF + !
;

\ ---- Helper: read cell from buffer ----
: MIR@  ( offset -- val )
    MIR-BUF + @
;

\ ---- Helper: dict size in bytes ----
: DICT-SZ  ( -- bytes )
    V-HERE @ DICT-BASE -
;

\ ---- Helper: blocks needed for dict ----
: DICT-BLKS  ( -- n )
    DICT-SZ 3FF + A RSHIFT
;

\ ---- Helper: data stack depth ----
: STK-DEPTH  ( -- n )
    DEPTH 1-
;

\ ============================================
\ MIRROR - Save context to blocks
\ ============================================
\ Layout on disk:
\   block#+0: header + stack data
\   block#+1..N: dictionary data (1KB each)

: MIRROR  ( block# -- )
    MIR-CLR

    \ Build header in staging buffer
    MIR-MAGIC  0 MIR!
    MIR-VER    4 MIR!
    DUP        8 MIR!
    TICK-COUNT @ C MIR!
    V-HERE @   10 MIR!
    V-LATEST @ 14 MIR!
    V-STATE @  18 MIR!
    V-BASE @   1C MIR!

    \ Stack depth (exclude block# arg)
    STK-DEPTH
    DUP MAX-STK > IF
        DROP MAX-STK
    THEN
    DUP 20 MIR!

    \ Dictionary info
    DICT-SZ 24 MIR!
    DICT-BASE 28 MIR!

    \ Search order
    V-SDEPTH @ 2C MIR!
    8 0 DO
        V-SORDER I 4 * + @
        30 I 4 * + MIR!
    LOOP
    V-CURRENT @ 50 MIR!
    V-FLATEST @ 54 MIR!
    V-BLK @    58 MIR!
    V-SCR @    5C MIR!
    DICT-BLKS  60 MIR!
    0          64 MIR!

    \ Save data stack items into buffer
    \ Stack: ( block# stk-depth )
    \ Item 0 = top of saved stack
    \ We skip the top 2 (block# + depth)
    DUP 0> IF
        DUP 0 DO
            I 2 + PICK
            HDR-SZ I 4 * + MIR!
        LOOP
    THEN
    DROP

    \ Write header block
    DUP BUFFER
    MIR-BUF SWAP 400 MOVE
    UPDATE SAVE-BUFFERS

    \ Write dictionary blocks
    DICT-BLKS DUP 0> IF
        0 DO
            DUP 1+ I + BUFFER
            DICT-BASE I A LSHIFT +
            SWAP 400 MOVE
            UPDATE SAVE-BUFFERS
        LOOP
    ELSE
        DROP
    THEN

    ." MIRROR saved to block "
    DECIMAL . HEX CR
;

\ ============================================
\ MIRROR? - Check for valid snapshot
\ ============================================

: MIRROR?  ( block# -- flag )
    BLOCK
    DUP @ MIR-MAGIC = IF
        4 + @ MIR-VER =
    ELSE
        DROP FALSE
    THEN
;

\ ============================================
\ MIRROR-INFO - Print snapshot info
\ ============================================

: MIRROR-INFO  ( block# -- )
    DUP MIRROR? 0= IF
        DROP
        ." No valid MIRROR image" CR
        EXIT
    THEN
    BLOCK MIR-BUF 400 MOVE
    ." MIRROR snapshot info:" CR
    ."   Saved to block: "
    8 MIR@ DECIMAL . HEX CR
    ."   Tick count:     "
    C MIR@ DECIMAL . HEX CR
    ."   HERE:           "
    10 MIR@ . CR
    ."   LATEST:         "
    14 MIR@ . CR
    ."   BASE:           "
    1C MIR@ DECIMAL . HEX CR
    ."   Stack depth:    "
    20 MIR@ DECIMAL . HEX CR
    ."   Dict size:      "
    24 MIR@ DECIMAL . CR
    ."   Dict blocks:    "
    60 MIR@ . HEX CR
    ."   Search depth:   "
    2C MIR@ DECIMAL . HEX CR
;

\ ============================================
\ LOOKINGGLASS - Restore context
\ ============================================
\ Restores dictionary, variables, search
\ order, and data stack from a snapshot.
\ Returns to the interpreter loop after
\ restoring (does NOT resume mid-word).

: LOOKINGGLASS  ( block# -- )
    DUP MIRROR? 0= IF
        DROP
        ." No valid MIRROR image" CR
        EXIT
    THEN

    \ Read header into staging buffer
    DUP BLOCK MIR-BUF 400 MOVE

    \ Restore dictionary blocks first
    60 MIR@ DUP 0> IF
        0 DO
            OVER 1+ I + BLOCK
            DICT-BASE I A LSHIFT +
            400 MOVE
        LOOP
    ELSE
        DROP
    THEN
    DROP

    \ Restore kernel variables
    10 MIR@ V-HERE !
    14 MIR@ V-LATEST !
    18 MIR@ V-STATE !
    1C MIR@ V-BASE !
    58 MIR@ V-BLK !
    5C MIR@ V-SCR !

    \ Restore search order
    2C MIR@ V-SDEPTH !
    8 0 DO
        30 I 4 * + MIR@
        V-SORDER I 4 * + !
    LOOP
    50 MIR@ V-CURRENT !
    54 MIR@ V-FLATEST !

    \ Restore data stack
    \ First, clear current stack
    DEPTH 0> IF
        DEPTH 0 DO DROP LOOP
    THEN

    \ Push items in reverse order
    \ (bottom first, then up to top)
    20 MIR@ DUP 0> IF
        DUP 1- 0 SWAP DO
            HDR-SZ I 4 * + MIR@
            SWAP
        -1 +LOOP
        DROP
    ELSE
        DROP
    THEN

    ." LOOKINGGLASS restored" CR
    ."   HERE=" V-HERE @ . CR
    ."   Stack depth="
    DEPTH DECIMAL . HEX CR
;

." MIRROR vocabulary loaded" CR

FORTH DEFINITIONS
DECIMAL
