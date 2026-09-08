\ ============================================
\ CATALOG: XHCI
\ CATEGORY: usb
\ PLATFORM: x86
\ SOURCE: hand-written
\ REQUIRES: PCI-ENUM ( PCI-READ FIND-XHCI PCI-ENABLE )
\ REQUIRES: HARDWARE ( MS-DELAY )
\ ============================================
\ Step 2a: 64-bit-safe BAR read (correctness word).
\ Iron reading 2026-09-05 (HP 15-bs0xx): BAR0=B1210004,
\ type bits 2:1 = 10 (64-bit BAR), upper dword (config
\ offset 14) = 0. Ruling: refuse the device if the upper
\ dword is nonzero; this word is NOT an enabler for >4GB
\ MMIO (reading 3 ruled out). ECAM deferred.
\ Block-loaded, never embedded: no boot-time caller.

VOCABULARY XHCI
XHCI DEFINITIONS
ALSO PCI-ENUM
ALSO HARDWARE
HEX

\ BAR64-MASK: pure logic, exposed so refusal paths are
\ testable with pushed literals. I/O bit set -> 0; type
\ 00 -> mask lo, hi ignored (config +4 is the NEXT BAR
\ and must never enter the decision); type 10 -> hi must
\ be 0 else refuse; reserved types 01/11 -> 0. Mask is
\ FFFFFFF0 -- same as PCI-BAR@'s MMIO leg.
: BAR64-MASK ( lo hi -- addr | 0 )
    OVER 1 AND IF 2DROP 0 EXIT THEN
    OVER 6 AND DUP 0= IF
        DROP DROP FFFFFFF0 AND EXIT THEN
    4 = IF
        IF DROP 0 ELSE FFFFFFF0 AND THEN EXIT THEN
    2DROP 0 ;

\ Scratch for the two-dword config read.
VARIABLE XR-B  VARIABLE XR-D  VARIABLE XR-F  VARIABLE XR-R

\ PCI-BAR64@: branches on the type bits BEFORE touching
\ offset +4. Non-64-bit types feed hi=0 (ignored or
\ refused inside BAR64-MASK).
: PCI-BAR64@ ( bus dev func bar# -- addr | 0 )
    4 * 10 + XR-R !  XR-F !  XR-D !  XR-B !
    XR-B @ XR-D @ XR-F @ XR-R @ PCI-READ
    DUP 6 AND 4 = IF
        XR-B @ XR-D @ XR-F @ XR-R @ 4 + PCI-READ
    ELSE 0 THEN
    BAR64-MASK ;

\ ---- Step 2b: bind / caps / halt / reset / handoff ----
\ Counted polls only: the timeout path is proven against a
\ suite-owned cell (a zero-iteration loop would pass every
\ hardware check because the controller is predicted already
\ halted on entry).  1 ms per iteration via MS-DELAY.
\ NOT RE-ENTRANT: PN/PA/PM are globals, so a nested poll
\ clobbers the outer one's state.  Sequential calls are safe
\ (XHCI-RESET); 2c event-ring polling must not nest these.
VARIABLE PN  VARIABLE PA  VARIABLE PM
: POLL@ ( -- x ) PA @ @ PM @ AND ;
: POLL-UNTIL ( addr mask limit -- flag )
    PN ! PM ! PA !
    BEGIN POLL@ 0= PN @ 0> AND
    WHILE 1 MS-DELAY -1 PN +! REPEAT
    POLL@ 0<> ;
: POLL-CLEAR ( addr mask limit -- flag )
    PN ! PM ! PA !
    BEGIN POLL@ 0<> PN @ 0> AND
    WHILE 1 MS-DELAY -1 PN +! REPEAT
    POLL@ 0= ;

VARIABLE XHCI-BASE
: XHCI-BIND ( -- flag )
    FIND-XHCI 0= IF 0 XHCI-BASE ! 0 EXIT THEN
    XR-F ! XR-D ! XR-B !
    XR-B @ XR-D @ XR-F @ PCI-ENABLE
    XR-B @ XR-D @ XR-F @ 0 PCI-BAR64@
    DUP XHCI-BASE ! 0<> ;

\ Caps: HCIVERSION read as (dword at +0) >> 16, avoiding a
\ 16-bit fetch the kernel does not have.
: CAP-LEN ( -- n ) XHCI-BASE @ C@ ;
: HCI-VER ( -- x ) XHCI-BASE @ @ 10 RSHIFT ;
: HCS1 ( -- x ) XHCI-BASE @ 4 + @ ;
: MAX-SLOTS ( -- n ) HCS1 FF AND ;
: MAX-PORTS ( -- n ) HCS1 18 RSHIFT FF AND ;
: HCC1 ( -- x ) XHCI-BASE @ 10 + @ ;
: OP-BASE ( -- addr ) XHCI-BASE @ CAP-LEN + ;
: USBCMD@ ( -- x ) OP-BASE @ ;
: USBCMD! ( x -- ) OP-BASE ! ;
: USBSTS@ ( -- x ) OP-BASE 4 + @ ;

\ Halt before reset: HCRST on a running controller is
\ undefined per spec.  HCH = USBSTS bit 0, HCRST = USBCMD
\ bit 1, CNR = USBSTS bit B.
: XHCI-HALT ( -- flag )
    USBCMD@ FFFFFFFE AND USBCMD!
    OP-BASE 4 + 1 20 POLL-UNTIL ;
\ Reset budget 3E8 (1000 ms): QEMU resets instantly but real
\ silicon can hold HCRST for hundreds of ms and CNR longer
\ still (Intel parts).  On timeout, print which poll failed
\ and the UNMASKED register so 2e can tell "stuck after the
\ full budget" (bit still set) from a dead window (all-ones,
\ prints -1) -- a masked print would show both the same.
: XHCI-RESET ( -- flag )
    USBCMD@ 2 OR USBCMD!
    OP-BASE 2 3E8 POLL-CLEAR
    DUP 0= IF ." HCRST poll timeout, cmd=" PA @ @ . CR THEN
    OP-BASE 4 + 800 3E8 POLL-CLEAR
    DUP 0= IF ." CNR poll timeout, sts=" PA @ @ . CR THEN
    AND ;

\ Handoff SKELETON: locate + classify only.  The request/
\ timeout/fail-closed sequence is 2e's third outcome.
\ XCAPS counts visited caps so a runaway walk is visible.
VARIABLE XCAPS  VARIABLE XCID  VARIABLE XCP
: XECP-BASE ( -- addr|0 )
    HCC1 10 RSHIFT DUP 0= IF EXIT THEN
    4 * XHCI-BASE @ + ;
: XECP-FIND ( id -- addr|0 )
    XCID !  0 XCAPS !  XECP-BASE XCP !
    BEGIN XCP @ 0<> XCAPS @ 10 < AND
    WHILE
        1 XCAPS +!
        XCP @ @ FF AND XCID @ = IF XCP @ EXIT THEN
        XCP @ @ 8 RSHIFT FF AND
        DUP 0= IF DROP 0 XCP ! ELSE 4 * XCP +! THEN
    REPEAT 0 ;
\ 0 = legacy cap absent; 1 = present + BIOS Owned Semaphore
\ set (bit 16 -- decimal, written out to dodge the base pun);
\ 2 = present, BIOS bit clear.  Code 2 does NOT check the OS
\ Owned Semaphore (bit 24) -- it measures only that BIOS is
\ not asserting ownership.  The stuck case for 2e is code 1
\ persisting after an ownership request.
: XHCI-OWNER ( -- code )
    1 XECP-FIND DUP 0= IF EXIT THEN
    @ 10000 AND IF 1 ELSE 2 THEN ;

." XHCI vocab loaded" CR

ONLY FORTH DEFINITIONS
DECIMAL
