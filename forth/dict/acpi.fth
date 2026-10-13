\ ============================================
\ CATALOG: ACPI
\ CATEGORY: system
\ PLATFORM: x86
\ SOURCE: hand-written
\ REQUIRES: PCI-ENUM ( .H2 .H8 )
\ REQUIRES: FWMEM ( FW-SPAN? FW-FOLLOW? FW-SAY )
\ CONFIDENCE: medium
\ ============================================
\
\ Read-only. The RSDP comes from the copy
\ GRUB passed (MB2-RSDP, a UEFI boot) or
\ the legacy scan (the EBDA, then E0000-
\ FFFFF); the RSDT or XSDT it points to is
\ walked and each table's checksum checked.
\ Nothing is written. A table above 4 GiB
\ is reported, not followed; so is one in
\ ForthOS memory (FWMEM).
\ HAL phase 0: docs/TASK_HAL_DISCOVERY.md.
\
\   ACPI.          revision, source
\   ACPI-TABLES    every table: signature,
\                  address, length, ok/BAD
\ ============================================

VOCABULARY ACPI
ACPI DEFINITIONS
ALSO PCI-ENUM
ALSO FWMEM
HEX

VARIABLE AC-OK
: AC-MEM= ( a1 a2 n -- flag )
    -1 AC-OK !
    0 DO
        OVER I + C@ OVER I + C@ <> IF
            0 AC-OK !
        THEN
    LOOP 2DROP AC-OK @ ;
: AC-SUM ( addr n -- byte )
    0 SWAP 0 DO OVER I + C@ + LOOP
    NIP FF AND ;

\ ---- The RSDP ----
: RSDP? ( addr -- flag )
    DUP S" RSD PTR " AC-MEM= IF
        14 AC-SUM 0=
    ELSE DROP 0 THEN ;

: RSDP-SCAN ( -- addr|0 )
    0 40E W@ 4 LSHIFT ?DUP IF
        DUP 400 + SWAP DO
            DUP 0= IF I RSDP? IF DROP I THEN THEN
        10 +LOOP
    THEN
    DUP 0= IF
        100000 E0000 DO
            DUP 0= IF I RSDP? IF DROP I THEN THEN
        10 +LOOP
    THEN ;

VARIABLE AC-RSDP
VARIABLE AC-SRC
: ACPI-RSDP ( -- addr|0 )
    MB2-RSDP ?DUP IF 1 AC-SRC !
    ELSE RSDP-SCAN 2 AC-SRC ! THEN
    DUP AC-RSDP ! ;

: .AC-SRC ( -- )
    AC-SRC @ 1 = IF ."  (multiboot2 copy)"
    ELSE ."  (legacy scan)" THEN ;

: ACPI. ( -- )
    ACPI-RSDP ?DUP 0= IF ." No RSDP" CR EXIT THEN
    ." RSDP rev " DUP F + C@ .H2
    ."  at " .H8 .AC-SRC CR ;

\ ---- The tables ----
: .TABLE ( taddr -- )
    DUP 4 TYPE SPACE DUP .H8
    ."  len " DUP 4 + @ DUP .H8 SPACE
    AC-SUM 0= IF ." ok" ELSE ." BAD" THEN CR ;
\ A table: its start first, silent (its
\ header holds the length), then all of
\ it, FW-SAY as it was.
VARIABLE AC-SAY
: AC-SPAN? ( taddr c-addr u -- flag )
    FW-SAY @ AC-SAY ! 0 FW-SAY !
    2 PICK 2 PICK 2 PICK FW-FOLLOW?
    AC-SAY @ FW-SAY ! 0= IF
        2DROP DROP 0 EXIT
    THEN
    ROT DUP 4 + @ 2SWAP FW-SPAN? ;

: .TABLE? ( taddr -- )
    DUP S" ACPI table" AC-SPAN?
    IF .TABLE ELSE DROP THEN ;

\ The root, checked (FW-SAY: with its type).
: AC-ROOT? ( taddr c-addr u -- taddr flag )
    1 FW-SAY ! 2 PICK ROT ROT AC-SPAN?
    0 FW-SAY ! ;

\ XSDT when the revision is 2 or later and
\ it lies below 4 GiB; else the RSDT.
: ACPI-TABLES ( -- )
    AC-RSDP @ ?DUP 0= IF
        ACPI-RSDP ?DUP 0= IF ." No RSDP" CR EXIT THEN
    THEN
    DUP F + C@ 2 >= OVER 1C + @ 0= AND
    OVER 18 + @ 0<> AND IF
        18 + @ S" ACPI XSDT" AC-ROOT?
        0= IF DROP EXIT THEN
        ." XSDT at " DUP .H8
        DUP 4 + @ 24 - 8 / ." : " DUP .
        ." tables" CR
        DUP 0> IF
            0 DO
                DUP 24 + I 8 * + DUP 4 + @ IF
                    DROP ." (above 4 GiB: unreachable)" CR
                ELSE @ .TABLE? THEN
            LOOP
        ELSE DROP THEN DROP
    ELSE
        10 + @ S" ACPI RSDT" AC-ROOT?
        0= IF DROP EXIT THEN
        ." RSDT at " DUP .H8
        DUP 4 + @ 24 - 4 / ." : " DUP .
        ." tables" CR
        DUP 0> IF
            0 DO DUP 24 + I 4 * + @ .TABLE? LOOP
        ELSE DROP THEN DROP
    THEN ;

ONLY FORTH DEFINITIONS
DECIMAL
