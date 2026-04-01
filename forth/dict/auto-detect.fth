\ ============================================
\ CATALOG: AUTO-DETECT
\ CATEGORY: system
\ PLATFORM: x86
\ SOURCE: hand-written
\ REQUIRES: PCI-ENUM RTL8168 AHCI
\ CONFIDENCE: medium
\ ============================================
\
\ Automatic hardware detection and init.
\ Scans PCI bus, identifies known devices,
\ initializes supported hardware, brings up
\ network console if a supported NIC is found.
\
\ Runs automatically on real hardware boot.
\ Skips init on QEMU (detects 1234:1111 VGA).
\
\ Usage:
\   AUTO-DETECT   ( auto-runs at boot )
\   QEMU?         ( -- flag )
\
\ ============================================

VOCABULARY AUTO-DETECT
AUTO-DETECT DEFINITIONS
ALSO PCI-ENUM
ALSO RTL8168
ALSO AHCI
HEX

\ ---- State ----
VARIABLE NIC-OK
VARIABLE AHCI-OK
VARIABLE KNOWN-N

\ ---- QEMU detection ----
\ QEMU standard VGA is 1234:1111.
: QEMU? ( -- flag )
    1234 1111 PCI-FIND IF
        DROP DROP DROP -1
    ELSE
        0
    THEN
;

\ ---- Device name lookup ----
\ Print name for known vendor:device.
\ Returns -1 if known, 0 if unknown.
: DEVICE-KNOWN? ( vendor device -- flag )
    OVER 10EC = IF
        DUP 8168 = IF
            2DROP ." RTL8168 GbE" -1 EXIT
        THEN
        DUP 8139 = IF
            2DROP ." RTL8139 100M" -1 EXIT
        THEN
    THEN
    OVER 8086 = IF
        DUP 9D03 = IF
            2DROP ." Intel AHCI" -1 EXIT
        THEN
        DUP 2922 = IF
            2DROP ." ICH9 AHCI" -1 EXIT
        THEN
        DUP 3A22 = IF
            2DROP ." ICH10 AHCI" -1 EXIT
        THEN
        DUP 9D2F = IF
            2DROP ." xHCI USB" -1 EXIT
        THEN
        DUP 5916 = IF
            2DROP ." HD Graphics 620" -1 EXIT
        THEN
        DUP 3EA0 = IF
            2DROP ." UHD Graphics 620" -1 EXIT
        THEN
        DUP 15A3 = IF
            2DROP ." Intel I219 GbE" -1 EXIT
        THEN
        DUP 10EA = IF
            2DROP ." Intel I217 GbE" -1 EXIT
        THEN
    THEN
    OVER 1022 = IF
        DUP 7901 = IF
            2DROP ." AMD AHCI" -1 EXIT
        THEN
    THEN
    OVER 14E4 = IF
        DUP 1682 = IF
            2DROP ." Broadcom BCM57xx" -1 EXIT
        THEN
    THEN
    2DROP 0
;

\ ---- Init dispatch ----
\ Call init word for known vendor:device.
: DEVICE-INIT ( vendor device -- )
    OVER 10EC = IF
        DUP 8168 = IF
            2DROP RTL8168-INIT EXIT
        THEN
    THEN
    OVER 8086 = IF
        DUP 9D03 = IF
            2DROP AHCI-INIT EXIT
        THEN
        DUP 2922 = IF
            2DROP AHCI-INIT EXIT
        THEN
        DUP 3A22 = IF
            2DROP AHCI-INIT EXIT
        THEN
    THEN
    OVER 1022 = IF
        DUP 7901 = IF
            2DROP AHCI-INIT EXIT
        THEN
    THEN
    2DROP
;

\ ---- Walk PCI table ----
\ Print all known devices with location.
: SCAN-KNOWN ( -- )
    PCI-COUNT @ 0<> IF
        PCI-COUNT @ 0 DO
            I PCI-ENTRY
            DUP 4 + W@
            OVER 6 + W@
            2DUP DEVICE-KNOWN? IF
                2DROP
                SPACE ." at "
                DUP C@ .H2 3A EMIT
                DUP 1+ C@ .H2 2E EMIT
                2 + C@ .H2 CR
                1 KNOWN-N +!
            ELSE
                2DROP DROP
            THEN
        LOOP
    THEN
;

\ ---- Hardware init ----
: TRY-NIC ( -- )
    RTL8168-INIT
    RTL-FOUND @ IF
        -1 NIC-OK !
    THEN
;

: TRY-AHCI ( -- )
    AHCI-INIT
    AH-FOUND @ IF
        -1 AHCI-OK !
    THEN
;

\ ---- Boot banner ----
: BOOT-BANNER ( -- )
    ." --- "
    DECIMAL KNOWN-N @ . HEX
    ." known, "
    0
    NIC-OK @ IF 1+ THEN
    AHCI-OK @ IF 1+ THEN
    DECIMAL . HEX
    ." active ---" CR
;

\ ---- Report ----
: AUTO-DETECT-REPORT ( -- )
    ." NIC: "
    NIC-OK @ IF
        ." OK" CR RTL8168-STATUS
    ELSE
        ." none" CR
    THEN
    ." AHCI: "
    AHCI-OK @ IF
        ." OK" CR
    ELSE
        ." none" CR
    THEN
;

\ ---- Main entry point ----
: AUTO-DETECT ( -- )
    0 NIC-OK !
    0 AHCI-OK !
    0 KNOWN-N !
    QEMU? IF EXIT THEN
    ." === ForthOS Auto-Detect ===" CR
    \ Init NIC first so net console
    \ captures subsequent output
    TRY-NIC
    NIC-OK @ IF NET-CONSOLE-ON THEN
    \ Now scan and print known devices
    \ (visible on net console if NIC ok)
    SCAN-KNOWN
    \ Init storage
    TRY-AHCI
    AHCI-OK @ IF MBR. THEN
    BOOT-BANNER
;

\ Auto-run on boot (skips in QEMU)
AUTO-DETECT

ONLY FORTH DEFINITIONS
DECIMAL
