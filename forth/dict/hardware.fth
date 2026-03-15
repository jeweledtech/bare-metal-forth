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
    B0 43 OUTB
    FF 42 OUTB
    FF 42 OUTB
    0
    BEGIN
        1+
        42 INB DROP
        42 INB
        42 INB 8 LSHIFT OR
        8000 <
    UNTIL
    DUP + 37 / US-LOOPS !
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
\ Physical Memory Allocation (Simple)
\ ============================================
\ For DMA buffers and device memory.
\ Page-aligned, physically contiguous.
\ Start at 1MB, end at 4MB.

VARIABLE PHYS-HEAP
    100000 PHYS-HEAP !
VARIABLE PHYS-HEAP-END
    400000 PHYS-HEAP-END !

\ Allocate page-aligned physical memory
: PHYS-ALLOC  ( size -- addr | 0 )
    FFF + FFFFF000 AND
    PHYS-HEAP @ +
    DUP PHYS-HEAP-END @ > IF
        DROP 0
    ELSE
        PHYS-HEAP @
        SWAP PHYS-HEAP !
    THEN
;

\ Allocate DMA buffer (below 16MB for ISA)
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
