# ForthOS: NE2000 Multi-Block Vocabulary Transfer
**Date:** 2026-03-19  
**Status:** Ready for Claude Code  
**Commit base:** `52912c8` (296 tests passing)  
**Goal:** Transfer a complete Forth vocabulary (PIT-TIMER, 5 blocks) from instance A to instance B over Ethernet, load it on B with `THRU`, and execute a word from it. This is the "dictionary sharing over network" feature from the original vision.

---

## Context

Single-block transfer works (`8ca63ac`). Consecutive receives work (`0ea676f`). What's missing is the **write-to-disk + load** path on the receiver side. Currently `BLOCK-RECV` receives a frame into `RX-FRM` (a RAM buffer) but does not write it to the block storage disk image. To load a vocabulary on B, the received block data must be written into B's block buffer system so that `THRU` can find it.

### What BLOCK-SEND Does (A side)
Reads block N from disk into a buffer, wraps it in an Ethernet frame with a custom header, and sends via `NE2K-SEND`. The frame layout (in `forth/dict/net-dict.fth`):

```
Bytes 0-5:   Destination MAC (broadcast FF:FF:FF:FF:FF:FF)
Bytes 6-11:  Source MAC
Bytes 12-13: EtherType (custom, e.g. 0x4654 = 'FT' for Forth Transfer)
Bytes 14-15: Block number (big-endian or little-endian — check net-dict.fth)
Bytes 16-17: Block count (always 1 per frame)
Bytes 18+:   1024 bytes of block data
Total frame: ~1042 bytes
```

### What BLOCK-RECV Does (B side) — Current State
Calls `NE2K-RECV` into `RX-FRM`, parses the block number from the frame header, returns the block number. The block data sits in `RX-FRM+18` (or wherever the header ends). It is **not** written to disk.

---

## What Needs to Change

### Step 1 — Audit net-dict.fth

Read `forth/dict/net-dict.fth` completely before writing any code. Confirm:
- Exact frame header layout (byte offsets for block number, data start)
- What `BLOCK-RECV` currently returns and what it leaves on the stack
- Whether `RX-FRM` is a fixed address or a variable

### Step 2 — Add BLOCK-RECV-STORE

Add a new word to `forth/dict/net-dict.fth` that receives a block AND writes it into the block buffer system:

```forth
\ Receive one block and store it at the given block number on disk.
\ ( dest-block# -- actual-block# | -1 )
\ If no packet, returns -1.
\ If packet received, stores data at dest-block#, returns frame's block#.
: BLOCK-RECV-STORE ( dest-blk -- actual-blk | -1 )
    >R                          \ save dest block#
    RX-FRM 600 NE2K-RECV        \ receive into RX-FRM, returns byte count
    0= IF R> DROP -1 EXIT THEN  \ no packet
    \ Parse block# from frame header (offset 14, 2 bytes)
    RX-FRM 14 + W@              \ block# from frame (big-endian? check!)
    \ Write data into block system at dest-blk
    R@ BUFFER                   \ get buffer for dest block# (no disk read)
    RX-FRM 18 + SWAP            \ src = RX-FRM+18, dst = block buffer
    400 CMOVE                   \ copy 1024 bytes (0x400)
    R@ UPDATE                   \ mark dirty
    R> SAVE-BUFFERS             \ flush to disk immediately
    RX-FRM 14 + W@              \ return actual block# from frame
;
```

**Critical details to verify before writing:**
- The `W@` (16-bit read) endian order — if the sender uses `W!` at offset 14, the receiver should use `W@` at the same offset. Check `BLOCK-SEND` in net-dict.fth.
- `400 CMOVE` copies 1024 bytes. Verify `CMOVE` exists in the kernel or use a loop. If not, use `1024 0 DO RX-FRM 18 + I + C@ OVER I + C! LOOP DROP` as a fallback (ugly but correct).
- `SAVE-BUFFERS` after each block may be slow but is safe. Alternative: batch with a final flush after all blocks received.

### Step 3 — Add VOCAB-RECV

Add a word that receives N consecutive blocks and stores them at a target block range on B:

```forth
\ Receive N blocks starting at dest-block# with timeout.
\ ( dest-blk count -- received-count )
: VOCAB-RECV ( dest-blk count -- n )
    0 -ROT                      \ ( 0 dest-blk count )
    0 DO
        I OVER + OVER SWAP      \ ( n dest-blk+I dest-blk count )
        DROP                    \ ( n dest-blk+I )
        \ Poll for block with retries
        10 0 DO
            DUP BLOCK-RECV-STORE
            DUP -1 <> IF
                NIP              \ got it - discard dest-blk slot
                ROT 1+ -ROT     \ increment count
                LEAVE
            ELSE
                DROP
            THEN
            50 MS-DELAY         \ wait 50ms between polls
        LOOP
        DROP
    LOOP
    NIP                         \ leave only count
;
```

**Note:** Stack manipulation here is complex. Write it as multiple simpler words if the above is hard to fit in 64-char lines:

```forth
\ Simpler decomposition:
VARIABLE V-DEST    \ destination block#
VARIABLE V-GOT     \ count of blocks received

: VOCAB-RECV ( dest-blk count -- n )
    V-DEST !
    0 V-GOT !
    0 DO
        V-DEST @ I +
        10 0 DO
            DUP BLOCK-RECV-STORE
            -1 <> IF
                V-GOT @ 1+ V-GOT !
                LEAVE
            THEN
            50 MS-DELAY
        LOOP
        DROP
    LOOP
    V-GOT @
;
```

### Step 4 — Sender Side: VOCAB-SEND

Add to net-dict.fth (or verify it already exists):

```forth
\ Send blocks start-blk through end-blk.
\ ( start-blk end-blk -- )
: VOCAB-SEND ( start end -- )
    OVER - 1+            \ count
    SWAP                 \ ( count start )
    0 DO
        DUP I + BLOCK-SEND
        200 MS-DELAY     \ 200ms between blocks for receiver to process
    LOOP
    DROP
;
```

The `200 MS-DELAY` between sends gives B time to call `BLOCK-RECV-STORE` and flush. Adjust if tests show B keeping up or falling behind.

### Step 5 — Check MS-DELAY Availability

`MS-DELAY` must exist in the search order when `NET-DICT` loads. Check the `REQUIRES:` header in `net-dict.fth`. If `MS-DELAY` isn't available, use a busy-wait loop:

```forth
\ Fallback if MS-DELAY not available:
: NET-WAIT ( ms -- )  \ approximate ms delay
    0 DO
        DECIMAL 12000 0 DO LOOP   \ ~1ms at QEMU speed
    LOOP HEX
;
```

Prefer `MS-DELAY` from HARDWARE vocabulary if it's in scope.

---

## Test

Update `tests/test_ne2000_network.py` to add the vocabulary transfer test. The test must run after the existing single-block and consecutive-block tests.

```python
# Test: Full vocabulary transfer (PIT-TIMER, 5 blocks)
print("\nTest: Vocabulary transfer (PIT-TIMER)")

# Get PIT-TIMER block range from catalog
pit_s = block_ranges.get('PIT-TIMER', [224])[0]
pit_e = block_ranges.get('PIT-TIMER', [228])[-1]
pit_count = pit_e - pit_s + 1

# Choose a safe destination on B (high block numbers, won't conflict with B's catalog)
dest_base = 850

# Send from A
r = send(sa, f'DECIMAL {pit_s} {pit_e} VOCAB-SEND HEX', pit_count * 3 + 5)
ok_send = alive(sa)
check(f'A: VOCAB-SEND {pit_s}-{pit_e}', ok_send, f'{r.strip()[:80]!r}')

if ok_send:
    # Receive on B into dest_base
    r = send(sb, f'DECIMAL {dest_base} {pit_count} VOCAB-RECV . HEX',
             pit_count * 5 + 10)
    got_count = None
    for tok in r.split():
        try:
            got_count = int(tok)
            break
        except ValueError:
            pass
    check(f'B: VOCAB-RECV got {pit_count} blocks',
          got_count == pit_count,
          f'{r.strip()[:120]!r}')

    # Load the received vocabulary on B
    dest_end = dest_base + pit_count - 1
    r = send(sb, f'DECIMAL {dest_base} {dest_end} THRU HEX', 10)
    ok_load = alive(sb) and '?' not in r
    check('B: PIT-TIMER loads from received blocks', ok_load,
          f'{r.strip()[:120]!r}')

    if ok_load:
        # Access a word from the vocabulary
        r = send(sb, 'ALSO PIT-TIMER PIT-BASE . PREVIOUS', 3)
        check('B: PIT-BASE accessible after transfer',
              '40' in r or '64' in r,   # 0x40 = 64 decimal
              f'{r.strip()[:80]!r}')

check('A alive after vocab transfer', alive(sa))
check('B alive after vocab transfer', alive(sb))
```

**Block range discovery:** The test already has a `block_ranges` dict built during setup (or uses hardcoded values). If not, add:

```python
# At test setup, parse catalog output for block ranges
block_ranges = {}
r = send(sa, 'USING CATALOG-RESOLVER CATALOG-LIST', 5)
# Parse "Blocks N-M: VOCAB-NAME" lines
import re
for m in re.finditer(r'Blocks (\d+)-(\d+): (\S+)', r):
    block_ranges[m.group(3)] = (int(m.group(1)), int(m.group(2)))
```

If catalog parsing is complex, hardcode `pit_s = 224, pit_e = 228` based on the current catalog layout.

---

## Success Criteria

- [ ] `VOCAB-SEND` in net-dict.fth sends N blocks with inter-block delay
- [ ] `BLOCK-RECV-STORE` receives a block and writes it to disk (via `BUFFER`/`UPDATE`/`SAVE-BUFFERS`)
- [ ] `VOCAB-RECV` loops BLOCK-RECV-STORE for count blocks
- [ ] `make test-network` includes vocabulary transfer test and passes
- [ ] After transfer: `THRU` loads the vocabulary on B with no `?` errors
- [ ] After load: a word from the vocabulary (e.g., `PIT-BASE`) executes correctly on B
- [ ] A and B both alive after the full transfer
- [ ] `make test` still 296/296 (no regressions in non-network tests)
- [ ] Commit: `"NE2000: multi-block vocabulary transfer via Ethernet"`

---

## Known Constraints

- 64-character line limit in all `.fth` block source — check with `awk 'length > 64'`
- No `2*` — use `DUP +`
- `HEX`/`DECIMAL` mode must be explicit — net-dict.fth likely runs in HEX; watch for number literals
- `CMOVE` — verify it exists in the 178-word kernel before using; if not, use a `DO` loop
- `W@` — verify it exists for 16-bit port reads; if only `C@` available, build the 16-bit read from two byte reads
- `MS-DELAY` — in HARDWARE vocabulary; make sure it's in scope when net-dict.fth definitions are made
- `ROT` exists; `-ROT` may not — use `ROT ROT` if needed
- After `make write-catalog`, block numbers may shift — the test should either parse the catalog dynamically or re-confirm PIT-TIMER block range before hardcoding

## Timing Notes

The QEMU socket network is reliable but has latency. At 200ms inter-send delay with 50ms poll interval:
- 5-block PIT-TIMER transfer: ~1-2 seconds total
- Test timeout for `VOCAB-RECV .` call: set to `pit_count * 5 + 10` seconds
- If B misses blocks, increase inter-send delay to 300ms or 500ms

The send-then-poll-immediately pattern (send block, immediately poll B for receipt) is more reliable than batch-send-then-batch-receive. The `VOCAB-SEND` word with built-in delay handles the timing on the A side.
