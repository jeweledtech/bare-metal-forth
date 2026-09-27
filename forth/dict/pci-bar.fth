\ ============================================
\ CATALOG: PCI-BAR
\ CATEGORY: pci
\ PLATFORM: x86
\ SOURCE: hand-written
\ REQUIRES: PCI-ENUM ( PCI-READ PCI-COUNT PCI-ENTRY
\   .H2 >HEXCH )
\ CONFIDENCE: high
\ ============================================
\ Shared PCI words that nothing calls at boot, so
\ block-loaded, never embedded (ruling 2026-09-07;
\ placement ruled 2026-09-27 for (bz)).  Callers:
\ XHCI (PCI-BAR64@) and translated driver vocabs
\ (PCI-CLASS-COUNT/-NTH/-LIST, PCI-BAR64@).
\ Every word here only READS config space.
\
\ Moved verbatim from xhci.fth ((bz), 2026-09-27):
\ Step 2a: 64-bit-safe BAR read (correctness word).
\ Iron reading 2026-09-05 (HP 15-bs0xx): BAR0=B1210004,
\ type bits 2:1 = 10 (64-bit BAR), upper dword (config
\ offset 14) = 0. Ruling: refuse the device if the upper
\ dword is nonzero; this word is NOT an enabler for >4GB
\ MMIO (reading 3 ruled out). ECAM deferred.

VOCABULARY PCI-BAR
PCI-BAR DEFINITIONS
ALSO PCI-ENUM
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


\ ---- Instances of a class, in scan order ----
\ (bz).  A match is PCI-FIND-CLASS's: the table's
\ +8/+9 bytes pre-filter, one live 8 PCI-READ
\ decides.  Nothing is chosen implicitly: the
\ caller names an instance by its index, so
\ class sub 0 PCI-CLASS-NTH = class sub
\ PCI-FIND-CLASS on every machine.
VARIABLE PC-C  VARIABLE PC-S  VARIABLE PC-N
: ENTRY-BDF ( entry -- b d f )
    DUP C@ OVER 1+ C@ ROT 2 + C@ ;
: CLASS-HIT? ( n -- flag )
    PCI-ENTRY DUP 8 + C@ PC-C @ =
    OVER 9 + C@ PC-S @ = AND 0= IF
        DROP 0 EXIT THEN
    ENTRY-BDF 8 PCI-READ
    DUP 18 RSHIFT FF AND PC-C @ =
    SWAP 10 RSHIFT FF AND PC-S @ = AND ;
: PCI-CLASS-COUNT ( class sub -- n )
    PC-S ! PC-C !  0
    PCI-COUNT @ DUP 0<> IF
        0 DO I CLASS-HIT? IF 1+ THEN LOOP
    ELSE DROP THEN ;
\ i < 0 or i >= count refuses ( -- 0 ).
: PCI-CLASS-NTH ( class sub i -- b d f -1 | 0 )
    PC-N ! PC-S ! PC-C !
    PCI-COUNT @ DUP 0<> IF
        0 DO I CLASS-HIT? IF
            PC-N @ 0= IF
                I PCI-ENTRY ENTRY-BDF
                -1 UNLOOP EXIT THEN
            -1 PC-N +!
        THEN LOOP
    ELSE DROP THEN 0 ;
\ One line per match: i bb:dd.f  (i printed by .)
: .BDF ( b d f -- )
    ROT .H2 ." :" SWAP .H2 ." ." >HEXCH EMIT ;
: PCI-CLASS-LIST ( class sub -- )
    PC-S ! PC-C !  0
    PCI-COUNT @ DUP 0<> IF
        0 DO I CLASS-HIT? IF
            CR DUP . I PCI-ENTRY ENTRY-BDF .BDF
            1+ THEN LOOP
    ELSE DROP THEN DROP ;

." PCI-BAR vocab loaded" CR

ONLY FORTH DEFINITIONS
DECIMAL
