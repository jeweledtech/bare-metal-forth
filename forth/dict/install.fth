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

\ ============================================
\ GPT-CRC32 (reflected, poly EDB88320)
\ ============================================
\ Tableless. Deliberately a second
\ implementation, not a collision: FILE-STREAM
\ carries a table-driven CRC32, but that
\ vocabulary is paid and this file is public,
\ so it cannot be called from here. The two
\ agree on the polynomial and the inner step,
\ which cross-validates both.
\
\ Gated against the standard vector
\ "123456789" -> CBF43926 before it is ever
\ pointed at a GPT. That vector drives the
\ register through high-bit-set states, so it
\ is exactly the test that catches a
\ sign-extending shift. RSHIFT here is `shr`
\ (forth.asm:909), verified at runtime, so no
\ post-shift mask is needed.
\
\ A wrong CRC at LBA 1 makes firmware fall
\ back to the backup header silently. The
\ machine still boots, so a naive "did it come
\ up" check passes a corrupt primary GPT.

HEX
EDB88320 CONSTANT GCRC-POLY
FFFFFFFF CONSTANT GCRC-ONES
DECIMAL

VARIABLE GCRC-ACC

\ The accumulator lives in a VARIABLE, not on
\ the return stack: >R / R> inline inside a
\ DO body corrupts I and J.
: GCRC-BIT ( -- )
    GCRC-ACC @ DUP 1 AND
    IF   1 RSHIFT GCRC-POLY XOR
    ELSE 1 RSHIFT
    THEN GCRC-ACC ! ;

\ 8 is a nonzero literal, so no phantom-loop
\ guard is needed here.
: GCRC-BYTE ( c -- )
    GCRC-ACC @ XOR GCRC-ACC !
    8 0 DO GCRC-BIT LOOP ;

\ Streaming interface: hash data across
\ multiple reads without a 16 KB buffer.
\ GPT-CRC32 is redefined as their wrapper
\ so the existing KAT transitively covers
\ all three primitives.
: CRC-BEGIN ( -- )
    GCRC-ONES GCRC-ACC ! ;
\ len 0 must be guarded: 0 0 DO runs the
\ body once under this kernel.
: CRC-CHUNK ( addr len -- )
    DUP 0> IF
        OVER + SWAP DO I C@ GCRC-BYTE LOOP
    ELSE 2DROP THEN ;
: CRC-END ( -- crc )
    GCRC-ACC @ GCRC-ONES XOR ;
: GPT-CRC32 ( addr len -- crc )
    CRC-BEGIN CRC-CHUNK CRC-END ;

\ ============================================
\ GPT entry array: free-slot selection
\ ============================================
\ 128 entries x 128 bytes = 32 sectors at
\ LBA 2..33. Slot N lives in sector 2 + N/4
\ at byte offset (N mod 4) * 128.
\
\ Shift and mask rather than / and MOD: both
\ are exact for powers of two and neither
\ raises a signed-division question.
\
\ This scans the raw entry array on disk and
\ deliberately does NOT consult the survey.
\ PART-TBL compacts entries as it collects
\ them -- SCAN-GPT-SEC drops the within-sector
\ index and TAKE-ENTRY stores at a running
\ PART-N -- so a physical slot number cannot
\ be recovered from it. A survey built to
\ answer "what partitions exist" cannot answer
\ "which slot is free", because for that
\ question the gaps are the payload.

128 CONSTANT GPT-ENT-SIZE
128 CONSTANT GPT-ENT-MAX
2 CONSTANT GPT-ARR-LBA
32 CONSTANT GPT-ARR-SECS

: SLOT-LBA ( n -- lba ) 2 RSHIFT GPT-ARR-LBA + ;
: SLOT-OFF ( n -- off ) 3 AND GPT-ENT-SIZE * ;

VARIABLE FS-SLOT

\ Free iff all 128 bytes are zero. Stricter
\ than the survey's test, which reads only the
\ first 8 bytes of the type GUID. The
\ asymmetry is deliberate: the survey is
\ deciding what to display, this is deciding
\ what to overwrite. Any nonzero byte -- a
\ stale name, a unique GUID left behind by a
\ tool that cleared only the type -- means
\ something else has a claim, so we refuse it.
\ GPT requires a nonzero PartitionTypeGUID for
\ any used entry, so all-zero is host-safe.
: SLOT-FREE? ( n -- flag )
    SLOT-OFF RD-BUF-ADDR @ +
    DUP GPT-ENT-SIZE + SWAP DO
        I @ IF 0 UNLOOP EXIT THEN
    4 +LOOP
    -1 ;

\ Sets FS-SLOT and returns nonzero on success,
\ matching FREE-EXTENT's shape. Reads once per
\ four slots -- 32 reads, not 128 -- and stays
\ a single DO loop so one UNLOOP is always the
\ right number on the early exits.
: FREE-SLOT ( -- flag )
    SEC-READ-VEC @ 0= IF 0 EXIT THEN
    RD-BUF-ADDR @ 0= IF 0 EXIT THEN
    GPT-ENT-MAX 0 DO
        I 3 AND 0= IF
            I SLOT-LBA 1
            SEC-READ-VEC @ EXECUTE IF
                0 UNLOOP EXIT
            THEN
        THEN
        I SLOT-FREE? IF
            I FS-SLOT ! -1 UNLOOP EXIT
        THEN
    LOOP
    0 ;

\ ============================================
\ The GPT metadata permit
\ ============================================
\ ADD-PARTITION is the one sanctioned write
\ outside OWN-EXTENT, so it cannot go through
\ SAFE-WRITE. It gets its own permit, and the
\ two are deliberately DISJOINT: GPT-WRITE can
\ reach only the metadata sectors, SAFE-WRITE
\ only OWN-EXTENT. Each is a small claim that
\ can be audited on its own. A single widened
\ predicate would destroy both at once -- every
\ ordinary data write would then carry standing
\ permission to corrupt the partition table.
\
\ The permit is an explicit set of exactly four
\ LBAs, compared for equality, not a range:
\   GW-HDR   LBA 1, the primary header
\   GW-ENT   the ONE primary entry sector our
\            slot lives in
\   GW-BENT  that sector's backup mirror
\   GW-BHDR  the backup header
\
\ LBA 0 -- the protective MBR -- is absent from
\ the set, so it is unreachable by
\ construction. There is deliberately no
\ "refuse LBA 0" line: a check can be deleted,
\ a value that was never in the set cannot.
\
\ Only the one changed entry sector is ever
\ written, never all 32. That is both the
\ minimal permit and what the byte-identical
\ gate wants: the host's other 31 entry sectors
\ are untouched, so they are trivially
\ unchanged. Recomputing the header CRC still
\ reads all 32 -- reads are not gated.
\
\ Everything is computed at CLAIM time, not per
\ write. The backup header sits at the disk's
\ last LBA, which is exactly where the horizon
\ must bite; deciding it here means "backup past
\ horizon" refuses once, before anything is
\ written. Deferred to write time it would fire
\ mid-sequence, leaving a mutated primary GPT
\ with a mirror that cannot be reached to match
\ it. Do not write a primary you cannot mirror.

VARIABLE GW-ARMED
VARIABLE GW-HDR
VARIABLE GW-ENT
VARIABLE GW-BENT
VARIABLE GW-BHDR

\ "EFI PART" as two little-endian cells.
HEX
20494645 CONSTANT GPT-SIG-LO
54524150 CONSTANT GPT-SIG-HI
DECIMAL

\ AlternateLBA -- the backup header's LBA -- is
\ 8 bytes at +0x20. NOT +0x28: that is
\ FirstUsableLBA, and reading it here would
\ either refuse on a tight GPT (34-32 < 34) or,
\ worse, arm on an aligned one with GW-BHDR and
\ GW-BENT pointing into the first partition's
\ live data. Offsets verified against a real
\ sgdisk-authored header, not from memory.
\ The high cell must be zero and the low cell
\ must clear bit 31, or the backup lies past
\ the horizon and this kernel cannot compare
\ it.
32 CONSTANT GPT-ALT-LO
36 CONSTANT GPT-ALT-HI

: GW-DISARM ( -- )
    0 GW-ARMED !  0 GW-HDR !  0 GW-ENT !
    0 GW-BENT !  0 GW-BHDR ! ;

\ Arm the permit for the slot FREE-SLOT chose.
\ Every failure path leaves the permit fully
\ disarmed, so a refused arm cannot leave a
\ half-populated set behind.
: GPT-ARM ( -- flag )
    GW-DISARM
    SEC-READ-VEC @ 0= IF 0 EXIT THEN
    RD-BUF-ADDR @ 0= IF 0 EXIT THEN
    FS-SLOT @ DUP 0<
    SWAP GPT-ENT-MAX < 0= OR IF 0 EXIT THEN
    1 1 SEC-READ-VEC @ EXECUTE IF 0 EXIT THEN
    RD-BUF-ADDR @ @ GPT-SIG-LO = 0= IF
        0 EXIT
    THEN
    RD-BUF-ADDR @ 4 + @ GPT-SIG-HI = 0= IF
        0 EXIT
    THEN
    RD-BUF-ADDR @ GPT-ALT-HI + @ IF 0 EXIT THEN
    RD-BUF-ADDR @ GPT-ALT-LO + @
    DUP 0< IF DROP 0 EXIT THEN
    DUP GPT-ARR-SECS - MIN-LBA < IF
        DROP 0 EXIT
    THEN
    GW-BHDR !
    GW-BHDR @ GPT-ARR-SECS -
    FS-SLOT @ 2 RSHIFT + GW-BENT !
    FS-SLOT @ SLOT-LBA GW-ENT !
    1 GW-HDR !
    -1 GW-ARMED !
    -1 ;

\ Membership in the four-LBA set. Unarmed
\ refuses first, and while unarmed every slot
\ holds 0 -- so an unarmed permit cannot be
\ tricked into matching LBA 0 either.
: GPT-PERMIT? ( lba -- flag )
    GW-ARMED @ 0= IF DROP 0 EXIT THEN
    DUP GW-HDR @ = IF DROP -1 EXIT THEN
    DUP GW-ENT @ = IF DROP -1 EXIT THEN
    DUP GW-BENT @ = IF DROP -1 EXIT THEN
    GW-BHDR @ = ;

: GPT-WRITE ( buf lba -- )
    DUP GPT-PERMIT? 0=
    ABORT" INSTALL: refuse, not a GPT sector"
    SEC-WRITE-VEC @ 0=
    ABORT" INSTALL: refuse, no writer bound"
    SWAP 1 SWAP
    SEC-WRITE-VEC @ EXECUTE
    ABORT" INSTALL: GPT write failed" ;

\ ============================================
\ ADD-PARTITION
\ ============================================
\ The one sanctioned write outside OWN-EXTENT.
\ Read-modify-writes exactly one 128-byte slot
\ in the GPT entry array, mirrors it to the
\ backup, recomputes both header CRCs, and
\ verifies every write by readback.
\
\ Caller provides a 128-byte entry at AP-ENT.
\ Preconditions: FREE-SLOT and GPT-ARM must
\ have succeeded (GW-ARMED true, FS-SLOT set,
\ the four-LBA permit populated).
\
\ The primary and backup ENTRY sectors are
\ byte-identical mirrors. The primary and
\ backup HEADERS are NOT -- they differ in
\ MyLBA, AlternateLBA, PartitionEntryLBA,
\ and their own HeaderCRC32. Each header is
\ patched in place from its own read, never
\ copied from the other.
\
\ HeaderSize is READ from the header (+0x0C),
\ bounded 92..512, and refused if out of
\ range. Hardcoding 92 against a header that
\ declares otherwise computes a CRC firmware
\ rejects, causing silent fallback to backup.

CREATE AP-SAVE 512 ALLOT
VARIABLE AP-ENT
VARIABLE AP-ECRC

\ GPT header field offsets
HEX
0C CONSTANT GPT-HSIZ-OFF
10 CONSTANT GPT-HCRC-OFF
58 CONSTANT GPT-ECRC-OFF
DECIMAL

92 CONSTANT GPT-HSIZ-MIN
512 CONSTANT GPT-HSIZ-MAX

\ ---- Snapshot and patch ----
\ Save the entry sector before modification
\ so the byte-identical gate can verify
\ neighbours are untouched.
: AP-SNAP ( -- )
    RD-BUF-ADDR @ AP-SAVE 512 CMOVE ;

\ Copy the 128-byte entry into our slot
\ within the sector buffer.
: AP-PATCH ( -- )
    AP-ENT @
    RD-BUF-ADDR @ FS-SLOT @ SLOT-OFF +
    GPT-ENT-SIZE CMOVE ;

\ ---- Entry-array CRC (streaming) ----
\ Hash all 32 entry sectors in ascending
\ order, reading each into the buffer.
\ Returns nonzero on success.
: AP-EARR-CRC ( -- flag )
    CRC-BEGIN
    GPT-ARR-LBA GPT-ARR-SECS + GPT-ARR-LBA
    DO
        I 1 SEC-READ-VEC @ EXECUTE IF
            0 UNLOOP EXIT
        THEN
        RD-BUF-ADDR @ 512 CRC-CHUNK
    LOOP
    CRC-END AP-ECRC !
    -1 ;

\ ---- Header CRC patch ----
\ Read a header at the given LBA, patch its
\ entry-array CRC, recompute HeaderCRC32,
\ write it back. HeaderSize is read from
\ +0x0C, bounded, and refused if out of
\ range. Returns nonzero on success.
: AP-HDR-PATCH ( lba -- flag )
    DUP 1 SEC-READ-VEC @ EXECUTE IF
        DROP 0 EXIT
    THEN
    \ Read and bound HeaderSize
    RD-BUF-ADDR @ GPT-HSIZ-OFF + @
    DUP GPT-HSIZ-MIN < IF
        2DROP 0 EXIT
    THEN
    DUP GPT-HSIZ-MAX > IF
        2DROP 0 EXIT
    THEN
    \ Stack: ( lba header-size )
    \ Patch entry-array CRC at +0x58
    AP-ECRC @
    RD-BUF-ADDR @ GPT-ECRC-OFF + !
    \ Zero the header's own CRC at +0x10
    0 RD-BUF-ADDR @ GPT-HCRC-OFF + !
    \ Hash HeaderSize bytes, write result
    RD-BUF-ADDR @ SWAP CRC-BEGIN
    CRC-CHUNK CRC-END
    RD-BUF-ADDR @ GPT-HCRC-OFF + !
    \ Write the patched header back
    RD-BUF-ADDR @ SWAP GPT-WRITE -1 ;

\ ---- Readback verification ----
\ Verify the entry sector at the given LBA
\ matches IO-BUF (the written content).
: AP-VERIFY-SEC ( lba -- flag )
    1 SEC-READ-VEC @ EXECUTE IF
        0 EXIT
    THEN
    512 0 DO
        RD-BUF-ADDR @ I + @
        IO-BUF I + @ = 0= IF
            0 UNLOOP EXIT
        THEN
    4 +LOOP
    -1 ;

\ Verify neighbours in the entry sector
\ are untouched. Compares all bytes outside
\ the 128-byte slot against AP-SAVE.
: AP-VERIFY-NBR ( -- flag )
    512 0 DO
        I FS-SLOT @ SLOT-OFF DUP
        GPT-ENT-SIZE + SWAP
        \ Stack: ( I slot-end slot-start )
        \ Skip bytes inside our slot
        ROT DUP ROT >= SWAP ROT < AND IF
        ELSE
            RD-BUF-ADDR @ I + @
            AP-SAVE I + @ = 0= IF
                0 UNLOOP EXIT
            THEN
        THEN
    4 +LOOP
    -1 ;

\ ---- Dual-array verify (decision #4) ----
\ Read all 32 backup entry sectors, hash
\ them, and refuse if the CRC differs from
\ AP-ECRC (the primary array's CRC). This
\ catches a pre-existing diverged backup --
\ writing a backup header whose CRC claims
\ content the backup array doesn't have
\ would leave an internally inconsistent
\ backup GPT.
: AP-VERIFY-BARR ( -- flag )
    CRC-BEGIN
    GW-BHDR @ GPT-ARR-SECS -
    DUP GPT-ARR-SECS + SWAP DO
        I 1 SEC-READ-VEC @ EXECUTE IF
            0 UNLOOP EXIT
        THEN
        RD-BUF-ADDR @ 512 CRC-CHUNK
    LOOP
    CRC-END AP-ECRC @ = ;

\ ---- Header CRC readback verify ----
\ Read a header back, recompute its CRC
\ from the bytes on disk, and refuse if it
\ does not match the CRC the header claims.
\ This is the final proof that what was
\ written is what the firmware will read.
: AP-VERIFY-HDR ( lba -- flag )
    1 SEC-READ-VEC @ EXECUTE IF
        0 EXIT
    THEN
    RD-BUF-ADDR @ GPT-HSIZ-OFF + @
    DUP GPT-HSIZ-MIN < IF DROP 0 EXIT THEN
    DUP GPT-HSIZ-MAX > IF DROP 0 EXIT THEN
    \ Save the claimed CRC before zeroing
    RD-BUF-ADDR @ GPT-HCRC-OFF + @
    SWAP
    \ Zero the CRC field for recomputation
    0 RD-BUF-ADDR @ GPT-HCRC-OFF + !
    \ Hash and compare
    RD-BUF-ADDR @ SWAP CRC-BEGIN
    CRC-CHUNK CRC-END
    = ;

\ ---- Top-level orchestration ----
\ ADD-PARTITION ( entry -- flag )
\
\ Sequence:
\   1. Read primary entry sector
\   2. Snapshot it (AP-SNAP)
\   3. Patch our entry into our slot
\   4. Save patched sector to IO-BUF
\   5. GPT-WRITE to primary entry sector
\   6. GPT-WRITE same sector to backup
\   7. Verify primary readback + neighbours
\   8. Verify backup = primary (byte-ident)
\   9. Streaming CRC over all 32 entry secs
\  10. Verify backup array = primary array
\  11. Patch primary header CRC, write
\  12. Patch backup header CRC, write
\  13. Verify both header CRCs by readback
: ADD-PARTITION ( entry -- flag )
    AP-ENT !
    GW-ARMED @ 0= IF 0 EXIT THEN
    SEC-WRITE-VEC @ 0= IF 0 EXIT THEN
    SEC-READ-VEC @ 0= IF 0 EXIT THEN
    RD-BUF-ADDR @ 0= IF 0 EXIT THEN
    AP-ENT @ 0= IF 0 EXIT THEN
    \ 1. Read the primary entry sector
    GW-ENT @ 1
    SEC-READ-VEC @ EXECUTE IF 0 EXIT THEN
    \ 2. Snapshot before modification
    AP-SNAP
    \ 3. Patch our entry into the slot
    AP-PATCH
    \ 4. Copy patched sector to IO-BUF
    RD-BUF-ADDR @ IO-BUF 512 CMOVE
    \ 5. Write primary entry sector
    IO-BUF GW-ENT @ GPT-WRITE
    \ 6. Write backup entry sector (mirror)
    IO-BUF GW-BENT @ GPT-WRITE
    \ 7. Verify primary + neighbours
    GW-ENT @ AP-VERIFY-SEC 0= IF
        0 EXIT
    THEN
    AP-VERIFY-NBR 0= IF 0 EXIT THEN
    \ 8. Verify backup = primary
    GW-BENT @ AP-VERIFY-SEC 0= IF
        0 EXIT
    THEN
    \ 9. Entry-array CRC (streaming)
    AP-EARR-CRC 0= IF 0 EXIT THEN
    \ 10. Verify backup array = primary
    AP-VERIFY-BARR 0= IF 0 EXIT THEN
    \ 11. Patch and write primary header
    GW-HDR @ AP-HDR-PATCH 0= IF
        0 EXIT
    THEN
    \ 12. Patch and write backup header
    GW-BHDR @ AP-HDR-PATCH 0= IF
        0 EXIT
    THEN
    \ 13. Verify both headers by readback
    GW-HDR @ AP-VERIFY-HDR 0= IF
        0 EXIT
    THEN
    GW-BHDR @ AP-VERIFY-HDR 0= IF
        0 EXIT
    THEN
    -1 ;

\ ============================================
\ Canonical ForthOS partition GUIDs.
\ Frozen 2026-08-05, minted ONCE-EVER.
\ Provenance: python3 uuid.uuid4(); cells are
\ little-endian 32-bit reads of bytes_le;
\ round-trip via uuid.UUID(bytes_le=...)
\ asserted at mint time. Never re-mint.
\ DELIBERATE GPT BEND: ForthOS identity lives
\ in the UNIQUE field because GRUB search has
\ no type-GUID mode (--part-uuid matches the
\ unique field only). Do not "fix" this.
\ These eight constants are the ONLY GUID
\ literals in the project. gen-grub-cfg.py
\ pattern-scans this file for the FOS-UG*
\ lines below; keep exactly one definition
\ per cell, on its own line, this format.
\ type: 4e011d24-9e20-45e8-bc49-85eb14c68532
HEX
4E011D24 CONSTANT FOS-TG0
45E89E20 CONSTANT FOS-TG1
EB8549BC CONSTANT FOS-TG2
3285C614 CONSTANT FOS-TG3
\ uniq: 32ba60fb-4548-4d4c-a439-fb80ce572b31
32BA60FB CONSTANT FOS-UG0
4D4C4548 CONSTANT FOS-UG1
80FB39A4 CONSTANT FOS-UG2
312B57CE CONSTANT FOS-UG3
DECIMAL

\ ---- Uniqueness scan (fail-closed) ----
\ True iff FOS-UNIQ-GUID appears nowhere in
\ the 32 primary entry sectors ON DISK. Disk,
\ not the surveyor map: disk is the stronger
\ authority and immune to same-session
\ staleness. Inherits the fail-open read
\ hazard: ANY flagged read refuses -- never
\ "no hit in the sectors I could read".
: GUID-AT? ( off -- flag )
    RD-BUF-ADDR @ + 16 +
    DUP @ FOS-UG0 =
    OVER 4 + @ FOS-UG1 = AND
    OVER 8 + @ FOS-UG2 = AND
    SWAP 12 + @ FOS-UG3 = AND ;

: GUID-ABSENT? ( -- flag )
    SEC-READ-VEC @ 0= IF 0 EXIT THEN
    RD-BUF-ADDR @ 0= IF 0 EXIT THEN
    GPT-ARR-LBA GPT-ARR-SECS +
    GPT-ARR-LBA DO
        I 1 SEC-READ-VEC @ EXECUTE IF
            0 UNLOOP EXIT THEN
        512 0 DO
            I GUID-AT? IF
                0 UNLOOP UNLOOP EXIT THEN
        GPT-ENT-SIZE +LOOP
    LOOP
    -1 ;

\ ---- Canonical entry composer ----
\ The ONLY tooling path that builds our GPT
\ entry. ADD-PARTITION still accepts any
\ hand-built entry -- deliberate operator
\ power, not an oversight; the uniqueness
\ guarantee holds for installs that compose
\ here, and the runbook composes here
\ unconditionally. Extent source: OWN-BASE/
\ OWN-LEN, i.e. AFTER FREE-EXTENT's claim.
CREATE OWN-ENT GPT-ENT-SIZE ALLOT

: MOE-NAME ( -- )
    70 OWN-ENT 56 + C!  79 OWN-ENT 58 + C!
    82 OWN-ENT 60 + C!  84 OWN-ENT 62 + C!
    72 OWN-ENT 64 + C!  79 OWN-ENT 66 + C!
    83 OWN-ENT 68 + C! ;

: MAKE-OWN-ENT ( -- entry | 0 )
    OWN-BASE @ 0= IF 0 EXIT THEN
    OWN-LEN @ 0= IF 0 EXIT THEN
    GUID-ABSENT? 0= IF 0 EXIT THEN
    OWN-ENT GPT-ENT-SIZE 0 FILL
    FOS-TG0 OWN-ENT !
    FOS-TG1 OWN-ENT 4 + !
    FOS-TG2 OWN-ENT 8 + !
    FOS-TG3 OWN-ENT 12 + !
    FOS-UG0 OWN-ENT 16 + !
    FOS-UG1 OWN-ENT 20 + !
    FOS-UG2 OWN-ENT 24 + !
    FOS-UG3 OWN-ENT 28 + !
    OWN-BASE @ OWN-ENT 32 + !
    0 OWN-ENT 36 + !
    OWN-BASE @ OWN-LEN @ + 1-
    OWN-ENT 40 + !
    0 OWN-ENT 44 + !
    MOE-NAME
    OWN-ENT ;

\ ==== Task 4: ADD-BOOT-ENTRY, step 0 ====
\ Controller-ready probe and the G1 (LBA 0
\ byte-identical) baseline/compare pair.
\
\ Fail-open read hazard (observed on iron,
\ 2026-08-01): an uninitialized controller
\ returns flag=1 with an ALL-ZERO buffer.
\ A gate that ignored the flag would compare
\ zero==zero and pass. So: a buffer is
\ meaningless unless the read returned 0,
\ and an all-zero LBA 0 is a failed read,
\ not an empty MBR. Every word below errors
\ (returns 0) rather than trusting such a
\ buffer -- an error must never read as
\ "identical".

\ Memdisk image physical base, snapshotted
\ once at load from the bootloader-set cell
\ at 28098 (hex). The bootloader wrote it
\ before this file could load, so the
\ snapshot is always valid; production and
\ tests both read the ForthOS-owned cell,
\ never the live kernel variable. 0 = not a
\ memdisk boot = no pristine source =
\ refuse. The raw address also appears as
\ MEMDISK-VAR in the paid ahci.fth --
\ duplicated because public code cannot
\ name a paid word; if the bootloader var
\ ever moves, update both.
VARIABLE MEM-BASE
HEX 28098 @ DECIMAL MEM-BASE !

CREATE LBA0-SAVE 512 ALLOT
VARIABLE LBA0-OK?

\ Boot signature at buffer end. Also rejects
\ the all-zero buffer of a failed read.
: ABE-SIG? ( -- flag )
    RD-BUF-ADDR @ 510 + C@ 85 =
    RD-BUF-ADDR @ 511 + C@ 170 = AND ;

\ Step-0 probe: reader bound, buffer set,
\ pristine memdisk source present, and LBA 0
\ reads back flag=0 with the signature.
: ABE-READY? ( -- flag )
    SEC-READ-VEC @ 0= IF 0 EXIT THEN
    RD-BUF-ADDR @ 0= IF 0 EXIT THEN
    MEM-BASE @ 0= IF 0 EXIT THEN
    0 1 SEC-READ-VEC @ EXECUTE IF
        0 EXIT
    THEN
    ABE-SIG? ;

\ G1 baseline capture. Never stores a buffer
\ from a failed read; clears the trust flag
\ first so a refused capture cannot leave a
\ stale baseline looking fresh.
: LBA0-BASELINE ( -- flag )
    0 LBA0-OK? !
    ABE-READY? 0= IF 0 EXIT THEN
    RD-BUF-ADDR @ LBA0-SAVE 512 CMOVE
    -1 LBA0-OK? ! -1 ;

\ G1 compare: -1 only when a fresh flag=0
\ read matches the trusted baseline. No
\ baseline or failed read = 0, same as a
\ mismatch -- fail closed.
: LBA0-SAME? ( -- flag )
    LBA0-OK? @ 0= IF 0 EXIT THEN
    ABE-READY? 0= IF 0 EXIT THEN
    512 0 DO
        RD-BUF-ADDR @ I + @
        LBA0-SAVE I + @ = 0= IF
            0 UNLOOP EXIT
        THEN
    4 +LOOP
    -1 ;

\ ---- Step 3: build the VBR image ----
\ Decision A: the DAP start-LBA field is
\ patched with OWN-BASE+KERNEL-OFFSET at a
\ FIXED offset. VBR-LBA-OFF must equal the
\ assembled template's dap+8; the harness
\ derives that from build/vbr.bin (the
\ CHS-removal chainload variant, the
\ artifact of record) at run time and goes
\ red loudly on drift.
1 CONSTANT KERNEL-OFFSET
375 CONSTANT VBR-LBA-OFF

\ Bit 31 set: at/past LBA-HORIZON, so no
\ permitted OWN-BASE+1 can ever equal it.
\ Sentinel-vs-real is disjoint by
\ construction, not by improbability.
HEX DEADBEEF CONSTANT VBR-SENTINEL DECIMAL

\ Template source. 0 = none = refuse. The
\ test fixture or the block-loaded real
\ template stores its address here.
VARIABLE VBR-TPL
CREATE VBR-IMG 512 ALLOT

\ G5-R3 gate: the bake fired. The sentinel
\ means an unpatched copy -- refused
\ explicitly, even though = expected
\ already excludes it, so a broken
\ expected-value calc cannot alias into a
\ pass.
: VBR-BAKED? ( -- flag )
    VBR-IMG VBR-LBA-OFF + @
    DUP VBR-SENTINEL = IF DROP 0 EXIT THEN
    OWN-BASE @ KERNEL-OFFSET + = ;

\ G5-R4 gate: chainloadable. GRUB's
\ chainloader +1 needs 55 AA at 510.
: VBR-SIGNED? ( -- flag )
    VBR-IMG 510 + C@ 85 =
    VBR-IMG 511 + C@ 170 = AND ;

\ Copy template, bake OWN-BASE+KERNEL-OFFSET
\ into the DAP field, then gate the result.
\ Only the copy is patched -- a template
\ with a real LBA baked in would poison
\ every later build. Refusals touch
\ nothing, including a previously built
\ image.
: BUILD-VBR ( -- flag )
    VBR-TPL @ 0= IF 0 EXIT THEN
    OWN-BASE @ 0= IF 0 EXIT THEN
    VBR-TPL @ 510 + C@ 85 =
    VBR-TPL @ 511 + C@ 170 = AND
    0= IF 0 EXIT THEN
    VBR-TPL @ VBR-IMG 512 CMOVE
    OWN-BASE @ KERNEL-OFFSET +
    VBR-IMG VBR-LBA-OFF + !
    VBR-BAKED? VBR-SIGNED? AND ;

\ ---- Step 1: kernel fits the extent ----
\ Must match the padded kernel image the
\ proven loader loads (KERNEL_PADDED_SIZE
\ 1C000h / 512 = 224). The harness derives
\ this from build/kernel.bin at run time
\ and goes red loudly on drift.
224 CONSTANT KERNEL-SECTORS

\ Extent holds VBR + kernel. Unclaimed
\ (OWN-LEN 0) refuses.
: ABE-FITS? ( -- flag )
    OWN-LEN @
    KERNEL-OFFSET KERNEL-SECTORS +
    < 0= ;

\ ---- Step 2b: G2 ESP sampled tripwire ----
\ SAMPLED by design: first + last + two
\ fixed interior sectors. The allowlist is
\ the guarantee; this is a tripwire. Do
\ not tighten.
VARIABLE ESP-BASE
VARIABLE ESP-LEN
VARIABLE ESP-OK?
CREATE ESP-SAVE 2048 ALLOT

\ Sample i -> LBA. Interior picks are fixed
\ LCG constants folded into (1..len-2), so
\ they are reproducible and never collide
\ with first/last.
: ESP-SAMPLE ( i -- lba )
    DUP 0= IF DROP ESP-BASE @ EXIT THEN
    DUP 1 = IF
        DROP ESP-BASE @ ESP-LEN @ + 1 -
        EXIT
    THEN
    2 = IF 48271 ELSE 16807 THEN
    ESP-LEN @ 2 - MOD 1+ ESP-BASE @ + ;

\ Cell-wise sector compare.
: SEC=? ( a1 a2 -- flag )
    512 0 DO
        OVER I + @ OVER I + @ =
        0= IF 2DROP 0 UNLOOP EXIT THEN
    4 +LOOP
    2DROP -1 ;

\ Read sample i into the bound buffer.
\ True only on a flag=0 read.
: ESP-RD ( i -- flag )
    ESP-SAMPLE 1
    SEC-READ-VEC @ EXECUTE 0= ;

\ Capture the 4 samples. Refuses on an
\ undeclared or too-small ESP, unbound
\ reader, or any failed read; a refusal
\ never leaves a stale baseline trusted.
: ESP-BASELINE ( -- flag )
    0 ESP-OK? !
    ESP-BASE @ 0= IF 0 EXIT THEN
    ESP-LEN @ 4 < IF 0 EXIT THEN
    SEC-READ-VEC @ 0= IF 0 EXIT THEN
    RD-BUF-ADDR @ 0= IF 0 EXIT THEN
    4 0 DO
        I ESP-RD 0= IF 0 UNLOOP EXIT THEN
        RD-BUF-ADDR @
        ESP-SAVE I 512 * + 512 CMOVE
    LOOP
    -1 ESP-OK? ! -1 ;

\ Re-read the samples and compare. No
\ baseline or a failed read = 0, same as
\ a mismatch -- fail closed.
: ESP-SAME? ( -- flag )
    ESP-OK? @ 0= IF 0 EXIT THEN
    ESP-BASE @ 0= IF 0 EXIT THEN
    ESP-LEN @ 4 < IF 0 EXIT THEN
    4 0 DO
        I ESP-RD 0= IF 0 UNLOOP EXIT THEN
        RD-BUF-ADDR @
        ESP-SAVE I 512 * + SEC=?
        0= IF 0 UNLOOP EXIT THEN
    LOOP
    -1 ;

\ ---- Step 2c: G3 GPT CRC tripwire ----
VARIABLE GPT-OK?
VARIABLE GPT-SAVE

\ Streaming CRC over LBA 1..33: header +
\ primary entry array. Backup structures
\ excluded: unreachable by construction
\ (allowlist), and G3 is a tripwire.
: GPT-SUM ( -- sum -1 | 0 )
    SEC-READ-VEC @ 0= IF 0 EXIT THEN
    RD-BUF-ADDR @ 0= IF 0 EXIT THEN
    CRC-BEGIN
    34 1 DO
        I 1 SEC-READ-VEC @ EXECUTE IF
            0 UNLOOP EXIT
        THEN
        RD-BUF-ADDR @ 512 CRC-CHUNK
    LOOP
    CRC-END -1 ;

\ One-cell baseline of the streamed sum.
: GPT-BASELINE ( -- flag )
    0 GPT-OK? !
    GPT-SUM 0= IF 0 EXIT THEN
    GPT-SAVE !
    -1 GPT-OK? ! -1 ;

\ Fail closed: no baseline or failed sum
\ = 0, same as a mismatch.
: GPT-SAME? ( -- flag )
    GPT-OK? @ 0= IF 0 EXIT THEN
    GPT-SUM 0= IF 0 EXIT THEN
    GPT-SAVE @ = ;

\ ---- Steps 4-7: the whole word ----
\ Step-6 sample sectors: first, last, two
\ fixed-LCG interior picks. Same shape as
\ ESP-SAMPLE; exposed so tests derive the
\ watch list from the artifact.
: KRN-SAMPLE ( i -- sec )
    DUP 0= IF DROP 0 EXIT THEN
    DUP 1 = IF
        DROP KERNEL-SECTORS 1 - EXIT
    THEN
    2 = IF 48271 ELSE 16807 THEN
    KERNEL-SECTORS 2 - MOD 1+ ;

\ Kernel sector i: memdisk source address
\ (Decision B: the pristine RAM image at
\ MEM-BASE+512) and destination LBA.
: KRN-SRC ( i -- addr )
    512 * MEM-BASE @ + 512 + ;
: KRN-LBA ( i -- lba )
    OWN-BASE @ KERNEL-OFFSET + + ;

\ Step-6 sample: a fresh flag=0 read of the
\ written sector must match its source.
\ Validates the write path; image content
\ is proven only at iron G6. Fail closed.
: KRN-CHK ( i -- flag )
    DUP KRN-LBA 1
    SEC-READ-VEC @ EXECUTE IF
        DROP 0 EXIT
    THEN
    KRN-SRC RD-BUF-ADDR @ SEC=? ;

\ Step-6 VBR readback vs the built image.
: VBR-CHK ( -- flag )
    OWN-BASE @ 1
    SEC-READ-VEC @ EXECUTE IF 0 EXIT THEN
    VBR-IMG RD-BUF-ADDR @ SEC=? ;

\ Step 4: every kernel sector, ascending
\ from OWN-BASE+KERNEL-OFFSET, via
\ SAFE-WRITE. Any out-of-extent or failed
\ write ABORTs loudly inside SAFE-WRITE; a
\ partial install never returns a flag.
: ABE-KWRITE ( -- )
    KERNEL-SECTORS 0 DO
        I KRN-SRC I KRN-LBA SAFE-WRITE
    LOOP ;

\ The orchestration. Gate refusals return
\ 0 before anything reaches the disk;
\ write faults ABORT. -1 only when every
\ step and every gate passed. VBR is
\ written LAST: an interrupted install
\ leaves no chainloadable sector behind.
: ADD-BOOT-ENTRY ( -- flag )
    ABE-READY? 0= IF 0 EXIT THEN
    ABE-FITS? 0= IF 0 EXIT THEN
    LBA0-BASELINE 0= IF 0 EXIT THEN
    ESP-BASELINE 0= IF 0 EXIT THEN
    GPT-BASELINE 0= IF 0 EXIT THEN
    BUILD-VBR 0= IF 0 EXIT THEN
    ABE-KWRITE
    VBR-IMG OWN-BASE @ SAFE-WRITE
    VBR-CHK 0= IF 0 EXIT THEN
    4 0 DO
        I KRN-SAMPLE KRN-CHK
        0= IF 0 UNLOOP EXIT THEN
    LOOP
    LBA0-SAME? 0= IF 0 EXIT THEN
    ESP-SAME? 0= IF 0 EXIT THEN
    GPT-SAME? 0= IF 0 EXIT THEN
    -1 ;

\ Binds if AHCI is already in the search
\ order; silently does not if it is not.
BIND-WRITER AHCI-WRITE
BIND-READER AHCI-READ

ONLY FORTH DEFINITIONS
DECIMAL
