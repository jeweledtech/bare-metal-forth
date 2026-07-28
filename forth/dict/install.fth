\ ============================================
\ CATALOG: INSTALL
\ CATEGORY: system
\ PLATFORM: x86
\ SOURCE: hand-written
\ REQUIRES: SURVEYOR
\ CONFIDENCE: high
\ ============================================
\
\ Piece 1 of the staged-dictionary installer:
\ the write guard.
\
\ The guarantee is an ALLOWLIST, not a
\ denylist. SAFE-WRITE permits exactly one
\ region -- the extent ForthOS owns -- and
\ refuses everything else, including every
\ sector it has never heard of. A denylist
\ would have to enumerate what to avoid, so
\ it would permit any partition the survey
\ failed to see. Fail-closed is the whole
\ point of the file.
\
\ This vocabulary is public so the allowlist
\ is auditable. The hardware write it calls
\ through is not part of the allowlist and
\ is not shipped here.
\
\ There is deliberately NO absolute-LBA write
\ primitive nameable in this vocabulary. The
\ only route to the disk is SEC-WRITE-VEC,
\ which starts unbound (0) and refuses. On
\ the free tier nothing binds it, so the
\ installer refuses by construction, not by
\ policy.
\
\ Full tier, after AHCI-INIT:
\   ALSO AHCI  USING INSTALL
\   BIND-WRITER AHCI-WRITE
\   INSTALL-STATUS
\
\ Usage:
\   2048 OWN-BASE !  65536 OWN-LEN !
\   IO-BUF 2048 SAFE-WRITE
\ ============================================

VOCABULARY INSTALL
INSTALL DEFINITIONS
ALSO SURVEYOR
DECIMAL

\ ---- The owned extent ----
\ Both default 0, so OWN-EXTENT? answers
\ false for every LBA until an extent has
\ been declared. An unconfigured installer
\ must not be a permissive one.
VARIABLE OWN-BASE
VARIABLE OWN-LEN

\ ---- The one route to the disk ----
\ 0 = unbound = refuse. Contract of the
\ bound xt:  ( lba count buf -- flag )
\ where a NONZERO flag means the write
\ failed. SAFE-WRITE checks it; a write
\ that reports failure is not allowed to
\ pass for a write that happened.
VARIABLE SEC-WRITE-VEC

CREATE IO-BUF 512 ALLOT

\ This kernel has no U< -- every compare is
\ signed -- so an LBA with bit 31 set reads
\ as negative. That is load-bearing here,
\ not a wart: such an LBA makes the offset
\ below negative and is refused, rather than
\ wrapping into the extent.
: OWN-EXTENT? ( lba -- flag )
    OWN-BASE @ -
    DUP 0< IF DROP 0 EXIT THEN
    OWN-LEN @ <
;

: SAFE-WRITE ( buf lba -- )
    DUP OWN-EXTENT? 0=
    ABORT" INSTALL: refuse, outside extent"
    SEC-WRITE-VEC @ 0=
    ABORT" INSTALL: refuse, no writer bound"
    SWAP 1 SWAP                 \ lba 1 buf
    SEC-WRITE-VEC @ EXECUTE     \ flag
    ABORT" INSTALL: write failed"
;

: WRITER! ( xt -- ) SEC-WRITE-VEC ! ;

\ Guarded bind: parses a name, binds it only
\ if the name resolves in the current search
\ order. Not finding it is not an error --
\ that is the free tier, and the vector
\ simply stays unbound.
: BIND-WRITER ( "name" -- )
    WORD FIND NIP
    DUP IF WRITER! ELSE DROP THEN
;

: INSTALL-STATUS ( -- )
    ." extent base " OWN-BASE @ .
    ." len " OWN-LEN @ . CR
    ." writer "
    SEC-WRITE-VEC @
    IF ." bound" ELSE ." UNBOUND (refuses)" THEN
    CR
;

\ ---- Reader vector ----
\ Contract of the bound xt:
\   ( lba count -- flag )
\ where flag 0 = success, nonzero = error.
\ The reader fills a buffer; its address is
\ stored in RD-BUF-ADDR.
\ 0 = unbound = FREE-EXTENT refuses.
VARIABLE SEC-READ-VEC
VARIABLE RD-BUF-ADDR

: BIND-READER ( "name" -- )
    WORD FIND NIP
    DUP IF SEC-READ-VEC ! ELSE DROP THEN
;

\ ---- FREE-EXTENT ----
\ Find a gap in the partition map, verify
\ it is empty, and claim it as OWN-EXTENT.
\
\ Consumes the survey contract: PART-ENT,
\ PART-END, PART-BAD?, MAP-TRUSTED?,
\ LBA-HORIZON, PART-N. PARTITION-MAP must
\ have been called first.
\
\ The reader must be bound and RD-BUF-ADDR
\ set before calling:
\   ' AHCI-READ SEC-READ-VEC !
\   SEC-BUF RD-BUF-ADDR !

VARIABLE FE-CAND
VARIABLE FE-NEED
VARIABLE FE-ADV
VARIABLE FE-PS
VARIABLE FE-PE

\ After GPT header + 32 entry sectors
34 CONSTANT MIN-LBA

\ Check one partition for overlap with
\ [FE-CAND, FE-CAND+FE-NEED). If overlap,
\ advance FE-CAND past the partition end.
: FE-CHK1 ( idx -- )
    DUP PART-BAD? IF DROP EXIT THEN
    DUP PART-ENT @ FE-PS !
    PART-END FE-PE !
    \ cand+need <= p-start means before
    FE-CAND @ FE-NEED @ +
    FE-PS @ <= IF EXIT THEN
    \ cand > p-end means after
    FE-CAND @ FE-PE @ > IF EXIT THEN
    \ overlap: advance past this partition
    FE-PE @ 1+ FE-CAND !
    -1 FE-ADV !
;

\ Find the first gap >= FE-NEED sectors.
\ Sets FE-CAND on success.
: FE-FIND ( -- flag )
    MIN-LBA FE-CAND !
    BEGIN
        \ Candidate wrapped past horizon?
        FE-CAND @ 0< IF 0 EXIT THEN
        \ Room before horizon?
        LBA-HORIZON FE-NEED @ -
        FE-CAND @ < IF 0 EXIT THEN
        \ Scan all partitions for overlap
        0 FE-ADV !
        PART-N @ 0= 0= IF
            PART-N @ 0 DO
                I FE-CHK1
            LOOP
        THEN
        FE-ADV @
    0= UNTIL
    -1
;

\ Check if the reader buffer is all zero.
: SECTOR-ZERO? ( -- flag )
    RD-BUF-ADDR @ 512 +
    RD-BUF-ADDR @ DO
        I @ IF 0 UNLOOP EXIT THEN
    4 +LOOP
    -1
;

\ Read back every sector of the candidate
\ extent and verify all are zero. This is
\ the placement check that holds when the
\ survey is wrong.
: FE-VERIFY ( -- flag )
    SEC-READ-VEC @ 0= IF 0 EXIT THEN
    RD-BUF-ADDR @ 0= IF 0 EXIT THEN
    FE-CAND @ FE-NEED @ + FE-CAND @ DO
        I 1 SEC-READ-VEC @ EXECUTE IF
            0 UNLOOP EXIT
        THEN
        SECTOR-ZERO? 0= IF
            0 UNLOOP EXIT
        THEN
    LOOP
    -1
;

\ FREE-EXTENT: find and claim free space.
\ Returns nonzero on success. On success,
\ OWN-BASE and OWN-LEN are set, arming
\ SAFE-WRITE for the claimed region.
: FREE-EXTENT ( sectors -- flag )
    DUP 1 < IF DROP 0 EXIT THEN
    FE-NEED !
    MAP-TRUSTED? 0= IF 0 EXIT THEN
    FE-FIND 0= IF 0 EXIT THEN
    FE-VERIFY 0= IF 0 EXIT THEN
    FE-CAND @ OWN-BASE !
    FE-NEED @ OWN-LEN !
    -1
;

\ Binds if AHCI is already in the search
\ order; silently does not if it is not.
BIND-WRITER AHCI-WRITE
BIND-READER AHCI-READ

ONLY FORTH DEFINITIONS
DECIMAL
