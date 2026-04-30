# FILE-STREAM Vocabulary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a multi-run NTFS file streaming vocabulary that extracts complete files from the HP's NTFS disk and sends them as chunked UDP packets to the dev machine.

**Architecture:** Single `file-stream.fth` vocab (~100 lines) with four sections: CRC-32, FBLK framing, sink infrastructure, and the streaming reader. Streams 4 KB batches through SEC-BUF to a deferred sink word. The Python receiver (`tools/net-receive.py`, already complete) reassembles and verifies.

**Tech Stack:** Forth-83 (block-loadable, all lines <= 64 chars), Python 3 (receiver, already done)

**Spec:** `docs/superpowers/specs/2026-04-29-file-stream-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `forth/dict/file-stream.fth` | Create | The complete vocabulary (dev in public repo, mirror to private) |
| `tests/test_file_stream_helpers.py` | Create | QEMU-based tests for CRC-32 and BE!/BE-W! (no NTFS/RTL8168 needed) |
| `Makefile` | Modify | Add `test-file-stream` target |

---

### Task 1: CRC-32 and BE!/BE-W! test harness

Write a Python test that boots QEMU, sends CRC-32 and BE! definitions interactively (no vocab loading needed), and verifies against known values. This proves the utility words before anything depends on them.

**Files:**
- Create: `tests/test_file_stream_helpers.py`
- Modify: `Makefile` (add test target)

- [ ] **Step 1: Write the test file**

Create `tests/test_file_stream_helpers.py`:

```python
#!/usr/bin/env python3
"""Test CRC-32 and BE!/BE-W! helpers in QEMU.

These are standalone definitions sent interactively —
no vocab loading or NTFS/RTL8168 deps needed.
"""
import socket, time, sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4560

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(5)
s.connect(('127.0.0.1', PORT))

time.sleep(1.5)
try:
    while True:
        s.recv(4096)
except:
    pass


def send(cmd, wait=1.0):
    s.sendall((cmd + '\r').encode())
    time.sleep(wait)
    s.settimeout(2)
    resp = b''
    while True:
        try:
            d = s.recv(4096)
            if not d:
                break
            resp += d
        except:
            break
    return resp.decode('ascii', errors='replace')


PASS = 0
FAIL = 0


def check(name, response, pattern):
    global PASS, FAIL
    if pattern in response:
        PASS += 1
        print(f'  PASS: {name}')
    else:
        FAIL += 1
        print(f'  FAIL: {name}'
              f' -- expected "{pattern}"'
              f' in {response.strip()!r}')


# ================================================
# Define BE-W! and BE! interactively
# ================================================
send('HEX', 0.5)

# BE-W! stores 16-bit big-endian
send(': BE-W! OVER 8 RSHIFT OVER C! '
     '1+ SWAP FF AND SWAP C! ;', 1.0)

# BE! stores 32-bit big-endian
# Split across multiple sends to stay under
# QEMU serial buffer limits
send(': BE! OVER 18 RSHIFT OVER C!', 0.5)
send('1+ OVER 10 RSHIFT FF AND', 0.5)
send('OVER C! 1+ OVER 8 RSHIFT', 0.5)
send('FF AND OVER C! 1+ SWAP', 0.5)
send('FF AND SWAP C! ;', 1.0)

# Allocate test buffer
send('VARIABLE TB1', 0.5)
send('VARIABLE TB2', 0.5)

# ---- BE-W! tests ----

# Test 1: BE-W! with 0x1234
send('1234 TB1 BE-W!', 0.5)
r = send('TB1 C@ .', 0.5)
check('BE-W! high byte 0x12', r, '18')

r = send('TB1 1+ C@ .', 0.5)
check('BE-W! low byte 0x34', r, '52')

# Test 2: BE-W! with 0x0001
send('1 TB1 BE-W!', 0.5)
r = send('TB1 C@ .', 0.5)
check('BE-W! 0x0001 high=0', r, '0')

r = send('TB1 1+ C@ .', 0.5)
check('BE-W! 0x0001 low=1', r, '1')

# ---- BE! tests ----

# Test 3: BE! with 0x12345678
send('12345678 TB1 BE!', 0.5)
r = send('TB1 C@ .', 0.5)
check('BE! byte0=0x12', r, '18')

r = send('TB1 1+ C@ .', 0.5)
check('BE! byte1=0x34', r, '52')

r = send('TB1 2 + C@ .', 0.5)
check('BE! byte2=0x56', r, '86')

r = send('TB1 3 + C@ .', 0.5)
check('BE! byte3=0x78', r, '120')

# Test 4: BE! with 0xDEADBEEF
send('DEADBEEF TB1 BE!', 0.5)
r = send('TB1 C@ .', 0.5)
check('BE! 0xDE=222', r, '222')

r = send('TB1 1+ C@ .', 0.5)
check('BE! 0xAD=173', r, '173')

r = send('TB1 2 + C@ .', 0.5)
check('BE! 0xBE=190', r, '190')

r = send('TB1 3 + C@ .', 0.5)
check('BE! 0xEF=239', r, '239')

# ================================================
# Define CRC-32 interactively
# ================================================
send('HEX', 0.5)
send('EDB88320 CONSTANT CRC32-POLY', 0.5)
send('FFFFFFFF CONSTANT CRC32-MASK', 0.5)
send('DECIMAL', 0.5)
send('CREATE CRC32-TABLE 1024 ALLOT', 1.0)

# CRC32-INIT: build the 256-entry table
send(': CRC32-INIT 256 0 DO', 0.5)
send('I 8 0 DO DUP 1 AND IF', 0.5)
send('1 RSHIFT CRC32-POLY XOR', 0.5)
send('ELSE 1 RSHIFT THEN', 0.5)
send('LOOP CRC32-TABLE I 4 * + !', 0.5)
send('LOOP ;', 1.0)

# CRC32: compute CRC-32 of (addr len)
send(': CRC32 CRC32-MASK -ROT', 0.5)
send('0 DO OVER I + C@', 0.5)
send('OVER XOR 255 AND 4 *', 0.5)
send('CRC32-TABLE + @', 0.5)
send('SWAP 8 RSHIFT XOR', 0.5)
send('LOOP NIP CRC32-MASK XOR ;', 1.0)

# Build the table
r = send('CRC32-INIT', 2.0)

# Test 5: CRC-32 of empty string
# CRC-32("") = 0x00000000 (length 0 loop
# does nothing, mask XOR mask = 0)
r = send('HEX', 0.3)
r = send('TB1 0 CRC32 .', 1.0)
check('CRC32 empty=0', r, '0')

# Test 6: CRC-32 table entry 0
# Entry 0 should be 0 (0 XOR'd 8 times)
r = send('CRC32-TABLE @ .', 0.5)
check('CRC32-TABLE[0]=0', r, '0')

# Test 7: CRC-32 table entry 1
# Byte 1: shift right 1, XOR poly = EDB88320
r = send('CRC32-TABLE 4 + @ .', 0.5)
check('CRC32-TABLE[1]=EDB88320',
      r, 'EDB88320')

# Test 8: CRC-32 of "123456789"
# Standard test vector: CRC32 = 0xCBF43926
send('DECIMAL', 0.3)
send('CREATE TVEC 9 ALLOT', 0.5)
# Store "123456789" byte by byte
send('49 TVEC C!', 0.3)       # '1'
send('50 TVEC 1+ C!', 0.3)    # '2'
send('51 TVEC 2 + C!', 0.3)   # '3'
send('52 TVEC 3 + C!', 0.3)   # '4'
send('53 TVEC 4 + C!', 0.3)   # '5'
send('54 TVEC 5 + C!', 0.3)   # '6'
send('55 TVEC 6 + C!', 0.3)   # '7'
send('56 TVEC 7 + C!', 0.3)   # '8'
send('57 TVEC 8 + C!', 0.3)   # '9'
send('HEX', 0.3)
r = send('TVEC 9 CRC32 .', 1.0)
check('CRC32 "123456789"=CBF43926',
      r, 'CBF43926')

# ================================================
# Summary
# ================================================
s.close()

print(f'\n{PASS} passed, {FAIL} failed'
      f' out of {PASS + FAIL}')
sys.exit(1 if FAIL else 0)
```

- [ ] **Step 2: Add Makefile target**

In `Makefile`, add `test-file-stream` target. Find the line with `test-integration` target (around line 199) and add after it. Use port offset +55 to avoid conflicts:

```makefile
test-file-stream: $(IMAGE)
	@PORT=$$(($(TEST_PORT_BASE)+55)); \
	echo "=== FILE-STREAM helpers (port $$PORT) ==="; \
	pkill -9 -f "[q]emu.*$$PORT" 2>/dev/null || true; \
	sleep 0.5; \
	qemu-system-i386 \
		-drive file=build/bmforth.img,format=raw,if=floppy \
		-serial tcp::$$PORT,server=on,wait=off \
		-display none -daemonize; \
	sleep 2; \
	python3 tests/test_file_stream_helpers.py $$PORT; \
	RESULT=$$?; \
	pkill -9 -f "[q]emu.*$$PORT" 2>/dev/null || true; \
	exit $$RESULT
```

Also add `test-file-stream` to the `test:` prerequisite list and the `.PHONY` line.

- [ ] **Step 3: Run the test to verify it fails**

```bash
make test-file-stream
```

Expected: PASS on BE!/BE-W! tests, PASS on CRC-32 tests. If any fail, the definitions have bugs that must be fixed before proceeding.

This step validates the Forth code in isolation before it gets embedded in the vocab file.

- [ ] **Step 4: Commit**

```bash
git add tests/test_file_stream_helpers.py Makefile
git commit -m "tests: CRC-32 and BE!/BE-W! helper validation for FILE-STREAM"
```

---

### Task 2: Write file-stream.fth — CRC-32 section

Write the first section of the vocabulary file with catalog header, constants, and CRC-32 implementation.

**Files:**
- Create: `forth/dict/file-stream.fth`

- [ ] **Step 1: Write the catalog header and CRC-32 section**

Create `forth/dict/file-stream.fth` with this exact content (every line verified <= 64 chars):

```forth
\ ============================================
\ CATALOG: FILE-STREAM
\ CATEGORY: substrate
\ PLATFORM: x86
\ SOURCE: hand-written
\ REQUIRES: NTFS ( MFT-FIND MFT-READ MFT-BUF )
\ REQUIRES: NTFS ( MFT-ATTR ATTR-DATA PARSE-RUN )
\ REQUIRES: NTFS ( PR-PTR PR-LEN PR-OFF RUN-PREV )
\ REQUIRES: NTFS ( SEC/CLUS PART-LBA FOUND-REC )
\ REQUIRES: AHCI ( AHCI-READ SEC-BUF )
\ REQUIRES: RTL8168 ( UDP-SEND TX-PAYLOAD TX-PLEN )
\ CONFIDENCE: medium
\ ============================================
\
\ Stream complete files off NTFS over UDP.
\ Multi-run reader + FBLK chunked transport.
\
\ Usage:
\   USING FILE-STREAM
\   S" i8042prt.sys" FILE-STREAM
\
\ Receiver: tools/net-receive.py
\
\ ============================================

VOCABULARY FILE-STREAM
FILE-STREAM DEFINITIONS
ALSO NTFS
ALSO AHCI
ALSO RTL8168
HEX

\ ============================================
\ Section 1: CRC-32
\ ============================================

EDB88320 CONSTANT CRC32-POLY
FFFFFFFF CONSTANT CRC32-MASK

DECIMAL
CREATE CRC32-TABLE 1024 ALLOT

: CRC32-INIT ( -- )
    256 0 DO
        I
        8 0 DO
            DUP 1 AND IF
                1 RSHIFT CRC32-POLY XOR
            ELSE
                1 RSHIFT
            THEN
        LOOP
        CRC32-TABLE I 4 * + !
    LOOP
;

CRC32-INIT

: CRC32 ( addr len -- crc )
    CRC32-MASK -ROT
    0 DO
        OVER I + C@
        OVER XOR 255 AND 4 *
        CRC32-TABLE + @
        SWAP 8 RSHIFT XOR
    LOOP
    NIP CRC32-MASK XOR
;
```

Note: CRC32-POLY and CRC32-MASK are defined in HEX context (set at line 29 of the vocab). CRC32-TABLE and CRC32-INIT use DECIMAL (set just before CREATE). `CRC32-INIT` is called at load time immediately after definition to populate the table.

- [ ] **Step 2: Verify all lines <= 64 chars**

```bash
python3 tools/lint-forth.py forth/dict/file-stream.fth
```

Expected: no errors. If any line exceeds 64 chars, split it.

- [ ] **Step 3: Commit**

```bash
git add forth/dict/file-stream.fth
git commit -m "file-stream: CRC-32 section (table + compute word)"
```

---

### Task 3: Write file-stream.fth — FBLK framing section

Add the big-endian helpers, FBLK constants, state variables, and header builder.

**Files:**
- Modify: `forth/dict/file-stream.fth` (append after CRC-32 section)

- [ ] **Step 1: Append the FBLK framing section**

Add after the CRC32 word definition, before any closing `ONLY FORTH DEFINITIONS`:

```forth

\ ============================================
\ Section 2: FBLK framing
\ ============================================

HEX
46424C4B CONSTANT FBLK-MAGIC
DECIMAL
20 CONSTANT FBLK-HDR-SZ
256 CONSTANT FBLK-NAME-SZ
4096 CONSTANT FBLK-CHUNK-SZ
1434 CONSTANT MAX-PAYLOAD
1 CONSTANT F-EOF
2 CONSTANT F-SPARSE

CREATE CHUNK-HDR  20 ALLOT
CREATE CHUNK-NAME 256 ALLOT
CREATE SEND-BUF   1500 ALLOT
VARIABLE CHUNK#
VARIABLE STREAM-SID
VARIABLE STREAM-SIZE
VARIABLE STREAM-SENT

\ Big-endian 16-bit store
: BE-W! ( val addr -- )
    OVER 8 RSHIFT OVER C!
    1+ SWAP 255 AND SWAP C!
;

\ Big-endian 32-bit store
: BE! ( val addr -- )
    OVER 24 RSHIFT OVER C!
    1+ OVER 16 RSHIFT 255 AND
    OVER C! 1+
    OVER 8 RSHIFT 255 AND
    OVER C! 1+
    SWAP 255 AND SWAP C!
;

\ Build 20-byte FBLK header in CHUNK-HDR
: BUILD-HDR ( payload-len flags -- )
    SWAP
    FBLK-MAGIC CHUNK-HDR BE!
    STREAM-SID @ CHUNK-HDR 4 + BE!
    STREAM-SIZE @ CHUNK-HDR 8 + BE!
    CHUNK# @ CHUNK-HDR 12 + BE!
    CHUNK-HDR 16 + BE-W!
    CHUNK-HDR 18 + BE-W!
;
```

Note: `FF` is hex — but we're in DECIMAL context here. Use `255` instead. The BE! line splitting keeps every line under 64 chars. `MAX-PAYLOAD` is 1434 (decimal): `1500 MTU - 14 ETH - 20 IP - 8 UDP - 20 FBLK-HDR = 1438`, rounded to `1434` for alignment with the spec.

- [ ] **Step 2: Verify all lines <= 64 chars**

```bash
python3 tools/lint-forth.py forth/dict/file-stream.fth
```

- [ ] **Step 3: Commit**

```bash
git add forth/dict/file-stream.fth
git commit -m "file-stream: FBLK framing section (BE!, BUILD-HDR, state vars)"
```

---

### Task 4: Write file-stream.fth — Sink infrastructure + NET-CHUNK-SINK

Add the deferred sink variable, the UDP chunking sink, and the EOF sender.

**Files:**
- Modify: `forth/dict/file-stream.fth` (append after framing section)

- [ ] **Step 1: Append the sink infrastructure section**

```forth

\ ============================================
\ Section 3: Sink infrastructure
\ ============================================

VARIABLE 'FILE-SINK

: DO-SINK ( buf len -- )
    'FILE-SINK @ EXECUTE
;

\ Send one UDP packet from SEND-BUF.
\ Copies CHUNK-HDR + data into SEND-BUF,
\ then calls UDP-SEND.
: SEND-CHUNK ( data-addr data-len -- )
    CHUNK-HDR SEND-BUF
    FBLK-HDR-SZ CMOVE
    CHUNK# @ 0= IF
        \ Chunk 0: hdr + name + data
        CHUNK-NAME SEND-BUF FBLK-HDR-SZ +
        FBLK-NAME-SZ CMOVE
        SEND-BUF FBLK-HDR-SZ +
        FBLK-NAME-SZ + SWAP CMOVE
        SEND-BUF SWAP
        FBLK-HDR-SZ + FBLK-NAME-SZ +
    ELSE
        \ Chunks 1+: hdr + data
        SEND-BUF FBLK-HDR-SZ + SWAP
        CMOVE
        SEND-BUF SWAP FBLK-HDR-SZ +
    THEN
    UDP-SEND
    1 CHUNK# +!
;

\ Default sink: chunk into UDP packets
: NET-CHUNK-SINK ( buf len -- )
    BEGIN DUP 0> WHILE
        DUP MAX-PAYLOAD MIN
        2DUP 0 BUILD-HDR
        2 PICK SWAP SEND-CHUNK
        DUP STREAM-SENT +!
        ROT OVER + -ROT -
    REPEAT
    2DROP
;

\ Send EOF marker (zero-payload packet)
: STREAM-DONE ( -- )
    0 F-EOF BUILD-HDR
    CHUNK-HDR SEND-BUF
    FBLK-HDR-SZ CMOVE
    SEND-BUF FBLK-HDR-SZ UDP-SEND
;
```

Key design note: `NET-CHUNK-SINK` receives the full 4 KB SEC-BUF contents and internally loops, sending up to `MAX-PAYLOAD` (1434) bytes per UDP packet. `/STRING` does NOT exist in the kernel, so pointer advance is done manually: `ROT OVER + -ROT -` which does `( addr len consumed -- addr+consumed len-consumed )`.

- [ ] **Step 2: Verify /STRING is correctly avoided**

`/STRING` does NOT exist in the kernel (verified). The code uses manual pointer arithmetic instead: `ROT OVER + -ROT -` which does `( addr len consumed -- addr+consumed len-consumed )`. Confirm this line is present in NET-CHUNK-SINK as written above.

- [ ] **Step 3: Verify all lines <= 64 chars**

```bash
python3 tools/lint-forth.py forth/dict/file-stream.fth
```

- [ ] **Step 4: Commit**

```bash
git add forth/dict/file-stream.fth
git commit -m "file-stream: sink infrastructure + NET-CHUNK-SINK"
```

---

### Task 5: Write file-stream.fth — FILE-STREAM multi-run reader

The core word that walks all data runs and streams through the sink.

**Files:**
- Modify: `forth/dict/file-stream.fth` (append after sink section)

- [ ] **Step 1: Append the FILE-STREAM section**

```forth

\ ============================================
\ Section 4: FILE-STREAM
\ ============================================

HEX
20 CONSTANT ATTR-RUNOFF
30 CONSTANT ATTR-RSIZE
DECIMAL

VARIABLE FS-ATTR
VARIABLE FS-LBA
VARIABLE FS-RSECS
VARIABLE FS-SPARSE

\ Zero-fill SEC-BUF for sparse runs
: ZERO-SEC-BUF ( -- )
    SEC-BUF FBLK-CHUNK-SZ 0 FILL
;

\ Compute bytes to send for this batch.
\ Caps at remaining file size.
: BATCH-LEN ( secs -- bytes )
    512 *
    STREAM-SIZE @ STREAM-SENT @ -
    MIN
;

\ Send one run's data through sink.
\ FS-LBA = starting LBA of run.
\ FS-RSECS = total sectors in run.
: SEND-RUN ( -- )
    BEGIN FS-RSECS @ 0> WHILE
        FS-SPARSE @ IF
            ZERO-SEC-BUF
        ELSE
            FS-LBA @ 8 FS-RSECS @ MIN
            AHCI-READ DROP
        THEN
        8 FS-RSECS @ MIN BATCH-LEN
        DUP 0> IF
            SEC-BUF SWAP DO-SINK
        ELSE
            DROP
        THEN
        8 FS-LBA +!
        -8 FS-RSECS +!
    REPEAT
;

\ Stream a named file over the sink.
: FILE-STREAM ( addr len -- )
    \ Save filename into CHUNK-NAME
    CHUNK-NAME FBLK-NAME-SZ 0 FILL
    2DUP CHUNK-NAME SWAP CMOVE
    \ Compute session ID
    2DUP CRC32 STREAM-SID !
    \ Find file in MFT
    MFT-FIND 0= IF
        ." Not found" CR EXIT
    THEN
    FOUND-REC !
    FOUND-REC @ MFT-READ IF
        ." MFT read err" CR EXIT
    THEN
    \ Locate $DATA attribute
    ATTR-DATA MFT-ATTR
    DUP 0= IF
        DROP ." No DATA" CR EXIT
    THEN
    DUP 8 + C@ 0= IF
        DROP ." Resident" CR EXIT
    THEN
    FS-ATTR !
    \ Extract file size (+30h)
    FS-ATTR @ ATTR-RSIZE + @
    STREAM-SIZE !
    \ Initialize state
    0 CHUNK# !
    0 STREAM-SENT !
    0 RUN-PREV !
    \ Set run-list pointer
    FS-ATTR @ DUP ATTR-RUNOFF + W@ +
    PR-PTR !
    \ Walk all data runs
    BEGIN
        PR-PTR @ C@ DUP 0<> WHILE
        \ Peek high nibble for sparse
        4 RSHIFT 0= IF
            -1 FS-SPARSE !
        ELSE
            0 FS-SPARSE !
        THEN
        PARSE-RUN DROP
        \ Accumulate absolute cluster
        FS-SPARSE @ 0= IF
            PR-OFF @ RUN-PREV +!
        THEN
        \ Convert clusters to LBA
        RUN-PREV @ SEC/CLUS @ *
        PART-LBA @ + FS-LBA !
        PR-LEN @ SEC/CLUS @ *
        FS-RSECS !
        SEND-RUN
        \ Check if file fully sent
        STREAM-SENT @
        STREAM-SIZE @ >= IF
            PR-PTR @ C@ DROP 0
        THEN
    REPEAT
    DROP
    STREAM-DONE
    ." Streamed "
    STREAM-SENT @ DECIMAL . HEX
    ." bytes" CR
;

\ Set default sink
' NET-CHUNK-SINK 'FILE-SINK !

ONLY FORTH DEFINITIONS
DECIMAL
```

Key implementation notes:

1. **Sparse detection** (line `PR-PTR @ C@ DUP 0<> WHILE`): The outer BEGIN/WHILE reads the run header byte. If nonzero, peek its high nibble. If high nibble is 0, the run is sparse. PARSE-RUN is then called to advance PR-PTR and set PR-LEN (cluster count). For sparse runs, RUN-PREV is NOT updated (no offset to accumulate).

2. **BATCH-LEN** caps each read at the remaining file bytes. This prevents the last batch from sending padding beyond the file size.

3. **SEND-RUN** loops AHCI-READ in 8-sector batches. For sparse runs, it zero-fills SEC-BUF instead. Each batch goes through DO-SINK.

4. **Early termination**: After each run, if STREAM-SENT >= STREAM-SIZE, the loop exits. This handles files whose allocated clusters exceed the real file size (common with cluster-aligned allocation).

5. **`FS-RSECS +!` with -8**: Forth `+!` with a negative value decrements. `FS-RSECS` counts down from run's total sectors. The `MIN` in AHCI-READ handles the last partial batch (< 8 sectors).

- [ ] **Step 2: Verify all lines <= 64 chars**

```bash
python3 tools/lint-forth.py forth/dict/file-stream.fth
```

Fix any lines that exceed 64 characters by splitting or shortening.

- [ ] **Step 3: Verify no forbidden patterns**

```bash
# No 2* usage
grep '2\*' forth/dict/file-stream.fth

# No DEFER/IS usage
grep -i 'DEFER\|\ IS ' forth/dict/file-stream.fth

# No .( usage
grep '\.(' forth/dict/file-stream.fth

# No bare ' inside colon defs (only ['] allowed)
# The only bare ' should be the final binding line
grep -n "^[^\\\\].*'" forth/dict/file-stream.fth
```

Expected: no matches except the `' NET-CHUNK-SINK` at the end (which is in interpret mode, not inside a colon def).

- [ ] **Step 4: Commit**

```bash
git add forth/dict/file-stream.fth
git commit -m "file-stream: FILE-STREAM multi-run reader + vocab complete"
```

---

### Task 6: Verify QEMU compilation smoke test

Boot the kernel and attempt to define key words interactively to catch any syntax errors before HP testing. We can't load the full vocab (NTFS/AHCI/RTL8168 deps won't resolve), but we can verify the CRC-32 test harness still passes and manually test compilation of critical words.

**Files:** None (verification only)

- [ ] **Step 1: Run the automated helper tests**

```bash
make test-file-stream
```

Expected: all CRC-32 and BE!/BE-W! tests PASS (12/12 or however many are in the test file). This confirms the core utility words work correctly.

- [ ] **Step 2: Run full test suite to check for regressions**

```bash
make test
```

Expected: all existing tests still pass. The new file-stream.fth is not in the block catalog yet (it's a private repo file), so it won't be loaded during test-vocabs. No regressions.

---

### Task 7: Mirror to private repo and update catalog

Copy the validated file to the private repo, add it to the catalog, and update documentation.

**Files:**
- Copy: `forth/dict/file-stream.fth` -> `~/projects/forthos-vocabularies/forth/dict/file-stream.fth`
- Modify: Private repo README vocabulary table
- Modify: Private repo write-catalog config (if applicable)

- [ ] **Step 1: Mirror the file**

```bash
cp forth/dict/file-stream.fth \
   ~/projects/forthos-vocabularies/forth/dict/file-stream.fth
```

- [ ] **Step 2: Verify the private repo has the file and lint passes**

```bash
python3 tools/lint-forth.py \
    ~/projects/forthos-vocabularies/forth/dict/file-stream.fth
```

- [ ] **Step 3: Update private repo README**

Add to the vocabulary table under "Disk Stack" tier:

```
| file-stream.fth | Disk Stack | Stream files off NTFS over UDP |
```

- [ ] **Step 4: Commit in private repo**

```bash
cd ~/projects/forthos-vocabularies
git add forth/dict/file-stream.fth README.md
git commit -m "file-stream: multi-run NTFS streaming over UDP (Disk Stack)"
```

---

### Task 8: HP bare-metal validation

This is the real test. PXE boot the HP, load the vocab chain, stream a known file, and verify the receiver gets correct output.

**Files:** None (validation only)

- [ ] **Step 1: Start the receiver on the dev machine**

```bash
python3 tools/net-receive.py --port 6666 --outdir ./extracted/ --verbose
```

- [ ] **Step 2: PXE boot HP and load vocabs**

On the HP console (after PXE boot reaches `ok` prompt):

```forth
USING RTL8168  RTL8168-INIT
USING NTFS  NTFS-INIT
```

Then load the FILE-STREAM vocab (via block loading from the private repo's disk image, or by pasting the definitions interactively for first-time testing).

- [ ] **Step 3: Stream a known file**

```forth
USING FILE-STREAM
S" i8042prt.sys" FILE-STREAM
```

Expected console output:
```
Streamed 118272 bytes
```

Expected receiver output:
```json
{"filename": "i8042prt.sys", "size": 118272, "sha256": "e1887a4e678bba7226e7ebe5b49ec821c2f23642d321a9e1513f7477e4b9340d", "chunks_received": 84, ...}
```

- [ ] **Step 4: Verify SHA-256 matches known fixture**

```bash
sha256sum extracted/i8042prt.sys
```

Expected: `e1887a4e678bba7226e7ebe5b49ec821c2f23642d321a9e1513f7477e4b9340d`

- [ ] **Step 5: Test a fragmented file**

```forth
S" ntoskrnl.exe" FILE-STREAM
```

This exercises multi-run support. ntoskrnl.exe is always fragmented on Windows installs. The receiver should reassemble all chunks with zero gaps.

- [ ] **Step 6: Verify no gaps in receiver log**

Check that `"gaps": []` in the JSON output for both files. Any gaps indicate dropped UDP packets or chunk numbering errors.

---

## Post-implementation

After HP validation passes:

1. Update `docs/TASK_NTFS_BULK_STREAM.md` status to COMPLETE
2. Update Shopify Disk Stack product description with FILE-STREAM proof point
3. Save session memory noting FILE-STREAM is validated
