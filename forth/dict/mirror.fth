\ ============================================
\ CATALOG: MIRROR
\ CATEGORY: system
\ PLATFORM: x86
\ SOURCE: hand-written
\ CONFIDENCE: high
\ REQUIRES: CATALOG-RESOLVER ( VOC-WORD )
\ ============================================
\
\ Execution context serialization.
\ MIRROR saves the complete Forth environment
\ (dictionary, variables, stacks) through
\ the block-write vector. LOOKINGGLASS
\ restores it through the persistent reader.
\
\ Patterned after the VROOM mobile OS swap
\ technique (mentor design, Brenden Brown).
\
\ Usage:
\   USING MIRROR
\   MIRROR-BLK MIRROR        \ save
\   ( power off, reboot, reload MIRROR )
\   MIRROR-BLK LOOKINGGLASS  \ restore
\
\ MIRROR-BLK..MIRROR-END (216-535) is the
\ range write-catalog reserves for it. Any
\ block# is allowed, but MIRROR refuses one
\ whose image would overlap the code store
\ or a disk partition, naming each overlap,
\ and writes nothing. It writes around the
\ block cache, one vector call per block,
\ and says MIRROR FAILED if any write did.
\
\ Saves: dictionary, kernel vars, search
\ order, data stack. Restores environment
\ to exact state, returns to interpreter.
\
\ ============================================

VOCABULARY MIRROR
MIRROR DEFINITIONS
ALSO CATALOG-RESOLVER
HEX

\ ---- Reserved range (write-catalog.py
\ MIRROR_RESERVED, MIRROR_BLK) ----
D8 CONSTANT MIRROR-BLK
217 CONSTANT MIRROR-END

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


\ ---- Printing, base-independent ----
\ u in decimal, no trailing space
: MR-N.  ( u -- )
    DUP 9 > IF DUP A / RECURSE THEN
    A MOD 30 + EMIT
;
\ a-b
: MR-RNG  ( a b -- )
    SWAP MR-N. 2D EMIT MR-N.
;
\ u in hex, trailing space
: MR-H.  ( u -- )
    BASE @ SWAP HEX . BASE !
;

\ ---- Refusal ----
\ The image's block range, the refusal
\ header flag, and the partition-check
\ xt: PG-WHICH, looked up on each call
\ and never kept past it.
VARIABLE MR-FIRST
VARIABLE MR-LAST
VARIABLE MR-HIT
VARIABLE MR-PW
VARIABLE MR-PF

\ Header once, then each overlap after it
: MR-REFUSE  ( -- )
    MR-HIT @ 0= IF
        ." MIRROR REFUSED: blocks "
        MR-FIRST @ MR-LAST @ MR-RNG
        ."  overlap"
        -1 MR-HIT !
    THEN
;

\ Size: an image starting inside the
\ reserved range must end inside it.
: MR-FITS?  ( -- flag )
    MR-FIRST @ MIRROR-BLK < 0=
    MR-FIRST @ MIRROR-END > 0= AND
    MR-LAST @ MIRROR-END > AND IF
        ." MIRROR REFUSED: image of "
        MR-LAST @ MR-FIRST @ - 1+ MR-N.
        ."  blocks does not fit blocks "
        MIRROR-BLK MIRROR-END MR-RNG CR
        FALSE EXIT
    THEN
    TRUE
;

\ ---- Code store: name every vocabulary
\ whose catalog blocks overlap ----
VARIABLE MC-WS
VARIABLE MC-WL

\ One catalog line: its name, first and
\ last block and TRUE, or FALSE if blank.
: MC-LINE  ( addr -- ws wl s e T | F )
    DUP 40 + >R
    BEGIN DUP C@ 20 = OVER R@ < AND
    WHILE 1+ REPEAT
    DUP R@ < 0= OVER C@ 20 < OR IF
        DROP R> DROP FALSE EXIT
    THEN
    DUP MC-WS !
    BEGIN DUP C@ 20 <> OVER R@ < AND
    WHILE 1+ REPEAT
    DUP MC-WS @ - MC-WL !
    BEGIN DUP C@ 20 = WHILE 1+ REPEAT
    CF-PARSE-NUM >R
    BEGIN DUP C@ 20 = WHILE 1+ REPEAT
    CF-PARSE-NUM NIP
    R> SWAP R> DROP
    MC-WS @ MC-WL @ 2SWAP TRUE
;

: MC-SCAN  ( -- )
    CATALOG-BLK
    BEGIN
        DUP CATALOG-BLK - CAT-MAXBLKS <
        IF DUP BLOCK CAT-HDR? ELSE FALSE THEN
    WHILE
        10 1 DO
            DUP BLOCK I 40 * + MC-LINE IF
                OVER MR-LAST @ > 0=
                OVER MR-FIRST @ < 0= AND IF
                    MR-REFUSE 20 EMIT
                    2SWAP TYPE
                    ."  (" MR-RNG ." )"
                ELSE
                    2DROP 2DROP
                THEN
            THEN
        LOOP
        1+
    REPEAT
    DROP
;

\ ---- Reserved data ranges: name each
\ one the image overlaps (write-catalog
\ SETTINGS_RESERVED, TELEMETRY_RESERVED;
\ MIRROR's own range when the image
\ starts outside it) ----
C0 CONSTANT MR-SET-LO
CF CONSTANT MR-SET-HI
D0 CONSTANT MR-LOG-LO
D7 CONSTANT MR-LOG-HI

: MR-RES1  ( lo hi a l -- )
    2SWAP
    OVER MR-LAST @ > 0=
    OVER MR-FIRST @ < 0= AND IF
        MR-REFUSE 20 EMIT 2SWAP TYPE
        ."  (" MR-RNG ." )"
    ELSE
        2DROP 2DROP
    THEN
;

: MR-RES  ( -- )
    MR-SET-LO MR-SET-HI S" settings" MR-RES1
    MR-LOG-LO MR-LOG-HI S" telemetry" MR-RES1
    MR-FIRST @ MIRROR-BLK <
    MR-FIRST @ MIRROR-END > OR IF
        MIRROR-BLK MIRROR-END
        S" MIRROR-reserved" MR-RES1
    THEN
;

\ ---- Partitions (AHCI's guard) ----
\ False only when AHCI's writer is the
\ active one and AHCI has no PG-WHICH.
: MR-PG  ( -- flag )
    0 MR-PW !
    S" AHCI-WRITER-XT" S" AHCI" VOC-CONST
    ?DUP 0= IF TRUE EXIT THEN
    BLK-WRITER@ <> IF TRUE EXIT THEN
    S" PG-WHICH" S" AHCI" VOC-WORD
    DUP MR-PW ! 0<>
;

\ One LBA: name its partition once
: MR-P1  ( lba -- )
    MR-PW @ EXECUTE IF
        OVER MR-PF @ = IF 2DROP EXIT THEN
        OVER MR-PF !
        MR-REFUSE ."  partition LBA " MR-RNG
    THEN
;

: MR-PART  ( -- )
    MR-PW @ 0= IF EXIT THEN
    -1 MR-PF !
    MR-LAST @ 1+ MR-FIRST @ DO
        I DUP + BLOCKS-LBA-BASE +
        DUP MR-P1 1+ MR-P1
    LOOP
;

\ ---- Writes: around the cache ----
VARIABLE MR-BAD
VARIABLE MR-BAD1

\ One block through the vector; count
\ a nonzero ior, remember the first.
: MR-W1  ( addr blk -- )
    DUP >R BLK-WRITER@ EXECUTE IF
        MR-BAD @ 0= IF R@ MR-BAD1 ! THEN
        1 MR-BAD +!
    THEN
    R> DROP
;

\ Drop any cached copy of the range:
\ a dirty one would be flushed over the
\ image, a clean one read instead of it.
: MR-DISCARD  ( -- )
    MR-LAST @ 1+ MR-FIRST @ DO
        I DISCARD-BLOCK
    LOOP
;

: MR-WRITE  ( -- )
    0 MR-BAD !
    MIR-BUF MR-FIRST @ MR-W1
    MR-LAST @ MR-FIRST @ - DUP 0> IF
        0 DO
            DICT-BASE I A LSHIFT +
            MR-FIRST @ 1+ I + MR-W1
        LOOP
    ELSE
        DROP
    THEN
;

\ ============================================
\ MIRROR - Save context to blocks
\ ============================================
\ Layout on disk:
\   block#+0: header + stack data
\   block#+1..N: dictionary data (1KB each)
\ Checked before any write, in order:
\ size, AHCI's partition check present,
\ then code store, reserved data ranges
\ and partitions (every overlap named). Then the range's cached
\ buffers are dropped and each block is
\ written through the vector.

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

    \ Range: header + DICT-BLKS blocks
    DUP MR-FIRST !
    DICT-BLKS OVER + MR-LAST !
    DROP
    0 MR-HIT !
    MR-FITS? 0= IF EXIT THEN
    MR-PG 0= IF
        ." MIRROR REFUSED: AHCI writer active, "
        ." no PG-WHICH" CR EXIT
    THEN
    MC-SCAN
    MR-RES
    MR-PART
    MR-HIT @ IF CR EXIT THEN

    MR-DISCARD
    MR-WRITE
    MR-BAD @ IF
        ." MIRROR FAILED: " MR-BAD @ MR-N.
        ."  of " MR-LAST @ MR-FIRST @ - 1+ MR-N.
        ."  blocks not written (first "
        MR-BAD1 @ MR-N. ." )" CR
    ELSE
        ." MIRROR saved to block "
        MR-FIRST @ MR-N. CR
    THEN
;

\ ============================================
\ Reading back: the persistent reader
\ ============================================
\ On memdisk BLOCK reads the RAM image,
\ never the disk MIRROR wrote, so every
\ reader here goes through PBLK-READ.

VARIABLE MR-IOR

\ Header into MIR-BUF; TRUE if read
: MR-READ  ( block# -- flag )
    MIR-BUF SWAP PBLK-READ
    DUP MR-IOR ! 0=
;

: MR-VALID?  ( -- flag )
    0 MIR@ MIR-MAGIC =
    4 MIR@ MIR-VER = AND
;

: MR-UNREAD  ( block# -- )
    ." MIRROR: block " MR-N.
    ."  unreadable, ior " MR-IOR @ MR-N. CR
;

\ ============================================
\ MIRROR? - Check for valid snapshot
\ ============================================

: MIRROR?  ( block# -- flag )
    MR-READ IF MR-VALID? ELSE FALSE THEN
;

\ ============================================
\ MIRROR-INFO - Print snapshot info
\ ============================================

: MIRROR-INFO  ( block# -- )
    DUP MR-READ 0= IF MR-UNREAD EXIT THEN
    DROP
    MR-VALID? 0= IF
        ." No valid MIRROR image" CR EXIT
    THEN
    ." MIRROR snapshot info:" CR
    ."   Saved to block: " 8 MIR@ MR-N. CR
    ."   Tick count:     " C MIR@ MR-N. CR
    ."   HERE:           " 10 MIR@ MR-H. CR
    ."   LATEST:         " 14 MIR@ MR-H. CR
    ."   BASE:           " 1C MIR@ MR-N. CR
    ."   Stack depth:    " 20 MIR@ MR-N. CR
    ."   Dict size:      " 24 MIR@ MR-N. CR
    ."   Dict blocks:    " 60 MIR@ MR-N. CR
    ."   Search depth:   " 2C MIR@ MR-N. CR
;

\ ============================================
\ LOOKINGGLASS - Restore context
\ ============================================
\ Restores dictionary, variables, search
\ order, and data stack from a snapshot.
\ Returns to the interpreter loop after
\ restoring (does NOT resume mid-word).
\ Each block is read into a kernel block
\ buffer (outside the dictionary it is
\ overwriting), copied into place, and
\ the buffer dropped. Every block is read
\ once first: one unreadable block and
\ nothing is restored.

\ Block into a pool buffer: buf ior
: MR-R1  ( blk -- buf ior )
    DUP BUFFER
    DUP ROT PBLK-READ
;

\ TRUE if every image block reads
: MR-ALL?  ( block# -- flag )
    60 MIR@ DUP 0> IF
        0 DO
            DUP 1+ I + DUP MR-R1 NIP
            SWAP DISCARD-BLOCK IF
                DROP FALSE UNLOOP EXIT
            THEN
        LOOP
    ELSE
        DROP
    THEN
    DROP TRUE
;

: LOOKINGGLASS  ( block# -- )
    DUP MR-READ 0= IF MR-UNREAD EXIT THEN
    MR-VALID? 0= IF
        DROP
        ." No valid MIRROR image" CR
        EXIT
    THEN
    DUP MR-ALL? 0= IF
        DROP
        ." LOOKINGGLASS: image unreadable, "
        ." nothing restored" CR
        EXIT
    THEN

    \ Restore dictionary blocks first.
    \ block# stays on the stack (DUP):
    \ the variables live in the
    \ dictionary being overwritten.
    60 MIR@ DUP 0> IF
        0 DO
            DUP 1+ I + DUP MR-R1 DROP
            DICT-BASE I A LSHIFT +
            400 MOVE
            DISCARD-BLOCK
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

ONLY FORTH DEFINITIONS
DECIMAL
