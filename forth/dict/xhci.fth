\ ============================================
\ CATALOG: XHCI
\ CATEGORY: usb
\ PLATFORM: x86
\ SOURCE: hand-written
\ REQUIRES: PCI-ENUM ( PCI-READ FIND-XHCI )
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

." XHCI vocab loaded" CR

ONLY FORTH DEFINITIONS
DECIMAL
