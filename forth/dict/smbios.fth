\ ============================================
\ CATALOG: SMBIOS
\ CATEGORY: system
\ PLATFORM: x86
\ SOURCE: hand-written
\ REQUIRES: PCI-ENUM ( .H8 )
\ CONFIDENCE: medium
\ ============================================
\
\ Read-only. The SMBIOS entry point comes
\ from a copy GRUB passed (MB2-SMBIOS), the
\ EFI configuration table (MB2-EFI-ST: GRUB
\ under OVMF passes no SMBIOS tag), or a
\ scan of F0000-FFFFF on 16-byte steps
\ (BIOS); the structures it points to are
\ walked, never written.
\ HAL phase 0: docs/TASK_HAL_DISCOVERY.md.
\
\   SMBIOS.   version, table, source
\   SYSTEM.   manufacturer, product
\   BIOS.     BIOS vendor, version
\ ============================================

VOCABULARY SMBIOS
SMBIOS DEFINITIONS
ALSO PCI-ENUM
HEX

VARIABLE SM-OK
: SM-MEM= ( a1 a2 n -- flag )
    -1 SM-OK !
    0 DO
        OVER I + C@ OVER I + C@ <> IF
            0 SM-OK !
        THEN
    LOOP 2DROP SM-OK @ ;
: SM-SUM ( addr n -- byte )
    0 SWAP 0 DO OVER I + C@ + LOOP
    NIP FF AND ;

\ ---- The entry point ----
\ 3: _SM3_ (3.x), 2: _SM_ (2.x), 0: none
: SM-SIG? ( addr -- 0|2|3 )
    DUP S" _SM3_" SM-MEM= IF
        DUP DUP 6 + C@ SM-SUM 0= IF
            DROP 3 EXIT
        THEN
    THEN
    DUP S" _SM_" SM-MEM= IF
        DUP DUP 5 + C@ SM-SUM 0= IF
            DROP 2 EXIT
        THEN
    THEN
    DROP 0 ;

: SM-SCAN ( -- addr|0 )
    0 100000 F0000 DO
        DUP 0= IF
            I SM-SIG? IF DROP I THEN
        THEN
    10 +LOOP ;

\ ---- UEFI: the EFI configuration table ----
\ The 64-bit system table: entry count at
\ +68, the table at +70; an entry is a
\ GUID (16) and a pointer (8). The SMBIOS
\ 3 and SMBIOS 2 GUIDs, in memory order:
CREATE SM3-GUID
44 C, 15 C, FD C, F2 C, 94 C, 97 C, 2C C, 4A C,
99 C, 2E C, E5 C, BB C, CF C, 20 C, E3 C, 94 C,
CREATE SM2-GUID
31 C, 2D C, 9D C, EB C, 88 C, 2D C, D3 C, 11 C,
9A C, 16 C, 00 C, 90 C, 27 C, 3F C, C1 C, 4D C,

: SE-HIT? ( entry -- flag )
    DUP SM3-GUID 10 SM-MEM=
    SWAP SM2-GUID 10 SM-MEM= OR ;

VARIABLE SE-N
\ 0: no system table, no SMBIOS entry, or
\ a pointer above 4 GiB (not followed).
: SM-EFI ( -- addr|0 )
    MB2-EFI-ST ?DUP 0= IF 0 EXIT THEN
    DUP 74 + @ IF DROP 0 EXIT THEN
    DUP 68 + @ SE-N ! 70 + @
    0 SE-N @ 0> IF
        SE-N @ 0 DO
            DUP 0= IF
                OVER I 18 * +
                DUP SE-HIT? IF
                    DUP 14 + @ 0= IF NIP 10 + @
                    ELSE DROP THEN
                ELSE DROP THEN
            THEN
        LOOP
    THEN NIP ;

VARIABLE SM-EPS
VARIABLE SM-SRC
\ SM-SRC: 1 GRUB's copy, 3 the EFI
\ configuration table, 2 the legacy scan.
: SMBIOS-EPS ( -- addr|0 )
    MB2-SMBIOS ?DUP IF 1 SM-SRC ! ELSE
        SM-EFI ?DUP IF 3 SM-SRC ! ELSE
            SM-SCAN 2 SM-SRC !
        THEN
    THEN
    DUP SM-EPS ! ;

\ ---- The structure table ----
VARIABLE SM-TAB
VARIABLE SM-LEN
VARIABLE SM-HI
\ ok? = 0: no entry point, or the table
\ lies above 4 GiB (not followed).
: SM-TABLE ( -- ok? )
    SMBIOS-EPS ?DUP 0= IF 0 EXIT THEN
    DUP SM-SIG? 3 = IF
        DUP 10 + @ SM-TAB !
        DUP 14 + @ SM-HI !
        0C + @ SM-LEN !
    ELSE
        DUP 18 + @ SM-TAB !
        0 SM-HI !
        16 + W@ SM-LEN !
    THEN
    SM-HI @ 0= ;

\ A structure: type, length, handle, the
\ formatted area, then strings ending in
\ a double NUL.
: SM-NEXT ( struct -- struct' )
    DUP 1+ C@ +
    BEGIN DUP W@ 0<> WHILE 1+ REPEAT
    2 + ;

: SM-FIND ( type -- struct|0 )
    SM-TABLE 0= IF DROP 0 EXIT THEN
    SM-TAB @
    BEGIN DUP SM-TAB @ SM-LEN @ + < WHILE
        2DUP C@ = IF NIP EXIT THEN
        DUP C@ 7F = IF 2DROP 0 EXIT THEN
        SM-NEXT
    REPEAT 2DROP 0 ;

\ String n (1-based) of a structure.
: SM-STR ( struct n -- addr len )
    ?DUP 0= IF DROP 0 0 EXIT THEN
    SWAP DUP 1+ C@ + SWAP 1-
    BEGIN DUP WHILE
        >R BEGIN DUP C@ WHILE 1+ REPEAT
        1+ R> 1-
    REPEAT DROP
    DUP BEGIN DUP C@ WHILE 1+ REPEAT
    OVER - ;

: .SM-FIELD ( struct off -- )
    OVER + C@ SM-STR TYPE ;

\ ---- Reports ----
: SMBIOS. ( -- )
    SM-TABLE IF
        ." SMBIOS "
        SM-EPS @ SM-SIG? 3 = IF ." 3" ELSE ." 2" THEN
        ." .x table at " SM-TAB @ .H8
        ."  len " SM-LEN @ .H8
        SM-SRC @ DUP 1 = IF ."  (multiboot2 copy)" THEN
        DUP 3 = IF ."  (EFI configuration table)" THEN
        2 = IF ."  (legacy scan)" THEN CR
    ELSE
        ." No SMBIOS table (or above 4 GiB)" CR
    THEN ;

: SYSTEM. ( -- )
    1 SM-FIND ?DUP 0= IF
        ." No SMBIOS type 1" CR EXIT
    THEN
    ." Manufacturer: " DUP 4 .SM-FIELD CR
    ." Product: " 5 .SM-FIELD CR ;

: BIOS. ( -- )
    0 SM-FIND ?DUP 0= IF
        ." No SMBIOS type 0" CR EXIT
    THEN
    ." BIOS vendor: " DUP 4 .SM-FIELD CR
    ." BIOS version: " 5 .SM-FIELD CR ;

ONLY FORTH DEFINITIONS
DECIMAL
