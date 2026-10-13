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
\ owns (MB2-OWNED: its windows, the
\ module). An address in ForthOS memory is
\ refused, by name, and not followed.
\ docs/TASK_HAL_FWMEM.md.
\
\   FW-FOLLOW? ( addr c-addr u -- flag )
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
: FW-FOLLOW? ( addr c-addr u -- flag )
    ROT DUP FW-A ! MB2-OWNED ?DUP IF
        >R TYPE ."  at " FW-A @ .H8
        ." : ForthOS memory (" R> .FW-OWNER
        ." ), not followed" CR 0 EXIT
    THEN
    FW-SAY @ MB2-MMAP NIP 0<> AND IF
        TYPE ."  at " FW-A @ .H8 ."  type "
        FW-A @ MB2-MEMTYPE .FW-TYPE CR
    ELSE 2DROP THEN -1 ;

ONLY FORTH DEFINITIONS
DECIMAL
