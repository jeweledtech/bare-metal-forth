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
    DUP 0= IF ." HCRST poll timeout, cmd=" PA @ @ .H8 CR THEN
    OP-BASE 4 + 800 3E8 POLL-CLEAR
    DUP 0= IF ." CNR poll timeout, sts=" PA @ @ .H8 CR THEN
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

\ ---- Step 2c: DCBAA / rings / Running / NOP ----
\ Timeout prints above go through PCI-ENUM's .H8
\ (base-transparent), closing the 2b render debt.
\ Allocation records: 0 = not held.  All pages come
\ from PHYS-ALLOC; XHCI-DOWN cross-checks each record
\ against the owner table (OWN-FIND + size match)
\ BEFORE releasing, so a record freed behind our back
\ is SKIPPED (code 1, partial), never double-released.
VARIABLE XDCBAA  VARIABLE XCRING
VARIABLE XERING  VARIABLE XERST
VARIABLE XSPA    VARIABLE XSPN   VARIABLE SPB
VARIABLE XENQ    VARIABLE XCCS
VARIABLE XEDQ    VARIABLE XECS

\ Runtime + doorbell bases (RTSOFF cap+18 mask E0;
\ DBOFF cap+14 mask FC).  Interrupter 0 lives at
\ runtime +20: ERSTSZ +28, ERSTBA +30, ERDP +38.
: RT-BASE ( -- addr )
    XHCI-BASE @ 18 + @ FFFFFFE0 AND
    XHCI-BASE @ + ;
: DB-BASE ( -- addr )
    XHCI-BASE @ 14 + @ FFFFFFFC AND
    XHCI-BASE @ + ;
: DOORBELL0 ( -- ) 0 DB-BASE ! ;

: PG0 ( addr -- )   \ zero one page
    1000 0 DO 0 OVER I + ! 4 +LOOP DROP ;

\ Scratchpad count: HCSPARAMS2 (cap+8) Hi bits 25:21,
\ Lo bits 31:27, count = Hi*32 + Lo.  Predicted 0 in
\ QEMU (named alt >0 -> array + 1 contiguous block).
: SP-COUNT ( -- n )
    XHCI-BASE @ 8 + @
    DUP 15 RSHIFT 1F AND 20 *
    SWAP 1B RSHIFT 1F AND OR ;

: SP-SETUP ( -- flag )
    1000 PHYS-ALLOC DUP XSPA ! 0= IF 0 EXIT THEN
    XSPN @ 1000 * PHYS-ALLOC DUP SPB ! 0= IF
        XSPA @ 1000 PHYS-RELEASE 0 XSPA !
        0 EXIT THEN
    XSPA @ PG0
    XSPN @ 0 DO
        SPB @ I 1000 * + XSPA @ I 8 * + !
    LOOP
    XSPA @ XDCBAA @ !  0 XDCBAA @ 4 + !  -1 ;

: XUP-FAIL ( -- 0 )
    XERST @ 0<> IF
        XERST @ 1000 PHYS-RELEASE 0 XERST ! THEN
    XERING @ 0<> IF
        XERING @ 1000 PHYS-RELEASE 0 XERING ! THEN
    XCRING @ 0<> IF
        XCRING @ 1000 PHYS-RELEASE 0 XCRING ! THEN
    XDCBAA @ 0<> IF
        XDCBAA @ 1000 PHYS-RELEASE 0 XDCBAA ! THEN
    0 ;

\ XHCI-UP: allocate DCBAA + 16-TRB command ring page +
\ event ring segment + 1-entry ERST, program DCBAAP /
\ CONFIG / CRCR (RCS=1) / ERSTSZ / ERSTBA / ERDP, init
\ producer (XENQ/XCCS) and consumer (XEDQ/XECS).
\ Fail-closed: any refused allocation releases the
\ rest and returns 0.
: XHCI-UP ( -- flag )
    XHCI-BASE @ 0= IF 0 EXIT THEN
    XDCBAA @ 0<> IF 0 EXIT THEN
    1000 PHYS-ALLOC DUP XDCBAA ! 0= IF
        XUP-FAIL EXIT THEN
    1000 PHYS-ALLOC DUP XCRING ! 0= IF
        XUP-FAIL EXIT THEN
    1000 PHYS-ALLOC DUP XERING ! 0= IF
        XUP-FAIL EXIT THEN
    1000 PHYS-ALLOC DUP XERST ! 0= IF
        XUP-FAIL EXIT THEN
    XDCBAA @ PG0  XCRING @ PG0
    XERING @ PG0  XERST @ PG0
    SP-COUNT XSPN !
    XSPN @ 0<> IF
        SP-SETUP 0= IF XUP-FAIL EXIT THEN THEN
    XDCBAA @ OP-BASE 30 + !  0 OP-BASE 34 + !
    MAX-SLOTS OP-BASE 38 + !
    XCRING @ 1 OR OP-BASE 18 + !  0 OP-BASE 1C + !
    1 RT-BASE 28 + !
    XERING @ XERST @ !  0 XERST @ 4 + !
    100 XERST @ 8 + !  0 XERST @ C + !
    XERST @ RT-BASE 30 + !  0 RT-BASE 34 + !
    XERING @ RT-BASE 38 + !  0 RT-BASE 3C + !
    0 XENQ !  1 XCCS !  0 XEDQ !  1 XECS !  -1 ;

: XHCI-RUN ( -- flag )
    XHCI-BASE @ 0= IF 0 EXIT THEN
    USBCMD@ 1 OR USBCMD!
    OP-BASE 4 + 1 3E8 POLL-CLEAR ;

\ Command ring producer.  16 TRBs; slot 15 is the link
\ TRB (type 6, Toggle Cycle) written AT the wrap with
\ the pre-toggle cycle so the controller follows it,
\ then XCCS flips -- the riskiest word in 2c, and 32
\ NOPs cross it twice.  NOP command = type 17 (hex),
\ control 5C00 OR cycle.
VARIABLE TRA
: CR-TRB ( -- addr ) XCRING @ XENQ @ 10 * + ;
: TRB-NOP! ( -- )
    CR-TRB TRA !
    0 TRA @ !  0 TRA @ 4 + !  0 TRA @ 8 + !
    5C00 XCCS @ OR TRA @ C + !
    1 XENQ +!
    XENQ @ F = IF
        XCRING @ F0 + TRA !
        XCRING @ TRA @ !
        0 TRA @ 4 + !  0 TRA @ 8 + !
        1802 XCCS @ OR TRA @ C + !
        0 XENQ !  XCCS @ 1 XOR XCCS ! THEN ;

\ Event ring consumer.  Own counter (EVN): POLL-UNTIL/
\ POLL-CLEAR are NOT re-entrant (PN/PA/PM globals) and
\ are never nested here.  Budget 100 (hex) ms.
VARIABLE EVN
: EV-TRB ( -- addr ) XERING @ XEDQ @ 10 * + ;
: EV-RDY? ( -- flag )
    EV-TRB C + @ 1 AND XECS @ = ;
: EV-POLL ( -- flag )
    100 EVN !
    BEGIN EV-RDY? 0= EVN @ 0> AND
    WHILE 1 MS-DELAY -1 EVN +! REPEAT
    EV-RDY? ;
: EV-NEXT ( -- )   \ consume + publish ERDP (EHB set)
    1 XEDQ +!
    XEDQ @ 100 = IF
        0 XEDQ !  XECS @ 1 XOR XECS ! THEN
    EV-TRB 8 OR RT-BASE 38 + !  0 RT-BASE 3C + ! ;

\ One NOP round-trip: enqueue, ring, await completion.
\ Per-NOP doorbell keeps the producer from overrunning
\ the 15 usable slots per cycle.
: NOP1 ( -- flag )
    TRB-NOP! DOORBELL0
    EV-POLL DUP IF EV-NEXT THEN ;
VARIABLE NTC  VARIABLE NTN
: NOP-TEST ( n -- count )
    0 NTC !  NTN !
    BEGIN NTC @ NTN @ < DUP IF DROP NOP1 THEN
    WHILE 1 NTC +! REPEAT
    NTC @ ;

\ Cross-checked release: OWN-FIND miss or size
\ mismatch -> skip (partial), never a blind
\ PHYS-RELEASE that would double-release a page freed
\ behind our back.
VARIABLE XDP
: XREL1 ( addr size -- )
    OVER OWN-FIND DUP 0= IF
        DROP 2DROP 1 XDP ! EXIT THEN
    @ OVER = 0= IF 2DROP 1 XDP ! EXIT THEN
    PHYS-RELEASE ;

\ Codes: -1 all released / 0 nothing held / 1 partial
\ (some record vanished; the rest were released).
: XHCI-DOWN ( -- code )
    XDCBAA @ XCRING @ OR XERING @ OR
    XERST @ OR XSPA @ OR 0= IF 0 EXIT THEN
    XHCI-HALT DROP
    0 XDP !
    XSPA @ 0<> IF
        XSPA @ @ XSPN @ 1000 * XREL1
        XSPA @ 1000 XREL1
        0 XSPA !  0 XSPN ! THEN
    XERST @ 0<> IF
        XERST @ 1000 XREL1 0 XERST ! THEN
    XERING @ 0<> IF
        XERING @ 1000 XREL1 0 XERING ! THEN
    XCRING @ 0<> IF
        XCRING @ 1000 XREL1 0 XCRING ! THEN
    XDCBAA @ 0<> IF
        XDCBAA @ 1000 XREL1 0 XDCBAA ! THEN
    XDP @ IF 1 ELSE -1 THEN ;

\ ---- Step 2d: PORTSC decode + port survey -- READ-ONLY ----
\ Every PORTSC change bit (CSC/PEC/PRC/...) is RW1C: a
\ read-modify-write clears them silently.  NO word in this
\ section writes a port register; port reset is step 3.
\ Port array: OP-BASE + 400, stride 10, ports 1-based.
\ PORTSC-ADDR refuses ports outside 1..MAX-PORTS (addr|0):
\ the dword below the array and the one past it both read
\ plausibly (same fail-closed family as XREL1).
: PORTSC-ADDR ( port# -- addr|0 )
    DUP 1 < OVER MAX-PORTS > OR IF DROP 0 EXIT THEN
    1- 10 * OP-BASE 400 + + ;
\ Refused port reads as 0: decoders on 0 give the
\ fail-safe answer (no device, no power).
: PORTSC@ ( port# -- x|0 ) PORTSC-ADDR DUP IF @ THEN ;
\ Decoders take the VALUE, not the port, so suite controls
\ feed synthetic dwords with hardware never consulted.
: P-CCS ( x -- flag ) 1 AND 0<> ;
: P-PED ( x -- flag ) 2 AND 0<> ;
: P-PR  ( x -- flag ) 10 AND 0<> ;
: P-PLS ( x -- n ) 5 RSHIFT F AND ;
: P-PP  ( x -- flag ) 200 AND 0<> ;
: P-SPEED ( x -- n ) A RSHIFT F AND ;
: P-CSC ( x -- flag ) 20000 AND 0<> ;
\ Kernel has no LEAVE: full walk, keep the FIRST hit.
: #CONNECTED ( -- n )
    0 MAX-PORTS 1+ 1 DO
        I PORTSC@ P-CCS IF 1+ THEN LOOP ;
: FIRST-CCS ( -- port#|0 )
    0 MAX-PORTS 1+ 1 DO
        I PORTSC@ P-CCS OVER 0= AND IF DROP I THEN
    LOOP ;
\ Survey display for the 2e iron trip (unscored output).
: .PORT ( port# -- )
    DUP . PORTSC@
    DUP P-CCS IF ." conn " THEN
    DUP P-PED IF ." en " THEN
    DUP P-SPEED . ." spd "
    P-PLS . ." pls " CR ;
: .PORTS ( -- ) MAX-PORTS 1+ 1 DO I .PORT LOOP ;

." XHCI vocab loaded" CR

ONLY FORTH DEFINITIONS
DECIMAL
