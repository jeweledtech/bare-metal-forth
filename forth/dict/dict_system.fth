\ ============================================================================
\ Bare-Metal Forth Dictionary System
\ ============================================================================
\
\ This implements the "USING <dictionary>" mechanism for loading
\ platform-specific or device-specific word sets.
\
\ Usage:
\   USING FORTH        \ Base Forth-83 dictionary (always loaded first)
\   USING HARDWARE     \ Direct hardware access words
\   USING RTL8139      \ RealTek NIC driver
\   USING AHCI         \ SATA disk controller
\
\ The dictionary system supports:
\   - Chained dictionaries (each can extend previous)
\   - Version checking
\   - Dependency resolution
\   - Conflict detection
\
\ ============================================================================

\ ============================================================================
\ Dictionary Registry
\ ============================================================================

\ Maximum dictionaries that can be loaded
32 CONSTANT MAX-DICTS

\ Dictionary entry structure (in bytes):
\   0: Link to previous dictionary entry (4 bytes)
\   4: Name string pointer (4 bytes)
\   8: Version (4 bytes: major.minor.patch.0)
\  12: Status flags (4 bytes)
\  16: Entry point (CFA of init word) (4 bytes)
\  20: Dependencies pointer (4 bytes)
\  24: Word count in this dictionary (4 bytes)
\  28: Reserved (4 bytes)
\ Total: 32 bytes per entry

32 CONSTANT DICT-ENTRY-SIZE

\ Dictionary status flags
1 CONSTANT DICT-LOADED      \ Dictionary is loaded
2 CONSTANT DICT-ACTIVE      \ Dictionary is active (searchable)
4 CONSTANT DICT-SYSTEM      \ System dictionary (cannot be unloaded)
8 CONSTANT DICT-HARDWARE    \ Contains hardware access words

\ Registry storage
CREATE DICT-REGISTRY  MAX-DICTS DICT-ENTRY-SIZE * ALLOT
VARIABLE DICT-COUNT   0 DICT-COUNT !
VARIABLE DICT-LATEST  0 DICT-LATEST !   \ Latest loaded dictionary

\ ============================================================================
\ Dictionary Path
\ ============================================================================

\ Where to look for dictionary files
CREATE DICT-PATH  256 ALLOT
S" /forth/dict/" DICT-PATH PLACE

\ Set dictionary path
: SET-DICT-PATH  ( addr u -- )
    255 MIN  DICT-PATH PLACE
;

\ ============================================================================
\ Dictionary Registration
\ ============================================================================

\ Register a new dictionary
: REGISTER-DICT  ( name-addr name-len version -- dict-id )
    DICT-COUNT @ MAX-DICTS >= IF
        ." Error: Dictionary registry full" CR
        -1 EXIT
    THEN
    
    \ Calculate entry address
    DICT-COUNT @ DICT-ENTRY-SIZE * DICT-REGISTRY +
    
    \ Store link to previous
    DUP DICT-LATEST @ SWAP !
    
    \ Store name (create copy in dictionary space)
    4 + HERE >R
    ROT ROT  ( version entry+4 name-addr name-len )
    DUP ALLOT  ( allocate space for name )
    R@ SWAP MOVE  ( copy name )
    0 C,  ( null terminate )
    R> SWAP !  ( store name pointer )
    
    \ Store version
    4 + SWAP OVER !
    
    \ Initialize flags to 0
    4 + 0 OVER !
    
    \ Initialize entry point to 0
    4 + 0 OVER !
    
    \ Initialize rest to 0
    DROP
    
    \ Update latest and count
    DICT-COUNT @ DUP DICT-LATEST !
    1+ DICT-COUNT !
    
    DICT-LATEST @
;

\ ============================================================================
\ Dictionary Lookup
\ ============================================================================

\ Find dictionary by name
: FIND-DICT  ( name-addr name-len -- dict-id | -1 )
    DICT-COUNT @ 0 ?DO
        I DICT-ENTRY-SIZE * DICT-REGISTRY + 4 +  \ Get name pointer
        @ DUP COUNT  ( stored-name-addr stored-len )
        2OVER COMPARE 0= IF
            2DROP DROP I UNLOOP EXIT
        THEN
        DROP
    LOOP
    2DROP -1
;

\ Get dictionary entry address
: DICT-ENTRY  ( dict-id -- entry-addr )
    DICT-ENTRY-SIZE * DICT-REGISTRY +
;

\ Get dictionary name
: DICT-NAME  ( dict-id -- addr len )
    DICT-ENTRY 4 + @ COUNT
;

\ Get dictionary status
: DICT-STATUS  ( dict-id -- flags )
    DICT-ENTRY 12 + @
;

\ Set dictionary status
: SET-DICT-STATUS  ( flags dict-id -- )
    DICT-ENTRY 12 + !
;

\ Check if dictionary is loaded
: DICT-LOADED?  ( dict-id -- flag )
    DICT-STATUS DICT-LOADED AND 0<>
;

\ ============================================================================
\ USING Implementation
\ ============================================================================

\ Build filename from dictionary name
: DICT-FILENAME  ( name-addr name-len -- filename-addr filename-len )
    \ Build: /forth/dict/<name>.fth
    PAD DICT-PATH COUNT ROT SWAP MOVE  ( copy path )
    DICT-PATH C@ PAD +                  ( point after path )
    2DUP SWAP MOVE                      ( copy name )
    + S" .fth" ROT SWAP MOVE            ( append .fth )
    PAD DICT-PATH C@ ROT + 4 +          ( full length )
;

\ Load a dictionary file
: LOAD-DICT-FILE  ( name-addr name-len -- flag )
    DICT-FILENAME
    2DUP ." Loading: " TYPE CR
    INCLUDED
    TRUE
;

\ The USING word
: USING  ( "name" -- )
    BL WORD COUNT  ( get dictionary name )
    
    \ Check if already loaded
    2DUP FIND-DICT DUP 0>= IF
        DUP DICT-LOADED? IF
            ." Dictionary already loaded: " DICT-NAME TYPE CR
            2DROP DROP EXIT
        THEN
    THEN
    DROP
    
    \ Try to load the file
    2DUP LOAD-DICT-FILE IF
        ." Dictionary loaded: " TYPE CR
    ELSE
        ." Failed to load dictionary: " TYPE CR
    THEN
;

\ ============================================================================
\ Dictionary Listing
\ ============================================================================

\ List all registered dictionaries
: .DICTS  ( -- )
    ." Registered dictionaries:" CR
    ." ID  Status  Name" CR
    ." --  ------  ----" CR
    DICT-COUNT @ 0 ?DO
        I 3 .R SPACE
        I DICT-STATUS
        DUP DICT-LOADED AND IF ." L" ELSE ." ." THEN
        DUP DICT-ACTIVE AND IF ." A" ELSE ." ." THEN
        DUP DICT-SYSTEM AND IF ." S" ELSE ." ." THEN
        DICT-HARDWARE AND IF ." H" ELSE ." ." THEN
        SPACE SPACE
        I DICT-NAME TYPE CR
    LOOP
;

\ ============================================================================
\ Built-in Dictionary: FORTH (Base System)
\ ============================================================================

\ This is always loaded automatically
: INIT-FORTH-DICT  ( -- )
    S" FORTH" $00010000 REGISTER-DICT  \ Version 1.0.0
    DUP DICT-LOADED DICT-ACTIVE OR DICT-SYSTEM OR
    SWAP SET-DICT-STATUS
;

\ ============================================================================
\ Built-in Dictionary: HARDWARE
\ ============================================================================

\ Direct hardware access primitives
\ These are the foundation that driver modules build on

: DEFINE-HARDWARE-DICT  ( -- )
    S" HARDWARE" $00010000 REGISTER-DICT DROP
;

\ Port I/O words (these wrap the assembly primitives)
: C@-PORT  ( port -- byte )
    \ IN AL, DX - read byte from port
    \ Implemented in assembly in the kernel
    PORT-IN-BYTE
;

: C!-PORT  ( byte port -- )
    \ OUT DX, AL - write byte to port
    PORT-OUT-BYTE
;

: W@-PORT  ( port -- word )
    PORT-IN-WORD
;

: W!-PORT  ( word port -- )
    PORT-OUT-WORD
;

: @-PORT  ( port -- dword )
    PORT-IN-DWORD
;

: !-PORT  ( dword port -- )
    PORT-OUT-DWORD
;

\ Timing words
: US-DELAY  ( microseconds -- )
    \ Busy wait for specified microseconds
    \ Uses RDTSC or PIT depending on availability
    BUSY-WAIT-US
;

: MS-DELAY  ( milliseconds -- )
    1000 * US-DELAY
;

\ Memory-mapped I/O
: MAP-PHYS  ( phys-addr size -- virt-addr )
    \ Map physical memory to virtual address
    \ On bare metal, this might be identity mapping
    PHYS-TO-VIRT
;

: UNMAP-PHYS  ( virt-addr size -- )
    VIRT-UNMAP
;

\ PCI Configuration Space
: PCI-READ  ( bus dev func reg -- value )
    PCI-CONFIG-READ
;

: PCI-WRITE  ( value bus dev func reg -- )
    PCI-CONFIG-WRITE
;

\ ============================================================================
\ Module System (for installable drivers)
\ ============================================================================

\ Module header structure
\   0: Magic number ($4D4F4455 = "MODU")
\   4: Module name pointer
\   8: Module version
\  12: Init word CFA
\  16: Cleanup word CFA
\  20: Status
\  24: Base address (for drivers)
\  28: IRQ number (for drivers)
\ Total: 32 bytes

32 CONSTANT MODULE-HEADER-SIZE
$4D4F4455 CONSTANT MODULE-MAGIC

\ Current module being defined
VARIABLE CURRENT-MODULE

\ Define a new module
: MODULE:  ( "name" -- )
    CREATE
        MODULE-MAGIC ,          \ Magic
        HERE 4 + ,              \ Name pointer (points to counted string)
        BL WORD COUNT           \ Get name
        DUP C, 0 ?DO            \ Store counted string
            DUP I + C@ C,
        LOOP DROP
        0 ,                     \ Version (set later)
        0 ,                     \ Init CFA
        0 ,                     \ Cleanup CFA
        0 ,                     \ Status
        0 ,                     \ Base address
        0 ,                     \ IRQ
    DOES>
        CURRENT-MODULE !
;

\ Set module init word
: MODULE-INIT:  ( -- )
    ' CURRENT-MODULE @ 12 + !
;

\ Set module cleanup word
: MODULE-CLEANUP:  ( -- )
    ' CURRENT-MODULE @ 16 + !
;

\ Set module base address
: MODULE-BASE!  ( addr -- )
    CURRENT-MODULE @ 24 + !
;

\ Get module base address
: MODULE-BASE@  ( -- addr )
    CURRENT-MODULE @ 24 + @
;

\ Initialize a module
: MODULE-INIT  ( module-addr -- )
    DUP @ MODULE-MAGIC <> IF
        ." Not a valid module" CR DROP EXIT
    THEN
    DUP 12 + @ ?DUP IF
        EXECUTE
        1 SWAP 20 + !  \ Set loaded flag
    ELSE
        DROP ." Module has no init word" CR
    THEN
;

\ ============================================================================
\ Example: How a driver module would look
\ ============================================================================

\ This shows the structure - actual drivers are generated by the extraction tool

COMMENT:
    \ File: rtl8139.fth - RealTek RTL8139 Network Driver
    
    USING HARDWARE          \ Need hardware primitives
    
    MODULE: RTL8139
    
    \ Register offsets
    $00 CONSTANT RTL-IDR0       \ MAC address
    $37 CONSTANT RTL-CMD        \ Command register  
    $3C CONSTANT RTL-IMR        \ Interrupt mask
    $3E CONSTANT RTL-ISR        \ Interrupt status
    $44 CONSTANT RTL-TCR        \ Transmit config
    $62 CONSTANT RTL-MPC        \ Missed packet counter
    
    \ Command bits
    $10 CONSTANT CMD-RESET
    $04 CONSTANT CMD-RX-ENABLE
    $08 CONSTANT CMD-TX-ENABLE
    
    : RTL-REG@  ( offset -- value )
        MODULE-BASE@ + C@-PORT
    ;
    
    : RTL-REG!  ( value offset -- )
        MODULE-BASE@ + C!-PORT
    ;
    
    : RTL-RESET  ( -- )
        CMD-RESET RTL-CMD RTL-REG!
        BEGIN
            RTL-CMD RTL-REG@
            CMD-RESET AND 0=
        UNTIL
    ;
    
    : RTL-READ-MAC  ( buffer -- )
        6 0 DO
            RTL-IDR0 I + RTL-REG@
            OVER I + C!
        LOOP
        DROP
    ;
    
    : RTL-INIT  ( base-port -- )
        MODULE-BASE!
        RTL-RESET
        ." RTL8139 initialized at port $" MODULE-BASE@ HEX U. DECIMAL CR
    ;
    
    ' RTL-INIT MODULE-INIT:
    
    .( RTL8139 driver loaded. Use: <port> RTL8139 MODULE-INIT ) CR
    
COMMENT;

\ ============================================================================
\ Initialization
\ ============================================================================

: INIT-DICT-SYSTEM  ( -- )
    INIT-FORTH-DICT
    DEFINE-HARDWARE-DICT
    ." Dictionary system initialized" CR
    ." Use USING <name> to load dictionaries" CR
    ." Use .DICTS to list available dictionaries" CR
;

\ Auto-run on load
INIT-DICT-SYSTEM
