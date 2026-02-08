\ ============================================================================
\ HARDWARE Dictionary - Low-Level Hardware Access Primitives
\ ============================================================================
\
\ This dictionary provides the fundamental words that all driver modules
\ build upon. These words directly manipulate:
\   - I/O ports (IN/OUT instructions)
\   - Physical memory (MMIO)
\   - CPU registers
\   - Timing (delays)
\   - PCI configuration space
\
\ IMPORTANT: These words only work on bare metal (Ring 0).
\ On a hosted system, they would need privilege escalation.
\
\ Usage:
\   USING HARDWARE          \ Load this dictionary
\   $60 C@-PORT             \ Read byte from keyboard port
\   $55 $1F0 C!-PORT        \ Write to IDE data port
\   100 US-DELAY            \ Wait 100 microseconds
\
\ ============================================================================

MARKER --HARDWARE--

\ ============================================================================
\ I/O Port Access
\ ============================================================================
\
\ These words compile to single x86 IN/OUT instructions.
\ In forth.asm, they're implemented as CODE words.

\ Read byte from I/O port
\ Stack: ( port -- byte )
\ x86: IN AL, DX
CODE C@-PORT
    POP EDX                 \ Port number into DX
    XOR EAX, EAX            \ Clear EAX
    IN AL, DX               \ Read byte
    PUSH EAX                \ Push result
    NEXT
END-CODE

\ Write byte to I/O port  
\ Stack: ( byte port -- )
\ x86: OUT DX, AL
CODE C!-PORT
    POP EDX                 \ Port number into DX
    POP EAX                 \ Value into AL
    OUT DX, AL              \ Write byte
    NEXT
END-CODE

\ Read word (16-bit) from I/O port
\ Stack: ( port -- word )
\ x86: IN AX, DX
CODE W@-PORT
    POP EDX                 \ Port into DX
    XOR EAX, EAX            \ Clear EAX
    IN AX, DX               \ Read word
    PUSH EAX                \ Push result
    NEXT
END-CODE

\ Write word (16-bit) to I/O port
\ Stack: ( word port -- )
\ x86: OUT DX, AX
CODE W!-PORT
    POP EDX                 \ Port into DX
    POP EAX                 \ Value into AX
    OUT DX, AX              \ Write word
    NEXT
END-CODE

\ Read dword (32-bit) from I/O port
\ Stack: ( port -- dword )
\ x86: IN EAX, DX
CODE @-PORT
    POP EDX                 \ Port into DX
    IN EAX, DX              \ Read dword
    PUSH EAX                \ Push result
    NEXT
END-CODE

\ Write dword (32-bit) to I/O port
\ Stack: ( dword port -- )
\ x86: OUT DX, EAX
CODE !-PORT
    POP EDX                 \ Port into DX
    POP EAX                 \ Value into EAX
    OUT DX, EAX             \ Write dword
    NEXT
END-CODE

\ ============================================================================
\ Block I/O (REP INS/OUTS)
\ ============================================================================

\ Read N bytes from port to buffer
\ Stack: ( buffer port count -- )
CODE C@N-PORT
    POP ECX                 \ Count
    POP EDX                 \ Port
    POP EDI                 \ Buffer
    CLD                     \ Forward direction
    REP INSB                \ Read bytes
    NEXT
END-CODE

\ Write N bytes from buffer to port
\ Stack: ( buffer port count -- )
CODE C!N-PORT
    POP ECX                 \ Count
    POP EDX                 \ Port
    POP ESI                 \ Buffer
    CLD                     \ Forward direction
    REP OUTSB               \ Write bytes
    NEXT
END-CODE

\ Read N words from port to buffer
CODE W@N-PORT
    POP ECX                 \ Count (in words)
    POP EDX                 \ Port
    POP EDI                 \ Buffer
    CLD
    REP INSW                \ Read words
    NEXT
END-CODE

\ Write N words from buffer to port
CODE W!N-PORT
    POP ECX                 \ Count (in words)
    POP EDX                 \ Port
    POP ESI                 \ Buffer
    CLD
    REP OUTSW               \ Write words
    NEXT
END-CODE

\ Read N dwords from port to buffer
CODE @N-PORT
    POP ECX                 \ Count (in dwords)
    POP EDX                 \ Port
    POP EDI                 \ Buffer
    CLD
    REP INSD                \ Read dwords
    NEXT
END-CODE

\ Write N dwords from buffer to port
CODE !N-PORT
    POP ECX                 \ Count (in dwords)
    POP EDX                 \ Port
    POP ESI                 \ Buffer
    CLD
    REP OUTSD               \ Write dwords
    NEXT
END-CODE

\ ============================================================================
\ Timing
\ ============================================================================

\ Calibrated delay loop constant (set during boot)
VARIABLE US-LOOPS   1000 US-LOOPS !     \ Loops per microsecond

\ Calibrate delay loop using PIT
: CALIBRATE-DELAY  ( -- )
    \ Use PIT channel 2 for calibration
    \ This is a simplified version; production code would be more precise
    
    \ Program PIT channel 2 for one-shot mode
    $B0 $43 C!-PORT         \ Channel 2, lobyte/hibyte, mode 0
    $FF $42 C!-PORT         \ Low byte of count
    $FF $42 C!-PORT         \ High byte (65535 total)
    
    \ Count how many loops in ~55ms (65536 / 1193182 Hz)
    0                       \ Loop counter
    BEGIN
        1+
        $42 C@-PORT DROP    \ Read to latch
        $42 C@-PORT         \ Low byte
        $42 C@-PORT 8 LSHIFT OR  \ High byte
        $8000 <             \ Count down past halfway?
    UNTIL
    
    \ Calculate loops per microsecond
    \ (loops * 2) / 55000 = loops per microsecond (approximately)
    2* 55 / US-LOOPS !
    
    ." Calibrated: " US-LOOPS @ . ." loops/us" CR
;

\ Microsecond busy-wait delay
\ Stack: ( microseconds -- )
: US-DELAY  ( us -- )
    US-LOOPS @ * 0 ?DO LOOP
;

\ Millisecond delay
: MS-DELAY  ( ms -- )
    1000 * US-DELAY
;

\ High-precision delay using RDTSC (if available)
VARIABLE TSC-MHZ    1000 TSC-MHZ !      \ CPU MHz (approximate)

\ Read Time Stamp Counter
CODE RDTSC@  ( -- low high )
    RDTSC
    PUSH EAX                \ Low 32 bits
    PUSH EDX                \ High 32 bits
    NEXT
END-CODE

\ TSC-based microsecond delay (more accurate)
: TSC-US-DELAY  ( us -- )
    TSC-MHZ @ *             \ Convert to cycles
    RDTSC@ DROP             \ Get current TSC (low part only for short delays)
    +                       \ Target TSC
    BEGIN
        RDTSC@ DROP         \ Current TSC
        OVER >=             \ Reached target?
    UNTIL
    DROP
;

\ ============================================================================
\ Memory-Mapped I/O
\ ============================================================================

\ On bare metal with identity mapping, these are just memory access.
\ With paging enabled, we'd need to set up page tables.

\ Read byte from physical address
: C@-MMIO  ( phys-addr -- byte )
    C@
;

\ Write byte to physical address
: C!-MMIO  ( byte phys-addr -- )
    C!
;

\ Read word from physical address
: W@-MMIO  ( phys-addr -- word )
    DUP C@ SWAP 1+ C@ 8 LSHIFT OR
;

\ Write word to physical address
: W!-MMIO  ( word phys-addr -- )
    2DUP C!
    SWAP 8 RSHIFT SWAP 1+ C!
;

\ Read dword from physical address
: @-MMIO  ( phys-addr -- dword )
    @
;

\ Write dword to physical address
: !-MMIO  ( dword phys-addr -- )
    !
;

\ Memory barrier (for MMIO ordering)
CODE MFENCE
    MFENCE                  \ Full memory barrier
    NEXT
END-CODE

\ ============================================================================
\ PCI Configuration Space
\ ============================================================================

\ PCI CONFIG_ADDRESS port
$0CF8 CONSTANT PCI-ADDR-PORT
\ PCI CONFIG_DATA port
$0CFC CONSTANT PCI-DATA-PORT

\ Build PCI address
: PCI-ADDRESS  ( bus dev func reg -- addr )
    $FC AND                 \ Align register to dword
    SWAP 8 LSHIFT OR        \ Function << 8
    SWAP 11 LSHIFT OR       \ Device << 11
    SWAP 16 LSHIFT OR       \ Bus << 16
    $80000000 OR            \ Enable bit
;

\ Read PCI configuration dword
: PCI-READ  ( bus dev func reg -- value )
    PCI-ADDRESS
    PCI-ADDR-PORT !-PORT    \ Write address
    PCI-DATA-PORT @-PORT    \ Read data
;

\ Write PCI configuration dword
: PCI-WRITE  ( value bus dev func reg -- )
    PCI-ADDRESS
    PCI-ADDR-PORT !-PORT    \ Write address
    PCI-DATA-PORT !-PORT    \ Write data
;

\ Read PCI configuration byte
: PCI-C@  ( bus dev func reg -- byte )
    DUP 3 AND >R            \ Save byte offset
    PCI-READ
    R> 8 * RSHIFT           \ Shift to get correct byte
    $FF AND
;

\ Read PCI configuration word
: PCI-W@  ( bus dev func reg -- word )
    DUP 2 AND >R            \ Save word offset
    PCI-READ
    R> 8 * RSHIFT           \ Shift to get correct word
    $FFFF AND
;

\ ============================================================================
\ Interrupt Control
\ ============================================================================

\ Disable interrupts
CODE CLI  ( -- )
    CLI
    NEXT
END-CODE

\ Enable interrupts
CODE STI  ( -- )
    STI
    NEXT
END-CODE

\ Disable interrupts and return previous state
CODE INT-OFF  ( -- flags )
    PUSHFD
    CLI
    POP EAX
    PUSH EAX
    NEXT
END-CODE

\ Restore interrupt state
CODE INT-RESTORE  ( flags -- )
    POP EAX
    PUSH EAX
    POPFD
    NEXT
END-CODE

\ ============================================================================
\ CPU Identification
\ ============================================================================

\ CPUID instruction wrapper
CODE CPUID  ( eax -- eax ebx ecx edx )
    POP EAX                 \ Input EAX
    CPUID                   \ Execute CPUID
    PUSH EDX
    PUSH ECX
    PUSH EBX
    PUSH EAX
    NEXT
END-CODE

\ Check if CPUID is available
: CPUID?  ( -- flag )
    \ Try to flip bit 21 of EFLAGS
    INT-OFF                 \ Get flags
    DUP $200000 XOR         \ Flip bit 21
    INT-RESTORE             \ Try to set
    INT-OFF                 \ Read back
    XOR $200000 AND 0<>     \ Did it change?
;

\ Get CPU vendor string
CREATE CPU-VENDOR 13 ALLOT

: GET-CPU-VENDOR  ( -- )
    0 CPUID                 \ EAX=0 returns vendor in EBX,EDX,ECX
    DROP                    \ Discard EAX
    CPU-VENDOR !            \ EBX -> bytes 0-3
    CPU-VENDOR 8 + !        \ ECX -> bytes 8-11
    CPU-VENDOR 4 + !        \ EDX -> bytes 4-7
    0 CPU-VENDOR 12 + C!    \ Null terminate
;

\ ============================================================================
\ Physical Memory Allocation (Simple)
\ ============================================================================

\ For DMA, we need physically contiguous memory.
\ This is a very simple allocator for bare metal use.

VARIABLE PHYS-HEAP      $100000 PHYS-HEAP !     \ Start at 1MB
VARIABLE PHYS-HEAP-END  $400000 PHYS-HEAP-END ! \ End at 4MB

\ Allocate physically contiguous memory (page-aligned)
: PHYS-ALLOC  ( size -- phys-addr | 0 )
    $FFF + $FFFFF000 AND    \ Round up to page boundary
    PHYS-HEAP @ +           \ New heap position
    DUP PHYS-HEAP-END @ > IF
        DROP 0              \ Out of memory
    ELSE
        PHYS-HEAP @         \ Return old position
        SWAP PHYS-HEAP !    \ Update heap
    THEN
;

\ ============================================================================
\ DMA Buffer Allocation
\ ============================================================================

\ Allocate DMA buffer (physically contiguous, below 16MB for ISA DMA)
: DMA-ALLOC  ( size -- phys-addr | 0 )
    PHYS-ALLOC
;

\ For 32-bit PCI DMA, we can use any address below 4GB (already covered)
\ For 64-bit DMA-capable devices, any address works

\ ============================================================================
\ Diagnostic/Debug
\ ============================================================================

\ Dump I/O port range
: PORT-DUMP  ( start count -- )
    CR ." Port  Value" CR
    0 DO
        DUP I + 
        DUP 4 U.R SPACE
        C@-PORT 2 U.R CR
    LOOP
    DROP
;

\ Scan PCI bus
: PCI-SCAN  ( -- )
    CR ." Bus Dev Fun  Vendor:Device" CR
    32 0 DO                 \ 32 buses (simplified)
        32 0 DO             \ 32 devices
            8 0 DO          \ 8 functions
                K J I 0 PCI-READ
                DUP $FFFF AND $FFFF <> IF
                    K 3 U.R SPACE
                    J 3 U.R SPACE
                    I 3 U.R SPACE
                    DUP $FFFF AND 4 U.R ." :"
                    16 RSHIFT 4 U.R CR
                ELSE
                    DROP
                THEN
            LOOP
        LOOP
    LOOP
;

\ ============================================================================
\ Initialization
\ ============================================================================

: HARDWARE-INIT  ( -- )
    CPUID? IF
        GET-CPU-VENDOR
        ." CPU: " CPU-VENDOR COUNT TYPE CR
    THEN
    CALIBRATE-DELAY
    ." HARDWARE dictionary loaded" CR
;

\ Run on load
HARDWARE-INIT

\ ============================================================================
\ Summary of words provided by HARDWARE dictionary
\ ============================================================================
\
\ Port I/O:
\   C@-PORT  ( port -- byte )       Read byte from port
\   C!-PORT  ( byte port -- )       Write byte to port
\   W@-PORT  ( port -- word )       Read word from port
\   W!-PORT  ( word port -- )       Write word to port
\   @-PORT   ( port -- dword )      Read dword from port
\   !-PORT   ( dword port -- )      Write dword to port
\   C@N-PORT ( buf port n -- )      Read n bytes
\   C!N-PORT ( buf port n -- )      Write n bytes
\   W@N-PORT ( buf port n -- )      Read n words
\   W!N-PORT ( buf port n -- )      Write n words
\   @N-PORT  ( buf port n -- )      Read n dwords
\   !N-PORT  ( buf port n -- )      Write n dwords
\
\ Timing:
\   US-DELAY ( us -- )              Busy-wait microseconds
\   MS-DELAY ( ms -- )              Busy-wait milliseconds
\   RDTSC@   ( -- low high )        Read timestamp counter
\
\ MMIO:
\   C@-MMIO  ( addr -- byte )       Read MMIO byte
\   C!-MMIO  ( byte addr -- )       Write MMIO byte
\   W@-MMIO  ( addr -- word )       Read MMIO word
\   W!-MMIO  ( word addr -- )       Write MMIO word
\   @-MMIO   ( addr -- dword )      Read MMIO dword
\   !-MMIO   ( dword addr -- )      Write MMIO dword
\   MFENCE   ( -- )                 Memory fence
\
\ PCI:
\   PCI-READ  ( bus dev fun reg -- val )   Read PCI config
\   PCI-WRITE ( val bus dev fun reg -- )   Write PCI config
\   PCI-C@    ( bus dev fun reg -- byte )  Read config byte
\   PCI-W@    ( bus dev fun reg -- word )  Read config word
\   PCI-SCAN  ( -- )                       Scan and list PCI devices
\
\ Interrupts:
\   CLI      ( -- )                 Disable interrupts
\   STI      ( -- )                 Enable interrupts
\   INT-OFF  ( -- flags )           Disable and save state
\   INT-RESTORE ( flags -- )        Restore interrupt state
\
\ CPU:
\   CPUID    ( eax -- eax ebx ecx edx )    CPUID instruction
\   CPUID?   ( -- flag )            Is CPUID available?
\
\ Memory:
\   PHYS-ALLOC ( size -- addr )     Allocate physical memory
\   DMA-ALLOC  ( size -- addr )     Allocate DMA buffer
\
\ ============================================================================
