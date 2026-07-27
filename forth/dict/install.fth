\ ============================================
\ CATALOG: INSTALL
\ CATEGORY: system
\ PLATFORM: x86
\ SOURCE: hand-written
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

\ Binds if AHCI is already in the search
\ order; silently does not if it is not.
BIND-WRITER AHCI-WRITE

ONLY FORTH DEFINITIONS
DECIMAL
