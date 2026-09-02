\ ============================================
\ CATALOG: HARDWARE
\ CATEGORY: system
\ PLATFORM: x86
\ SOURCE: hand-written
\ CONFIDENCE: high
\ ============================================
\
\ Hardware utility layer for bare-metal Forth.
\ Provides timing primitives and MMIO helpers.
\ Port I/O uses kernel INB/OUTB/INW/OUTW/
\ INL/OUTL directly -- no wrappers needed.
\
\ Usage:
\   USING HARDWARE
\   100 US-DELAY
\   1000 MS-DELAY
\
\ ============================================

VOCABULARY HARDWARE
HARDWARE DEFINITIONS
HEX

\ ============================================
\ Timing
\ ============================================

\ Loops-per-microsecond calibration value
VARIABLE US-LOOPS  3E8 US-LOOPS !

\ Calibrate delay loop using PIT channel 2.
\ Programs PIT ch2 in one-shot mode, counts
\ how many loop iterations pass in ~55ms
\ (65536 ticks at 1.193182 MHz).
: CALIBRATE-DELAY  ( -- )
    61 INB
    DUP 1 OR FE AND 61 OUTB
    B0 43 OUTB
    FF 42 OUTB  FF 42 OUTB
    0
    BEGIN
        1+
        42 INB DROP
        42 INB
        42 INB 8 LSHIFT OR  8000 <
        OVER 100000 > OR
    UNTIL
    DUP 100000 > IF
        DROP C US-LOOPS !
        ." PIT timeout; default" CR
    ELSE
        DUP + 37 / US-LOOPS !
    THEN
    61 OUTB
    ." Calibrated: "
    US-LOOPS @ DECIMAL . HEX
    ." loops/us" CR
;

\ Microsecond busy-wait delay
: US-DELAY  ( us -- )
    US-LOOPS @ *
    DUP 0> IF
        0 DO LOOP
    ELSE
        DROP
    THEN
;

\ Millisecond delay
: MS-DELAY  ( ms -- )
    3E8 * US-DELAY
;

\ ============================================
\ Memory-Mapped I/O
\ ============================================
\ On bare metal with identity mapping,
\ physical addresses = virtual addresses.
\ These words document MMIO intent.

: C@-MMIO  ( phys-addr -- byte )  C@ ;
: C!-MMIO  ( byte phys-addr -- )  C! ;
: W@-MMIO  ( phys-addr -- word )
    DUP C@ SWAP 1+ C@
    8 LSHIFT OR
;
: W!-MMIO  ( word phys-addr -- )
    2DUP C!
    SWAP 8 RSHIFT SWAP 1+ C!
;
: @-MMIO  ( phys-addr -- dword )  @ ;
: !-MMIO  ( dword phys-addr -- )  ! ;

\ ============================================
\ Physical Memory Allocation
\ ============================================
\ For DMA buffers and device memory.
\ Page-aligned, physically contiguous.
\ Pool: 1MB..4MB.  Owner side table (LIVE
\ entries only) is a STATIC CARVE at the pool
\ origin -- not self-allocated, so the table
\ never appears as an allocation and PHYS-AUDIT
\ must account for it explicitly.
\
\ OWN-TABLE-DERIVATION (gated three ways in
\ tests/kernel_constants.check_phys_table):
\   record = size(4) + tag(4) + base(4) = C
\   capacity: OWN-CAP * 1000 >= PHYS-TOP -
\     POOL-ORIGIN  (300 pages exactly; the 3
\     entries consumed by the carve itself are
\     spare -- rounding artifact, safe side)
\   carve: OWN-BYTES = page-round(OWN-CAP *
\     OWN-REC) = 3000 (3 pages)
\   POOL-BASE = POOL-ORIGIN + OWN-BYTES, so
\   overlap is impossible by identity.

100000 CONSTANT POOL-ORIGIN
400000 CONSTANT PHYS-TOP
300 CONSTANT OWN-CAP
C CONSTANT OWN-REC
3000 CONSTANT OWN-BYTES
POOL-ORIGIN OWN-BYTES + CONSTANT POOL-BASE
POOL-ORIGIN CONSTANT OWN-TABLE
28048 CONSTANT FORTH-CELL

VARIABLE PHYS-HEAP
    POOL-BASE PHYS-HEAP !
VARIABLE PHYS-HEAP-END
    PHYS-TOP PHYS-HEAP-END !

\ Owner table records: [size(4)][tag(4)][base(4)].
\ Empty slot: size = 0.  Tag is CURRENT @ at alloc
\ time (measured truthful for all load-time callers,
\ docs/evidence/phys-current-probe-2026-08-30.log).
\ Tag = FORTH-CELL is the UNATTRIBUTED third state:
\ counted on its own audit line, never folded into
\ a vocabulary's total.
\ Refusal contract: every named refusal begins
\ "PHYS: " (gated by tests/test_phys_alloc.py).

VARIABLE FND-S   VARIABLE FND-A

: OWN-SLOT ( i -- addr )  OWN-REC * OWN-TABLE + ;

\ Full-range loops with result variables: kernel
\ has no LEAVE, and EXIT must not fire in DO..LOOP.
: OWN-FIND ( base -- slot | 0 )
    0 FND-A !
    OWN-CAP 0 DO
        I OWN-SLOT FND-S !
        DUP FND-S @ 8 + @ =
        FND-S @ @ 0= 0= AND IF
            FND-S @ FND-A !
        THEN
    LOOP DROP FND-A @ ;

: OWN-EMPTY ( -- slot | 0 )
    0 FND-A !
    OWN-CAP 0 DO
        I OWN-SLOT FND-S !
        FND-S @ @ 0= IF FND-S @ FND-A ! THEN
    LOOP FND-A @ ;

: OWN-WIPE ( -- )
    OWN-BYTES 0 DO
        0 OWN-TABLE I + !
    4 +LOOP ;
OWN-WIPE

\ Free list: LIVE side table has no tombstones; the
\ free list is the ONLY representation of freed
\ memory.  Node lives IN the freed extent:
\ [next(4)][size(4)] at extent base.  A late DMA
\ write from a badly-exited driver corrupts the
\ allocator's own structure, so the walk is bounded
\ and self-checking: refuse loudly, never hang.
VARIABLE FL-HEAD  0 FL-HEAD !
VARIABLE FL-CUR   VARIABLE FL-PV
VARIABLE FL-N     VARIABLE FL-TOT
VARIABLE FL-OK    VARIABLE FL-HIT
VARIABLE FL-ADDR

\ In-pool and strictly above the previous node.
\ Signed compares are safe: pool < 2GB, and a wild
\ pointer like DEADBEEF goes negative -> refused.
: FL-NODE-OK ( node -- flag )
    DUP POOL-BASE < 0=
    OVER PHYS-TOP < AND
    SWAP FL-PV @ > AND ;

\ Walk: flag true = clean.  Side effects: FL-N node
\ count, FL-TOT freed bytes, FL-HIT true if
\ FL-ADDR fell inside a freed extent (extent-range
\ membership: interior pointers DO hit -- both
\ membership refusals answer for the extent, not
\ the exact base).
: FL-WALK ( -- flag )
    -1 FL-OK !  0 FL-N !  0 FL-TOT !
    0 FL-PV !  0 FL-HIT !
    FL-HEAD @ FL-CUR !
    BEGIN FL-CUR @ 0= 0=  FL-OK @ AND WHILE
        FL-N @ 1+ FL-N !
        FL-N @ OWN-CAP > IF
            ." PHYS: free list too long" CR
            0 FL-OK !
        ELSE FL-CUR @ FL-NODE-OK 0= IF
            ." PHYS: free list corrupt" CR
            0 FL-OK !
        ELSE
            FL-CUR @ 4 + @ FL-TOT +!
            FL-ADDR @ FL-CUR @ < 0=
            FL-ADDR @
            FL-CUR @ DUP 4 + @ + < AND IF
                -1 FL-HIT !
            THEN
            FL-CUR @ FL-PV !
            FL-CUR @ @ FL-CUR !
        THEN THEN
    REPEAT FL-OK @ ;

\ First-fit take with split; unlinks from the list.
VARIABLE FT-A   VARIABLE FT-PV
VARIABLE FT-SZ  VARIABLE FT-RM  VARIABLE FT-NW
: FL-TAKE ( sz -- addr | 0 )
    FT-SZ !  0 FT-A !  0 FT-PV !
    FL-HEAD @ FL-CUR !
    BEGIN FL-CUR @ 0= 0=  FT-A @ 0= AND WHILE
        FL-CUR @ 4 + @ FT-SZ @ < 0= IF
            FL-CUR @ FT-A !
        ELSE
            FL-CUR @ FT-PV !
            FL-CUR @ @ FL-CUR !
        THEN
    REPEAT
    FT-A @ 0= IF 0 EXIT THEN
    FT-A @ 4 + @ FT-SZ @ - FT-RM !
    FT-RM @ 0= IF
        FT-A @ @ FT-NW !
    ELSE
        FT-A @ FT-SZ @ + FT-NW !
        FT-A @ @    FT-NW @ !
        FT-RM @     FT-NW @ 4 + !
    THEN
    FT-PV @ 0= IF
        FT-NW @ FL-HEAD !
    ELSE
        FT-NW @ FT-PV @ !
    THEN
    FT-A @ ;

\ Sorted insert with merge-on-insert, BOTH
\ directions (successor then predecessor) --
\ coalescing that never merges is a slower leak.
VARIABLE IN-A  VARIABLE IN-SZ
: FL-INSERT ( addr sz -- )
    IN-SZ !  IN-A !
    0 FT-PV !  FL-HEAD @ FL-CUR !
    BEGIN
        FL-CUR @ 0= 0=
        FL-CUR @ IN-A @ < AND
    WHILE
        FL-CUR @ FT-PV !
        FL-CUR @ @ FL-CUR !
    REPEAT
    FL-CUR @ IN-A @ !
    IN-SZ @ IN-A @ 4 + !
    FT-PV @ 0= IF
        IN-A @ FL-HEAD !
    ELSE
        IN-A @ FT-PV @ !
    THEN
    IN-A @ IN-SZ @ +  FL-CUR @ =
    FL-CUR @ 0= 0= AND IF
        FL-CUR @ @        IN-A @ !
        FL-CUR @ 4 + @ IN-SZ @ +
        DUP IN-SZ !  IN-A @ 4 + !
    THEN
    FT-PV @ 0= 0= IF
        FT-PV @ FT-PV @ 4 + @ +
        IN-A @ = IF
            IN-A @ @  FT-PV @ !
            FT-PV @ 4 + @ IN-SZ @ +
            FT-PV @ 4 + !
        THEN
    THEN ;

\ Allocate page-aligned physical memory.
\ Free list first, bump heap second; every success
\ recorded in the owner table with CURRENT @ tag.
\ Table full is a NAMED refusal, distinct from the
\ bare 0 of out-of-memory (unreachable with real
\ capacity; exercised by the cap-8 fixture image).
VARIABLE PA-SZ  VARIABLE PA-A  VARIABLE PA-SL
: PHYS-ALLOC ( size -- addr | 0 )
    FFF + FFFFF000 AND PA-SZ !
    PA-SZ @ 0= IF 0 EXIT THEN
    OWN-EMPTY PA-SL !
    PA-SL @ 0= IF
        ." PHYS: owner table full" CR 0 EXIT
    THEN
    PA-SZ @ FL-TAKE PA-A !
    PA-A @ 0= IF
        PHYS-HEAP @ PA-SZ @ +
        PHYS-HEAP-END @ > 0= IF
            PHYS-HEAP @ PA-A !
            PHYS-HEAP @ PA-SZ @ + PHYS-HEAP !
        THEN
    THEN
    PA-A @ 0= IF 0 EXIT THEN
    PA-SZ @    PA-SL @ !
    CURRENT @  PA-SL @ 4 + !
    PA-A @     PA-SL @ 8 + !
    PA-A @ ;

\ Release: sizes compared page-ROUNDED, so calling
\ with the original request size is legal.  The two
\ membership refusals answer for the containing
\ extent (base-address semantics documented in the
\ suite): inside a live allocation that is not the
\ base -> "not allocated"; inside a freed extent ->
\ "double release".
VARIABLE PR-A  VARIABLE PR-SZ  VARIABLE PR-SL
: PHYS-RELEASE ( addr size -- )
    FFF + FFFFF000 AND PR-SZ !  PR-A !
    PR-A @ 0= IF
        ." PHYS: not allocated" CR EXIT
    THEN
    PR-A @ OWN-FIND PR-SL !
    PR-SL @ 0= IF
        PR-A @ FL-ADDR !
        FL-WALK 0= IF
            \ walk refused; a membership verdict
            \ from an instrument that just declared
            \ itself broken would be unearned
            ." PHYS: membership unanswerable" CR
            EXIT
        THEN
        FL-HIT @ IF
            ." PHYS: double release" CR
        ELSE
            ." PHYS: not allocated" CR
        THEN EXIT
    THEN
    PR-SL @ @ PR-SZ @ = 0= IF
        ." PHYS: size mismatch" CR EXIT
    THEN
    0 PR-SL @ !
    0 PR-SL @ 4 + !
    0 PR-SL @ 8 + !
    PR-A @ PR-SZ @ FL-INSERT ;

\ Audit: per-entry lines, then summary in HEX.
\ Closing sum live + freelist + tail + table must
\ equal PHYS-TOP - POOL-ORIGIN exactly -- an
\ allocator whose accounting does not sum is
\ reporting on a state it has lost track of.
\ BASE saved and restored on EVERY exit path.
VARIABLE AU-B   VARIABLE AU-LV
VARIABLE AU-UN  VARIABLE AU-LB
: PHYS-AUDIT ( -- )
    BASE @ AU-B !  HEX
    0 AU-LV !  0 AU-UN !  0 AU-LB !
    OWN-CAP 0 DO
        I OWN-SLOT FND-S !
        FND-S @ @ 0= 0= IF
            FND-S @ 8 + @ U.
            FND-S @ @ U.
            FND-S @ 4 + @ FORTH-CELL = IF
                ." FORTH(unattrib)"
                AU-UN @ 1+ AU-UN !
            THEN CR
            AU-LV @ 1+ AU-LV !
            FND-S @ @ AU-LB +!
        THEN
    LOOP
    0 FL-ADDR !
    FL-WALK 0= IF AU-B @ BASE ! EXIT THEN
    ." live: " AU-LV @ U.
    ." unattributed: " AU-UN @ U. CR
    ." extents: " FL-N @ U. CR
    AU-LB @ FL-TOT @ +
    PHYS-HEAP-END @ PHYS-HEAP @ - +
    OWN-BYTES +
    DUP ." total: " U. CR
    PHYS-TOP POOL-ORIGIN - = 0= IF
        ." PHYS: audit sum mismatch" CR
    THEN
    AU-B @ BASE ! ;

\ Allocate DMA buffer (below 16MB for ISA).  Bare
\ delegation is CORRECT while the whole pool sits
\ below 16MB -- machine-checked: kernel_constants
\ asserts PHYS-TOP <= 0x1000000.
: DMA-ALLOC  ( size -- addr | 0 )
    PHYS-ALLOC
;

\ ============================================
\ Deferred Procedure Call
\ ============================================
\ In cooperative single-threaded Forth,
\ immediate execution is the correct
\ semantics. DPC-QUEUE will be redefined
\ when a scheduler is added.

: DPC-QUEUE  ( xt -- )  EXECUTE ;

\ ============================================
\ IRQ Management
\ ============================================
\ ISR hook table at 29C00 (16 x 4 bytes).
\ Kernel ISR stubs will dispatch through
\ this table when hook support is added.
\ IRQ-UNMASK is a kernel primitive.

29C00 CONSTANT HOOK-TABLE

: NOP-HANDLER  ( -- ) ;

: IRQ-MASK  ( irq# -- )
    DUP 8 < IF
        1 SWAP LSHIFT
        21 INB OR 21 OUTB
    ELSE
        8 -
        1 SWAP LSHIFT
        A1 INB OR A1 OUTB
    THEN
;

: IRQ-CONNECT  ( xt irq# -- )
    DUP >R
    4 * HOOK-TABLE + !
    R> IRQ-UNMASK
;

: IRQ-DISCONNECT  ( irq# -- )
    DUP >R
    4 * HOOK-TABLE +
    ['] NOP-HANDLER SWAP !
    R> IRQ-MASK
;

\ ============================================
\ Initialization
\ ============================================

: HARDWARE-INIT  ( -- )
    CALIBRATE-DELAY
    ." HARDWARE loaded" CR
;

HARDWARE-INIT

FORTH DEFINITIONS
DECIMAL
