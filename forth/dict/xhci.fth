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
\ HRST-LEFT: PN's leftover count after the HCRST poll,
\ captured before the CNR poll clobbers PN (shared cell).
\ Elapsed ms = 1000 HRST-LEFT @ - ; turns the reasoned 1000 ms
\ budget into a measurement on iron.
VARIABLE HRST-LEFT
: XHCI-RESET ( -- flag )
    USBCMD@ 2 OR USBCMD!
    OP-BASE 2 3E8 POLL-CLEAR
    PN @ HRST-LEFT !
    DUP 0= IF ." HCRST poll timeout, cmd=" PA @ @ .H8 CR THEN
    OP-BASE 4 + 800 3E8 POLL-CLEAR
    DUP 0= IF ." CNR poll timeout, sts=" PA @ @ .H8 CR THEN
    AND ;

\ Handoff SKELETON: locate + classify only.  The request/
\ timeout/fail-closed sequence is 2e's third outcome.
\ XCAPS counts visited caps so a runaway walk is visible.
VARIABLE XCAPS  VARIABLE XCID  VARIABLE XCP
\ Unbound-base guards (iron 2026-09-10, a6a6cae correction 2):
\ XHCI-CLAIM ran before XHCI-BIND, HCC1 read the real-mode
\ IVT at 10, and it returned 0 -- "cap absent" -- only because
\ bits 31:16 there were clear.  (CLAIM) writes.  Address words
\ refuse with 0 (every caller dereferences nonzero); the
\ code-returning wrappers refuse with -2, unused by both code
\ sets, so a refusal can never be read as outcome A.  A zero
\ check is the whole predicate: XHCI-BIND is the only writer
\ and stores 0 or PCI-BAR64@'s fail-closed addr|0.  Red-first
\ evidence: docs/evidence/xhci-guard-red-2026-09-11.log.
: XECP-BASE ( -- addr|0 )
    XHCI-BASE @ 0= IF 0 EXIT THEN
    HCC1 10 RSHIFT DUP 0= IF EXIT THEN
    4 * XHCI-BASE @ + ;
: XECP-FIND ( id -- addr|0 )
    XHCI-BASE @ 0= IF DROP 0 EXIT THEN
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
    XHCI-BASE @ 0= IF -2 EXIT THEN
    1 XECP-FIND DUP 0= IF EXIT THEN
    @ 10000 AND IF 1 ELSE 2 THEN ;

\ ---- Step 2e prep: claim + SMI-clear (address-taking) ----
\ (CLAIM) requests ownership on ANY cap-present outcome
\ (uniform-claim ruling): set OS Owned Semaphore (bit 24,
\ 1000000 hex), poll BIOS bit (10000) clear for the full
\ 1000 ms budget.  -1 = released (or never held -- the
\ OWNER/CLAIM pair adjacent in the log preserves which);
\ 1 = stuck past budget, unmasked print, card STOPS.
\ Address-taking (2b poll-control pattern): QEMU's cap is
\ absent, so claim/stuck paths run on suite-owned cells.
\ Untestable in habitat: released-AFTER-held timing.
: (CLAIM) ( addr -- code )
    DUP @ 1000000 OR OVER !
    DUP 10000 3E8 POLL-CLEAR
    IF DROP -1 ELSE
        ." handoff stuck, legsup=" @ .H8 CR 1 THEN ;
: XHCI-CLAIM ( -- code )
    XHCI-BASE @ 0= IF -2 EXIT THEN
    1 XECP-FIND DUP IF (CLAIM) THEN ;
\ SMI-clear on USBLEGCTLSTS (legsup + 4): read first --
\ enables mask E011 (bits 0,4,13,14,15; bit 4 = SMI on Host
\ System Error, armed during the reset leg).  Already clear
\ => code -1, NO write (that is a finding, not a failure).
\ Else write (old AND E1FEE) OR E0000000: E1FEE preserves
\ RsvdP groups 3:1, 12:5, 19:17; E0000000 writes 1 to the
\ RW1C status bits (clears them).  Masks verified against
\ Linux xhci-ext-caps.h / spec 7.1.2 -- NOT recalled.
\ code 1 = enables read back clear; 2 = write did not stick
\ (card treats as STOP; untestable in habitat).
: (SMI-OFF) ( addr -- code )
    DUP @ E011 AND 0= IF DROP -1 EXIT THEN
    DUP @ E1FEE AND E0000000 OR OVER !
    @ E011 AND 0= IF 1 ELSE 2 THEN ;
: SMI-OFF ( -- code )
    XHCI-BASE @ 0= IF -2 EXIT THEN
    1 XECP-FIND DUP IF 4 + (SMI-OFF) THEN ;
\ Memdisk safety gate (card Section 4.5): kernel sysvar
\ MEMDISK_BASE at 28098 selects the RAM-vs-ATA block path at
\ boot.  0 = not memdisk-resident => card STOPS before the
\ reset leg (XHCI-RESET kills the controller behind a USB
\ boot stick).  Iron pre-registration: nonzero + 4 KiB-
\ aligned; prior HP reading 37BB7000 (2026-09-05).
: MEMDISK-BASE@ ( -- x ) 28098 @ ;

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
    XCRING @ 0= IF EXIT THEN
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
\ Kernel has no LEAVE: full walk.  FIRST-CCS (which port) is
\ fixture-side from 3a: on iron it returns port 1, the internal
\ high-speed device -- policy stays out of the shipped vocab.
: #CONNECTED ( -- n )
    0 MAX-PORTS 1+ 1 DO
        I PORTSC@ P-CCS IF 1+ THEN LOOP ;
\ Survey display for the 2e iron trip (unscored output).
\ .D: fixed-base decimal print, closing the base-transparency
\ debt (P-PLS 15 rendered "F" under HEX = the F-vs-15
\ ambiguity, 3rd appearance of the class).  No >R/R>: .PORTS
\ calls this inside DO..LOOP and the project keeps the return
\ stack untouched in loop bodies.
: .D ( n -- ) BASE @ SWAP DECIMAL . BASE ! ;
\ .PSC takes the VALUE (suite feeds synthetics); raw dword
\ via .H8 first so the iron log carries every bit.
: .PSC ( x -- )
    DUP .H8 ."  "
    DUP P-CCS IF ." conn " THEN
    DUP P-PED IF ." en " THEN
    DUP P-SPEED .D ." spd "
    P-PLS .D ." pls " CR ;
: .PORT ( port# -- ) DUP .D PORTSC@ .PSC ;
: .PORTS ( -- ) MAX-PORTS 1+ 1 DO I .PORT LOOP ;

\ ---- Step 3a: port reset (first port WRITE), typed events ----
\ PORTSC attribute classes, xHCI 1.2 section 5.4.8 (Table 5-27):
\   RO/ROS  : 0 CCS, 3 OCA, 13:10 speed, 24 CAS, 30 DR
\   RWS     : 8:5 PLS, 9 PP, 15:14 PIC, 27:25 WCE/WDE/WOE
\   RW      : 16 LWS (write 0: leave the link state alone)
\   RW1S    : 4 PR, 31 WPR
\   RW1CS   : 1 PED (writing 1 DISABLES the port), 23:17 change
\   RsvdZ   : 2, 29:28
\ A read-modify-write must carry only the RO + RWS classes, so
\ it neither clears a change bit by accident nor disables the
\ port.  Derived from the table: bits 0,3,5-15,25-27,30 =
\ 4E00FFE9 (bit 24 left out: RO ignores writes either way).
\ Cross-checked equal to Linux xhci-hub.c XHCI_PORT_RO|RWS
\ at pinned tag v6.12 (sha256 7cc388b7...): the spec is the
\ source, Linux a version-pinned check (not master, which can
\ drift).  Change bits 23:17 = FE0000, cleared by writing 1.
: P-NEUTRAL ( x -- x' ) 4E00FFE9 AND ;
: P-PRC ( x -- flag ) 200000 AND 0<> ;
\ PORT-RESET: refuses (0) an unbound base (PORTSC-ADDR alone is
\ fail-open read-only; this word writes), a port out of range,
\ or an empty port (PR with CCS clear is undefined).  Writes
\ neutral|PR, polls PRC (bit 21) set within 3E8 ms, keeps PN's
\ leftover in PRST-LEFT (elapsed ms = 1000 PRST-LEFT @ -), then
\ writes neutral|FE0000 to clear all seven change bits.  -1 only
\ if PRC was seen AND PED reads set afterwards.  The reset runs
\ halted or running; the PSCE it raises reaches the event ring
\ only when running.
VARIABLE PRST-LEFT  VARIABLE PRA
: PORT-RESET ( port# -- flag )
    XHCI-BASE @ 0= IF DROP 0 EXIT THEN
    PORTSC-ADDR DUP 0= IF EXIT THEN
    DUP @ P-CCS 0= IF DROP 0 EXIT THEN
    PRA !
    PRA @ @ P-NEUTRAL 10 OR PRA @ !
    PRA @ 200000 3E8 POLL-UNTIL
    PN @ PRST-LEFT !
    PRA @ @ P-NEUTRAL FE0000 OR PRA @ !
    PRA @ @ P-PED AND ;

\ Event TRB fields (xHCI 1.2 section 6.4.2; TRB type field
\ 6.4.6 Table 6-91): type = control bits 15:10; completion
\ code = status bits 31:24; slot = control bits 31:24; PSCE
\ port id = dword0 bits 31:24 (6.4.2.3).  VALUE-taking
\ decoders (suite feeds literals); EV-* read the TRB at the
\ dequeue pointer.
: T-TYPE ( ctrl -- n ) A RSHIFT 3F AND ;
: T-CC ( sts -- n ) 18 RSHIFT FF AND ;
: T-SLOT ( ctrl -- n ) 18 RSHIFT FF AND ;
: T-PORT ( d0 -- n ) 18 RSHIFT FF AND ;
: EV-D0 ( -- x ) EV-TRB @ ;
: EV-TYPE ( -- n ) EV-TRB C + @ T-TYPE ;
: EV-CC ( -- n ) EV-TRB 8 + @ T-CC ;
: EV-SLOT ( -- n ) EV-TRB C + @ T-SLOT ;
\ EV-WAIT: wait for an event of one type.  Any other type is
\ consumed and RECORDED (XEV-SKIP count, XEV-LAST type): a port
\ status change landing ahead of a command completion is normal
\ traffic, but a silent skip would hide a runaway, so the skip
\ count is bounded at 14 (20 decimal).  -1 = the wanted event is
\ at EV-TRB, NOT consumed -- caller reads its fields, then
\ EV-NEXT.  0 = poll budget or skip bound exhausted.  NOP1 (2c)
\ stays type-blind: run it before any port reset or it counts a
\ PSCE as a completion.
VARIABLE XEV-SKIP  VARIABLE XEV-LAST  VARIABLE XEV-WANT
: EV-WAIT ( type -- flag )
    XEV-WANT !  0 XEV-SKIP !
    BEGIN EV-POLL
    WHILE
        EV-TYPE XEV-WANT @ = IF -1 EXIT THEN
        EV-TYPE XEV-LAST !  1 XEV-SKIP +!  EV-NEXT
        XEV-SKIP @ 14 < 0= IF 0 EXIT THEN
    REPEAT 0 ;
\ Context size: HCCPARAMS1 bit 2 CSZ (xHCI 1.2 section 5.3.6)
\ -> 40 (64-byte contexts) else 20.  Refuses unbound: 20 or
\ 40 would read as a plausible answer on a pre-bind card line.
\ QEMU: 20 by derivation (hcd-xhci.c HCCPARAMS = 00080000 or
\ 00080001, bit 2 clear).  Iron: unmeasured, pre-registered 40.
: CTX-SIZE ( -- n|0 )
    XHCI-BASE @ 0= IF 0 EXIT THEN
    HCC1 4 AND IF 40 ELSE 20 THEN ;

\ ---- Step 3b: slot commands / contexts / Address Device ----
\ Generic command TRB + Enable Slot / Address Device / Disable
\ Slot.  First rung that builds structures the CONTROLLER reads
\ back (contexts it dereferences), not just rings it consumes.
\ Command/completion codes are xHCI 1.2 Table 6-90/6-91 (QEMU
\ v8.2.2 confirms): Enable Slot 9, Disable Slot 10 (A),
\ Address Device 11 (B); Command Completion event 33 (21);
\ CC Success 1, TRB Error 5, Slot Not Enabled 11 (B), Parameter
\ Error 17 (11).  Slot states Default 1, Addressed 2.
\
\ CONTEXT SIZE is the load-bearing correctness bit and QEMU
\ cannot exercise it: QEMU reads the input context at hardcoded
\ +32/+64, i.e. always 32-byte stride, so a 32 hardcode passes
\ on QEMU and writes wrong offsets into DMA on a 64-byte part.
\ CTX-SZ caches CTX-SIZE (HCC1 CSZ) once; every offset word
\ scales with it, and the suite forces CTX-SZ = 64 to prove the
\ scaling the emulator can't (feedback_mask_blindness).
VARIABLE CTX-SZ
: CTX-CACHE ( -- ) CTX-SIZE CTX-SZ ! ;
: I-SLOT ( ictx -- a ) CTX-SZ @ + ;
: I-EP0  ( ictx -- a ) CTX-SZ @ 2 * + ;
: O-EP0  ( octx -- a ) CTX-SZ @ + ;

\ Slot structures: output device context, input context, EP0
\ transfer ring.  One page each from PHYS-ALLOC; SLOT-FREE
\ cross-checks each against the owner table (XREL1) before
\ release, like XHCI-DOWN.
VARIABLE XODC   VARIABLE XICTX  VARIABLE XEP0R
VARIABLE XEP0ENQ  VARIABLE XEP0CCS  VARIABLE XSLOT
VARIABLE CTX-MPS   \ 3b default EP0 max packet, read back by 3c

\ Generic command-ring producer.  16 TRBs; slot 15 is the link
\ TRB (type 6, Toggle Cycle), same wrap as TRB-NOP!.  The cycle
\ bit is written LAST (controller polls it to detect the TRB),
\ so params+status land before control|cycle.
VARIABLE CMA  VARIABLE CMCTL  VARIABLE CMCC  VARIABLE CMSLOT
: CMD-ENQ ( plo phi sts ctl -- )
    XCRING @ 0= IF 2DROP 2DROP EXIT THEN
    XCCS @ OR CMCTL !
    XCRING @ XENQ @ 10 * + CMA !
    CMA @ 8 + !
    CMA @ 4 + !
    CMA @ !
    CMCTL @ CMA @ C + !
    1 XENQ +!
    XENQ @ F = IF
        XCRING @ F0 + CMA !
        XCRING @ CMA @ !  0 CMA @ 4 + !  0 CMA @ 8 + !
        1802 XCCS @ OR CMA @ C + !
        0 XENQ !  XCCS @ 1 XOR XCCS ! THEN ;
\ CMD-RUN: enqueue, ring, await a Command Completion event (21),
\ read completion code + slot, consume it.  ( -- cc slot ); on a
\ poll timeout returns 0 0 (never a valid completion).
: CMD-RUN ( plo phi sts ctl -- cc slot )
    XCRING @ 0= IF 2DROP 2DROP 0 0 EXIT THEN
    CMD-ENQ DOORBELL0
    21 EV-WAIT IF
        EV-CC CMCC !  EV-SLOT CMSLOT !  EV-NEXT
    ELSE 0 CMCC !  0 CMSLOT ! THEN
    CMCC @ CMSLOT @ ;
: ENABLE-SLOT ( -- cc slot ) 0 0 0 2400 CMD-RUN ;
: DISABLE-SLOT ( slot -- cc )
    18 LSHIFT 2800 OR >R  0 0 0 R>  CMD-RUN DROP ;

\ EP0 max packet DEFAULT by port speed (xHCI 1.2 4.3, USB 2.0
\ 5.5.3): HS 64, SS 512, LS/FS 8.  Derived from P-SPEED (a
\ register read), NOT hardcoded; 3c reads the real
\ bMaxPacketSize0 via GET_DESCRIPTOR(8), corrects w/ Eval Ctx.
: SPEED>MPS ( speed -- mps )
    DUP 3 = IF DROP 40 EXIT THEN
    4 = IF 200 ELSE 8 THEN ;

\ Input context for Address Device (spec 6.2.5.1/6.2.2/6.2.3):
\ control: Drop=0, Add=3 (A0 slot + A1 EP0) -- QEMU rejects any
\ other with TRB Error.  slot dword0 = ctx-entries(1)<<27 |
\ speed<<20; dword1 = port#<<16.  EP0 dword1 = mps<<16 | type
\ Control(4)<<3 | CErr(3)<<1 = mps<<16|26; dword2 = ring|DCS;
\ dword4 = avg TRB length 8.
: BUILD-ICTX ( port# speed -- )
    XICTX @ 0= IF 2DROP EXIT THEN
    XICTX @ PG0
    3 XICTX @ 4 + !
    DUP SPEED>MPS DUP CTX-MPS !
    10 LSHIFT 26 OR XICTX @ I-EP0 4 + !
    14 LSHIFT 8000000 OR XICTX @ I-SLOT !
    10 LSHIFT XICTX @ I-SLOT 4 + !
    XEP0R @ 1 OR XICTX @ I-EP0 8 + !
    0 XICTX @ I-EP0 C + !
    8 XICTX @ I-EP0 10 + ! ;

: SLOT-ALLOC ( -- flag )
    1000 PHYS-ALLOC DUP XODC ! 0= IF 0 EXIT THEN
    1000 PHYS-ALLOC DUP XICTX ! 0= IF
        XODC @ 1000 PHYS-RELEASE 0 XODC ! 0 EXIT THEN
    1000 PHYS-ALLOC DUP XEP0R ! 0= IF
        XICTX @ 1000 PHYS-RELEASE 0 XICTX !
        XODC @ 1000 PHYS-RELEASE 0 XODC ! 0 EXIT THEN
    XODC @ PG0  XICTX @ PG0  XEP0R @ PG0
    0 XEP0ENQ !  1 XEP0CCS !  -1 ;
: SLOT-FREE ( -- )
    XEP0R @ 0<> IF XEP0R @ 1000 XREL1 0 XEP0R ! THEN
    XICTX @ 0<> IF XICTX @ 1000 XREL1 0 XICTX ! THEN
    XODC @ 0<> IF XODC @ 1000 XREL1 0 XODC ! THEN ;

\ Slot context state (output dword3 bits 31:27): 1 Default,
\ 2 Addressed.  Read from the OUTPUT device context the
\ controller wrote.
: SLOT-STATE ( -- n ) XODC @ C + @ 1B RSHIFT 1F AND ;

\ ENUM-ADDRESS: the 3b sequence for one occupied port.  Requires
\ a bound base and XHCI-UP done (DCBAA live).  Enable Slot ->
\ allocate + build input ctx -> program DCBAA[slot] = output ctx
\ -> Address Device.  Returns the slot on Addressed (both cc=1),
\ else tears down (Disable Slot if enabled + release) and 0.
: ENUM-ADDRESS ( port# -- slot|0|-3 )
    XHCI-BASE @ 0= IF DROP 0 EXIT THEN
    XDCBAA @ 0= IF DROP 0 EXIT THEN
    \ Port must be ENABLED (PED) to address: HCRST leaves ports
    \ disabled (2d), and speed read off a Polling port builds a
    \ speed-0 context that fails cc4 two layers down (3d iron).
    \ Refuse -3 (distinct from 0 / a valid slot); caller resets.
    DUP PORTSC@ P-PED 0= IF DROP -3 EXIT THEN
    CTX-CACHE
    SLOT-ALLOC 0= IF DROP 0 EXIT THEN
    ENABLE-SLOT
    SWAP 1 = 0= IF 2DROP SLOT-FREE 0 EXIT THEN
    DUP XSLOT !
    XODC @ XDCBAA @ XSLOT @ 8 * + !
    0 XDCBAA @ XSLOT @ 8 * + 4 + !
    DROP
    DUP PORTSC@ P-SPEED BUILD-ICTX
    XICTX @ 0 0 XSLOT @ 18 LSHIFT 2C00 OR CMD-RUN
    DROP
    1 = IF XSLOT @ ELSE
        XSLOT @ DISABLE-SLOT DROP SLOT-FREE 0 XSLOT ! 0 THEN ;

\ SLOT-DOWN: Disable Slot, clear the DCBAA entry, cross-checked
\ release.  -1 all released / 0 nothing held / 1 partial.
: SLOT-DOWN ( -- code )
    XSLOT @ 0= IF 0 EXIT THEN
    XSLOT @ DISABLE-SLOT DROP
    0 XDCBAA @ XSLOT @ 8 * + !
    0 XDCBAA @ XSLOT @ 8 * + 4 + !
    0 XDP !
    SLOT-FREE
    0 XSLOT !
    XDP @ IF 1 ELSE -1 THEN ;

\ ---- Step 3c: EP0 control transfers / configure ----
\ Three-stage control transfers on the EP0 ring (Setup type 2,
\ Data type 3, Status type 4; xHCI 1.2 6.4.1.2), each completed
\ by ONE Transfer Event (type 32): IOC is set only on the Status
\ stage, and QEMU's xhci_xfer_report resets shortpkt at the
\ Status stage before the IOC check, so a control read reports
\ CC Success (1), not Short Packet (13) -- verified in v8.2.2
\ source, not recalled.  GET_DESCRIPTOR reads the REAL
\ bMaxPacketSize0 (device desc byte 7) and corrects the EP0
\ context via Evaluate Context (type 13) when it differs from
\ the 3b speed-derived default; then bConfigurationValue (config
\ desc byte 5) drives SET_CONFIGURATION, proven by a
\ GET_CONFIGURATION readback taken BEFORE and AFTER.
\ Control TRB flags: Setup IDT 40 | type2 800 | TRT (IN 30000 /
\ none 0); Data type3 C00 | DIR-IN 10000; Status type4 1000 |
\ IOC 20 | DIR.  The Setup Stage TRB Transfer Length is 8 per
\ xHCI 1.2 section 6.4.1.2.1 (setup packet is always 8 bytes,
\ immediate data since IDT is set) -- a spec requirement, with
\ QEMU v8.2.2 xhci_fire_ctl_transfer as the version-pinned
\ cross-check (it refuses a setup TRB whose length is not 8).
VARIABLE XDBUF  VARIABLE CFGVAL  VARIABLE CFGCC8
VARIABLE EPA  VARIABLE EPCTL  VARIABLE GDBUF  VARIABLE GDLEN

\ EP0 transfer-ring producer (mirror of CMD-ENQ on XEP0R;
\ cycle written last, link TRB at slot 15).
: EP0-ENQ ( plo phi sts ctl -- )
    XEP0R @ 0= IF 2DROP 2DROP EXIT THEN
    XEP0CCS @ OR EPCTL !
    XEP0R @ XEP0ENQ @ 10 * + EPA !
    EPA @ 8 + !
    EPA @ 4 + !
    EPA @ !
    EPCTL @ EPA @ C + !
    1 XEP0ENQ +!
    XEP0ENQ @ F = IF
        XEP0R @ F0 + EPA !
        XEP0R @ EPA @ !  0 EPA @ 4 + !  0 EPA @ 8 + !
        1802 XEP0CCS @ OR EPA @ C + !
        0 XEP0ENQ !  XEP0CCS @ 1 XOR XEP0CCS ! THEN ;
\ EP0 doorbell: slot's doorbell = DB-BASE + slot*4, target
\ DCI 1 (the control endpoint).
: EP0-BELL ( -- ) 1 XSLOT @ 4 * DB-BASE + ! ;
\ GD-RESID (step 4, design 1.5): residual of the last EP0
\ transfer = Transfer Event status bits 23:0 (TRB length -
\ bytes transferred), recorded before the event is consumed.
\ A walker bounded by wTotalLength would parse stale page
\ bytes after a short read; ENUM-HID bounds EP-FIND by
\ wLength - GD-RESID instead.
VARIABLE GD-RESID
: EP0-WAIT ( -- cc )
    20 EV-WAIT IF EV-TRB 8 + @ FFFFFF AND GD-RESID !
        EV-CC EV-NEXT ELSE 0 THEN ;
\ Success on a control READ is 1 (Success) or D (Short Packet):
\ QEMU gives 1, but a controller that sets ISP semantics could
\ give D on a sub-MPS read -- accept both, no habitat reds.
: CC-OK? ( cc -- flag ) DUP 1 = SWAP D = OR ;

\ GET_DESCRIPTOR: bmRequestType 80, bRequest 6, wValue =
\ dtype<<8 | dindex, wLength = wlen, data IN to buf.
: GET-DESC ( dtype dindex wlen buf -- cc )
    XEP0R @ 0= IF 2DROP 2DROP 0 EXIT THEN
    GDBUF !  GDLEN !
    SWAP 8 LSHIFT OR 10 LSHIFT 680 OR   \ d0=wValue<<16|0680
    GDLEN @ 10 LSHIFT                     \ d1 = wLen<<16
    8 30840 EP0-ENQ                       \ setup (IN data)
    GDBUF @ 0 GDLEN @ 10C00 EP0-ENQ       \ data IN
    0 0 0 1020 EP0-ENQ                    \ status OUT, IOC
    EP0-BELL EP0-WAIT ;

\ Evaluate Context to correct EP0 max packet: input control
\ Add = A1 only (2), EP0 ctx with the new MPS.  QEMU
\ xhci_evaluate_slot updates output ep0 ctx; real-controller
\ acceptance is an iron finding.
: EVAL-MPS ( mps -- cc )
    XICTX @ 0= IF DROP 0 EXIT THEN
    XICTX @ PG0
    2 XICTX @ 4 + !
    10 LSHIFT 26 OR XICTX @ I-EP0 4 + !
    XEP0R @ 1 OR XICTX @ I-EP0 8 + !
    0 XICTX @ I-EP0 C + !
    8 XICTX @ I-EP0 10 + !
    XICTX @ 0 0 XSLOT @ 18 LSHIFT 3400 OR CMD-RUN DROP ;

\ SET_CONFIGURATION (OUT no-data): status stage is IN, CC 1.
: SET-CONFIG ( value -- cc )
    XEP0R @ 0= IF DROP 0 EXIT THEN
    10 LSHIFT 900 OR                   \ d0=value<<16|0900
    0 8 840 EP0-ENQ                      \ setup, len 8 per spec
    0 0 0 11020 EP0-ENQ                   \ status IN, IOC
    EP0-BELL EP0-WAIT ;
\ GET_CONFIGURATION (IN 1 byte): current config value -> buf.
: GET-CONFIG ( buf -- cc )
    XEP0R @ 0= IF DROP 0 EXIT THEN
    880 10000 8 30840 EP0-ENQ          \ setup d0=880 d1=1<<16
    0 1 10C00 EP0-ENQ                   \ data IN 1 byte (buf)
    0 0 0 1020 EP0-ENQ                    \ status OUT, IOC
    EP0-BELL EP0-WAIT ;

\ ENUM-CONFIGURE: after ENUM-ADDRESS.  Read the real MPS,
\ correct via Evaluate Context if it differs from the 3b
\ default (CTX-MPS, set in BUILD-ICTX), read the config value,
\ set it.  Returns bConfigurationValue on the SET succeeding
\ (cc 1), else 0.  CFGCC8 keeps the GET_DESCRIPTOR(8) code.
: ENUM-CONFIGURE ( -- cc )
    XHCI-BASE @ 0= IF 0 EXIT THEN
    XSLOT @ 0= IF 0 EXIT THEN
    1000 PHYS-ALLOC DUP XDBUF ! 0= IF 0 EXIT THEN
    XDBUF @ PG0
    1 0 8 XDBUF @ GET-DESC CFGCC8 !
    XDBUF @ 7 + C@                       \ real bMaxPacketSize0
    DUP CTX-MPS @ = 0= IF EVAL-MPS DROP ELSE DROP THEN
    1 0 12 XDBUF @ GET-DESC DROP         \ full device desc 18
    2 0 9 XDBUF @ GET-DESC DROP            \ config desc (9)
    XDBUF @ 5 + C@ CFGVAL !                \ bConfigurationValue
    CFGVAL @ SET-CONFIG
    XDBUF @ 1000 PHYS-RELEASE 0 XDBUF !
    DUP 1 = IF DROP CFGVAL @ ELSE DROP 0 THEN ;

\ CFG-STATE: current configured value via GET_CONFIGURATION
\ (0 before SET, bConfigurationValue after).  Own scratch page.
: CFG-STATE ( -- n|-1 )
    XSLOT @ 0= IF -1 EXIT THEN
    1000 PHYS-ALLOC DUP 0= IF DROP -1 EXIT THEN
    XDBUF !
    XDBUF @ GET-CONFIG CC-OK? IF XDBUF @ C@ ELSE -1 THEN
    XDBUF @ 1000 PHYS-RELEASE  0 XDBUF ! ;

\ ---- Step 4: Configure Endpoint + HID interrupt-IN ----
\ Design: docs/xhci-step4-design-2026-09-14.md (private), rev 2
\ + rulings.  xHCI 1.2 4.6.6 / 6.2.5.1 (Configure Endpoint,
\ input control Drop=0, Add=A0|A(dci): A1 CLEAR, EP0 is not
\ reconfigured), 6.2.3 (endpoint ctx: Interrupt IN type 7,
\ CErr 3, MPS, interval, TR dequeue|DCS, avg TRB len / ESIT),
\ 6.2.3.6 (FS/LS interval = 3+log2(bInterval), HS = bInt-1),
\ 4.5.1 (DCI = 2*EP + dir), 6.4.1.1 (Normal TRB type 1 with
\ IOC|ISP = 424), 4.6.9 (Stop Endpoint type 15 = 3C00).  USB
\ 2.0 9.6 descriptor walk; HID 1.11 7.2.6 SET_PROTOCOL.  QEMU
\ v8.2.2 hcd-xhci.h enums read 2026-09-15 as the version-
\ pinned cross-check: CR_CONFIGURE_ENDPOINT 12, CR_STOP_
\ ENDPOINT 15, TR_NORMAL 1, CC 5/12/19; EP_STOPPED 3.
VARIABLE HID-EPADDR  VARIABLE HID-MPS  VARIABLE HID-BINT
VARIABLE HID-DCI  VARIABLE HID-IFACE  VARIABLE HIDCC-PROT
VARIABLE XEP1R  VARIABLE XEP1ENQ  VARIABLE XEP1CCS
VARIABLE HIDBUF  VARIABLE HID-PEND  VARIABLE HTL
VARIABLE E1A  VARIABLE E1CTL
VARIABLE EFP  VARIABLE EFL  VARIABLE EFO  VARIABLE EFB

: EP-DCI ( bEndpointAddress -- dci )
    DUP F AND 2 * SWAP 7 RSHIFT + ;
\ FS/LS interrupt: Interval = 3 + floor(log2 bInterval), 3..A.
: INTERVAL-FS ( bInterval -- field )
    3 SWAP
    BEGIN 1 RSHIFT DUP 0<> WHILE SWAP 1+ SWAP REPEAT DROP
    DUP A > IF DROP A THEN ;
: INTERVAL-HS ( bInterval -- field )
    1- DUP 0< IF DROP 0 THEN ;
\ Context addressing, CTX-SZ-scaled like I-EP0/O-EP0 (3b):
\ input ctx: slot at 1x, EP0 at 2x, DCI n at (n+1)x;
\ output ctx: slot at 0, DCI n at n x.
: I-EPN ( ictx dci -- a ) 1+ CTX-SZ @ * + ;
: O-EPN ( octx dci -- a ) CTX-SZ @ * + ;

\ Descriptor walker.  EF@ reads byte i of the descriptor at the
\ current offset.  Refuses (0) on bLength 0 BEFORE advancing
\ (rev 2 defect 2), and never reads past len = bytes received
\ (rev 2 defect 3).  Captures bInterfaceNumber of the most
\ recent interface descriptor into HID-IFACE (rev 2 defect 5).
: EF@ ( i -- byte ) EFO @ + EFP @ + C@ ;
: EP-INT-IN? ( -- flag )
    3 EF@ 3 AND 3 =  2 EF@ 80 AND 0<>  AND ;
: EP-FIND ( buf len -- off|0 )
    EFL !  EFP !  0 EFO !  0 HID-IFACE !
    BEGIN
        EFO @ 2 + EFL @ > IF 0 EXIT THEN
        0 EF@ EFB !  EFB @ 0= IF 0 EXIT THEN
        EFO @ EFB @ + EFL @ > IF 0 EXIT THEN
        1 EF@ 4 = IF 2 EF@ HID-IFACE ! THEN
        1 EF@ 5 = IF EP-INT-IN? IF EFO @ EXIT THEN THEN
        EFB @ EFO +!
    AGAIN ;

\ Input context for Configure Endpoint from the HID-* cells and
\ the OUTPUT slot context (route/speed/port copied; entries=3).
\ Speed (slot dword0 bits 23:20): 1 FS / 2 LS -> INTERVAL-FS,
\ 3 HS / 4 SS -> INTERVAL-HS.  Stack-neutral (check 29).
: BUILD-EPCTX ( -- )
    XICTX @ 0= IF EXIT THEN
    XICTX @ PG0
    0 XICTX @ !
    1 HID-DCI @ LSHIFT 1 OR XICTX @ 4 + !
    XODC @ @ 7FFFFFF AND 18000000 OR XICTX @ I-SLOT !
    XODC @ 4 + @ XICTX @ I-SLOT 4 + !
    XODC @ 8 + @ XICTX @ I-SLOT 8 + !
    XODC @ @ 14 RSHIFT F AND 3 <
    IF HID-BINT @ INTERVAL-FS ELSE HID-BINT @ INTERVAL-HS THEN
    10 LSHIFT XICTX @ HID-DCI @ I-EPN !
    HID-MPS @ 10 LSHIFT 3E OR XICTX @ HID-DCI @ I-EPN 4 + !
    XEP1R @ 1 OR XICTX @ HID-DCI @ I-EPN 8 + !
    0 XICTX @ HID-DCI @ I-EPN C + !
    HID-MPS @ 10 LSHIFT 8 OR XICTX @ HID-DCI @ I-EPN 10 + ! ;

: CONFIGURE-EP ( -- cc )
    XICTX @ 0= IF 0 EXIT THEN
    XICTX @ 0 0 XSLOT @ 18 LSHIFT 3000 OR CMD-RUN DROP ;
: STOP-EP ( dci -- cc )
    XSLOT @ 0= IF DROP 0 EXIT THEN
    10 LSHIFT 3C00 OR XSLOT @ 18 LSHIFT OR >R
    0 0 0 R> CMD-RUN DROP ;
: EP-BELL ( dci -- ) XSLOT @ 4 * DB-BASE + ! ;

\ EP1 transfer-ring producer (mirror of EP0-ENQ on XEP1R).
: EP1-ENQ ( plo phi sts ctl -- )
    XEP1R @ 0= IF 2DROP 2DROP EXIT THEN
    XEP1CCS @ OR E1CTL !
    XEP1R @ XEP1ENQ @ 10 * + E1A !
    E1A @ 8 + !
    E1A @ 4 + !
    E1A @ !
    E1CTL @ E1A @ C + !
    1 XEP1ENQ +!
    XEP1ENQ @ F = IF
        XEP1R @ F0 + E1A !
        XEP1R @ E1A @ !  0 E1A @ 4 + !  0 E1A @ 8 + !
        1802 XEP1CCS @ OR E1A @ C + !
        0 XEP1ENQ !  XEP1CCS @ 1 XOR XEP1CCS ! THEN ;

\ HID-POLL: one Normal TRB (IOC|ISP) at HIDBUF if none pending,
\ then wait one Transfer Event.  Returns the event's cc
\ UNCHANGED, or 0 on timeout with the TRB LEFT PENDING (ruling
\ 2026-09-14); refuses 0 with no enqueue on no slot / no ring.
: HID-POLL ( -- cc )
    XSLOT @ 0= IF 0 EXIT THEN
    XEP1R @ 0= IF 0 EXIT THEN
    HID-PEND @ 0= IF
        HIDBUF @ 0 8 424 EP1-ENQ
        HID-DCI @ EP-BELL  -1 HID-PEND ! THEN
    20 EV-WAIT IF EV-CC 0 HID-PEND ! EV-NEXT ELSE 0 THEN ;

\ SET_PROTOCOL (HID 1.11 7.2.6): bmRequestType 21, bRequest 0B,
\ wValue = proto, wIndex = HID-IFACE, no data; SET-CONFIG shape.
: SET-PROTOCOL ( proto -- cc )
    XEP0R @ 0= IF DROP 0 EXIT THEN
    10 LSHIFT B21 OR  HID-IFACE @
    8 840 EP0-ENQ
    0 0 0 11020 EP0-ENQ
    EP0-BELL EP0-WAIT ;

\ Release whatever the HID leg holds (used on every ENUM-HID
\ failure path and by HID-DOWN); XDBUF is the config scratch.
: HID-REL ( -- )
    HIDBUF @ 0<> IF HIDBUF @ 1000 XREL1 0 HIDBUF ! THEN
    XEP1R @ 0<> IF XEP1R @ 1000 XREL1 0 XEP1R ! THEN
    XDBUF @ 0<> IF XDBUF @ 1000 PHYS-RELEASE 0 XDBUF ! THEN ;

\ ENUM-HID: after ENUM-CONFIGURE.  Full config descriptor ->
\ EP-FIND (bounded by bytes received) -> HID-* cells -> ring +
\ buffer pages -> BUILD-EPCTX -> Configure Endpoint cc 1 ->
\ SET_PROTOCOL recorded (HIDCC-PROT, not gated) -> -1.  Refuses
\ 0 on unbound / no slot / already configured (XEP1R live) /
\ no interrupt-IN endpoint / cc <> 1, releasing what it took.
: ENUM-HID ( -- flag )
    XHCI-BASE @ 0= IF 0 EXIT THEN
    XSLOT @ 0= IF 0 EXIT THEN
    XEP1R @ 0<> IF 0 EXIT THEN
    1000 PHYS-ALLOC DUP XDBUF ! 0= IF 0 EXIT THEN
    XDBUF @ PG0
    2 0 9 XDBUF @ GET-DESC DROP
    XDBUF @ 2 + C@ XDBUF @ 3 + C@ 8 LSHIFT OR
    DUP 1000 > IF DROP 1000 THEN HTL !
    2 0 HTL @ XDBUF @ GET-DESC CC-OK? 0= IF HID-REL 0 EXIT THEN
    HTL @ GD-RESID @ -  DUP 0< IF DROP 0 THEN
    XDBUF @ SWAP EP-FIND DUP 0= IF DROP HID-REL 0 EXIT THEN
    XDBUF @ +
    DUP 2 + C@ HID-EPADDR !
    DUP 4 + C@ OVER 5 + C@ 8 LSHIFT OR 7FF AND HID-MPS !
    6 + C@ HID-BINT !
    HID-EPADDR @ EP-DCI HID-DCI !
    1000 PHYS-ALLOC DUP XEP1R ! 0= IF HID-REL 0 EXIT THEN
    XEP1R @ PG0  0 XEP1ENQ !  1 XEP1CCS !
    1000 PHYS-ALLOC DUP HIDBUF ! 0= IF HID-REL 0 EXIT THEN
    HIDBUF @ PG0
    BUILD-EPCTX
    CONFIGURE-EP 1 = 0= IF HID-REL 0 EXIT THEN
    0 SET-PROTOCOL HIDCC-PROT !
    XDBUF @ 1000 PHYS-RELEASE 0 XDBUF !
    0 HID-PEND !  -1 ;

\ HID-DOWN: Stop Endpoint on HID-DCI (retires a pending TRB with
\ its ring, 4.6.9), release ring + buffer, reset the cells.
\ -1 all released / 0 nothing held / 1 partial.  SLOT-DOWN is
\ separate (card: HID-DOWN then SLOT-DOWN on separate lines).
: HID-DOWN ( -- code )
    XEP1R @ 0= HIDBUF @ 0= AND IF 0 EXIT THEN
    HID-DCI @ 0<> XSLOT @ 0<> AND IF HID-DCI @ STOP-EP DROP THEN
    0 XDP !
    HID-REL
    0 HID-PEND !  0 HID-DCI !  0 XEP1ENQ !  1 XEP1CCS !
    XDP @ IF 1 ELSE -1 THEN ;

." XHCI vocab loaded" CR

ONLY FORTH DEFINITIONS
DECIMAL
