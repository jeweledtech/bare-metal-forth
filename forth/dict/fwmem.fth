\ ============================================
\ CATALOG: FWMEM
\ CATEGORY: system
\ PLATFORM: x86
\ SOURCE: hand-written
\ REQUIRES: PCI-ENUM ( .H8 )
\ CONFIDENCE: medium
\ ============================================
\
\ Read-only. A firmware address is looked
\ up before it is followed: in the
\ multiboot2 memory map the kernel kept
\ (MB2-MEMTYPE), and against what ForthOS
\ owns (MB2-OWNED-IN: its windows, the
\ module). A range that touches ForthOS
\ memory is refused, by name, and not
\ followed. docs/TASK_HAL_FWMEM.md.
\
\   FW-SPAN?   ( addr len c-addr u -- flag )
\   FW-FOLLOW? ( addr c-addr u -- flag )
\              the address alone (len 0)
\   FW-SAY     on: a followed address is
\              printed with its map type
\ ============================================

VOCABULARY FWMEM
FWMEM DEFINITIONS
ALSO PCI-ENUM
HEX

VARIABLE FW-SAY

: .FW-OWNER ( n -- )
    DUP 4 = IF DROP ." module" EXIT THEN
    ." window " 30 + EMIT ;

: .FW-TYPE ( type -- )
    DUP . DUP 1 = IF ." (available)" THEN
    DUP 2 = IF ." (reserved)" THEN
    DUP 3 = IF ." (ACPI reclaimable)" THEN
    DUP 4 = IF ." (ACPI NVS)" THEN
    DUP 5 = IF ." (bad)" THEN
    0= IF ." (not in the map)" THEN ;

VARIABLE FW-A
VARIABLE FW-L
\ Where it starts, and with a length the
\ last byte checked: start-last.
: .FW-AT ( c-addr u -- )
    TYPE ."  at " FW-A @ .H8 FW-L @ IF
        ." -" FW-A @ FW-L @ + 1- .H8
    THEN ;
: FW-SPAN? ( addr len c-addr u -- flag )
    2SWAP FW-L ! FW-A !
    FW-A @ FW-L @ MB2-OWNED-IN ?DUP IF
        >R .FW-AT ." : ForthOS memory ("
        R> .FW-OWNER ." ), not followed" CR
        0 EXIT
    THEN
    FW-SAY @ MB2-MMAP NIP 0<> AND IF
        .FW-AT ."  type "
        FW-A @ MB2-MEMTYPE .FW-TYPE CR
    ELSE 2DROP THEN -1 ;
: FW-FOLLOW? ( addr c-addr u -- flag )
    ROT 0 2SWAP FW-SPAN? ;

ONLY FORTH DEFINITIONS
DECIMAL
