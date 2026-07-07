\ ============================================
\ CATALOG: SHUTDOWN
\ CATEGORY: system
\ PLATFORM: x86
\ SOURCE: hand-written
\ CONFIDENCE: high
\ REQUIRES:
\ ============================================
\
\ ACPI S5 shutdown for QEMU and real hardware.
\
\ Tier 1 — QEMU i440FX:
\   USING SHUTDOWN
\   SHUTDOWN
\
\ Tier 2 — Real hardware (ACPI table walk):
\   USING SHUTDOWN
\   ACPI-SHUTDOWN
\
\ ACPI-SHUTDOWN scans for the RSDP, walks
\ RSDT to find FADT, extracts PM1a_CNT port
\ and SLP_TYPa from the DSDT _S5_ object,
\ enables ACPI mode if needed, then writes
\ the S5 sleep command. Prints diagnostic
\ and returns if any ACPI table is missing.
\
\ ============================================

VOCABULARY SHUTDOWN
SHUTDOWN DEFINITIONS
HEX

\ ---- Tier 1: QEMU i440FX shortcut ----
\ PM1a_CNT = 0x604, SLP_EN bit 13
: QEMU-OFF ( -- ) 2000 604 OUTW ;

\ ---- ACPI table variables ----
VARIABLE RSDP-ADDR
VARIABLE RSDT-ADDR
VARIABLE FADT-ADDR
VARIABLE DSDT-ADDR
VARIABLE PM1A-PORT
VARIABLE SLP-TYPE
VARIABLE SMI-PORT
VARIABLE ACPI-EN

\ ---- Signature matching ----
: SIG4? ( addr c1 c2 c3 c4 -- flag )
    >R >R >R >R
    DUP C@ R> = SWAP
    DUP 1+ C@ R> = ROT AND SWAP
    DUP 2 + C@ R> = ROT AND SWAP
    3 + C@ R> = AND ;

\ ---- RSDP checksum (20 bytes) ----
: RSDP-CSUM ( addr -- ok? )
    0 SWAP 14 0 DO
        DUP I + C@ ROT + SWAP
    LOOP DROP FF AND 0= ;

\ ---- Scan for RSDP ----
\ Check EBDA first, then E0000-FFFFF
: SCAN-RSDP ( -- addr | 0 )
    \ EBDA: read word at 0x40E, shift left 4
    40E @ FFFF AND 4 LSHIFT
    DUP 0<> IF
        DUP 400 + SWAP DO
            I 52 53 44 20 SIG4? IF
                I 4 + 50 54 52 20 SIG4? IF
                    I RSDP-CSUM IF
                        I UNLOOP EXIT
                    THEN
                THEN
            THEN
        10 +LOOP
    ELSE DROP THEN
    \ Main BIOS area: E0000-FFFFF
    100000 E0000 DO
        I 52 53 44 20 SIG4? IF
            I 4 + 50 54 52 20 SIG4? IF
                I RSDP-CSUM IF
                    I UNLOOP EXIT
                THEN
            THEN
        THEN
    10 +LOOP
    0 ;

\ ---- RSDT walk for FADT ----
: FIND-FADT ( -- addr | 0 )
    RSDT-ADDR @ DUP 4 + @ ( rsdt len )
    24 - 4 / ( entry-count )
    SWAP 24 + SWAP ( first-entry count )
    0 DO
        DUP I 4 * + @
        DUP 46 41 43 50 SIG4? IF
            NIP UNLOOP EXIT
        THEN
        DROP
    LOOP DROP 0 ;

\ ---- Match _S5_ at addr ----
: S5? ( addr -- flag )
    DUP    C@ 5F <> IF DROP 0 EXIT THEN
    DUP 1+ C@ 53 <> IF DROP 0 EXIT THEN
    DUP 2 + C@ 35 <> IF DROP 0 EXIT THEN
        3 + C@ 5F = ;

\ ---- Extract SLP_TYPa from AML byte ----
\ 0x0A = BytePrefix (next byte is value)
\ 0x00 = ZeroOp, 0x01 = OneOp (bare)
: AML-BYTE ( addr -- value )
    DUP C@ 0A = IF
        1+ C@
    ELSE C@ THEN 7 AND ;

\ ---- Scan DSDT for _S5_ object ----
\ AML: "_S5_" + PkgOp(12) + PkgLen
\ + NumElements + SLP_TYPa
: FIND-S5 ( -- slp-type | -1 )
    DSDT-ADDR @ DUP 4 + @ ( dsdt len )
    OVER + SWAP 24 + ( end start )
    DO
        I S5? IF
            I 4 + C@ 12 = IF
                \ PkgLen must be 1-byte
                I 5 + C@ 3F > IF
                    -1 UNLOOP EXIT
                THEN
                \ Skip name+PkgOp+PkgLen
                I 6 +
                \ Skip NumElements byte
                1+ AML-BYTE
                UNLOOP EXIT
            THEN
        THEN
    LOOP -1 ;

\ ---- Enable ACPI mode if needed ----
: ENSURE-ACPI ( -- ok? )
    PM1A-PORT @ INW 1 AND IF
        -1 EXIT
    THEN
    SMI-PORT @ 0= IF
        ." SMI_CMD=0" CR 0 EXIT
    THEN
    ACPI-EN @ SMI-PORT @ OUTB
    \ Poll PM1a_CNT for SCI_EN, timeout
    1000 0 DO
        PM1A-PORT @ INW 1 AND IF
            -1 UNLOOP EXIT
        THEN
    LOOP
    ." ACPI enable timeout" CR 0 ;

\ ---- Full ACPI shutdown ----
: ACPI-SHUTDOWN ( -- )
    SCAN-RSDP DUP 0= IF
        DROP ." No RSDP" CR EXIT
    THEN
    RSDP-ADDR !
    RSDP-ADDR @ 10 + @ RSDT-ADDR !
    FIND-FADT DUP 0= IF
        DROP ." No FADT" CR EXIT
    THEN
    FADT-ADDR !
    FADT-ADDR @ 28 + @ DSDT-ADDR !
    DSDT-ADDR @ 0= IF
        ." No DSDT" CR EXIT
    THEN
    FADT-ADDR @ 40 + @ PM1A-PORT !
    FADT-ADDR @ 30 + @ FF AND SMI-PORT !
    FADT-ADDR @ 34 + C@ ACPI-EN !
    FIND-S5 DUP -1 = IF
        DROP ." No _S5_" CR EXIT
    THEN
    SLP-TYPE !
    ENSURE-ACPI 0= IF
        ." SCI_EN not set, trying" CR
    THEN
    SLP-TYPE @ A LSHIFT 2000 OR
    PM1A-PORT @ OUTW ;

\ ---- User-facing word ----
: SHUTDOWN ( -- )
    ACPI-SHUTDOWN ;

ONLY FORTH DEFINITIONS
