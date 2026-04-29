# FILE-STREAM Vocabulary Design

**Date:** 2026-04-29
**Status:** Design — ready for implementation
**Parent:** `docs/2026-04-28-substrate-design.md` (architecture),
`docs/TASK_NTFS_BULK_STREAM.md` (task spec),
`docs/TASK_NET_RECEIVER.md` (receiver spec, already implemented)

## Context

The UBT pipeline has been working against 14 hand-copied fixture files
because `FILE-READ` in the NTFS vocab only reads run #1 of any file,
capped at 8 sectors (4 KB). A 126 KB DLL gets 3% extracted; a 10 MB
ntoskrnl.exe gets 0.04%.

The substrate design (committed 2026-04-28) established the
architecture: sector-streaming through a deferred sink, 4 KB batches
via SEC-BUF, no large buffers. The Python receiver
(`tools/net-receive.py`, 14/14 tests) is complete.

What remains is the Forth-side sender: ~100 lines of block-loadable
Forth in a new `forth/dict/file-stream.fth` vocabulary.

## Repo placement: PRIVATE

`file-stream.fth` lives in the **private** repo
(`forthos-vocabularies/forth/dict/file-stream.fth`). Rationale:
all three of its REQUIRES deps (NTFS, AHCI, RTL8168) are private
vocabs. It bridges the Disk Stack ($19) and UBT Pipeline Tools
($29) tiers — bundled into Disk Stack as a value-add.

Development happens in `~/projects/forthos`, then the final file
is mirrored to `~/projects/forthos-vocabularies/` per the
established mirror discipline. The public repo's .gitignore
already excludes paid files.

Post-implementation:
- Add block range in private repo's write-catalog config
- Add to README-private vocabulary table under Disk Stack
- Update Shopify Disk Stack product description

## File: `forthos-vocabularies/forth/dict/file-stream.fth`

Single vocabulary, four clearly separated sections with cut-point
comments for future extraction.

### Catalog header

```
\ CATALOG: FILE-STREAM
\ CATEGORY: substrate
\ PLATFORM: x86
\ SOURCE: hand-written
\ REQUIRES: NTFS AHCI RTL8168
\ CONFIDENCE: medium
```

Search order: `ALSO NTFS`, `ALSO AHCI`, `ALSO RTL8168`.
Closes with `ONLY FORTH DEFINITIONS DECIMAL`.

### Section 1: CRC-32 (~25 lines)

Table-driven CRC-32 with polynomial 0xEDB88320 (reflected).

```
CREATE CRC32-TABLE  400 ALLOT
```

The 256-entry table (1 KB) is built at load time by a compile-time
loop. Each entry: `crc = crc XOR poly` when low bit set, else
`crc >> 1`, iterated 8 times per byte value.

Words:

| Word | Stack effect | Description |
|------|-------------|-------------|
| `CRC32-TABLE` | `( -- addr )` | 256 x 4-byte lookup table |
| `CRC32-INIT` | `( -- )` | Build table at load time |
| `CRC32` | `( addr len -- crc )` | Standard CRC-32 |

CRC32 implementation: start with `FFFFFFFF`, for each byte XOR into
low byte of CRC, look up `CRC32-TABLE + (low-byte * 4)`, XOR with
`CRC >> 8`. Final XOR with `FFFFFFFF`.

### Section 2: FBLK framing (~30 lines)

State variables:

| Word | Type | Description |
|------|------|-------------|
| `CHUNK-HDR` | CREATE 14 ALLOT | 20-byte header buffer |
| `CHUNK-NAME` | CREATE 100 ALLOT | 256-byte filename buffer |
| `CHUNK#` | VARIABLE | Current chunk index |
| `STREAM-SID` | VARIABLE | Session ID (CRC-32) |
| `STREAM-SIZE` | VARIABLE | Total file size |
| `STREAM-SENT` | VARIABLE | Bytes sent so far |

Header builder:

`BUILD-HDR ( payload-len flags -- )` fills CHUNK-HDR with big-endian
fields: magic 0x46424C4B, session ID, total size, chunk index,
payload length, flags. Uses manual byte stores (C!) for big-endian
encoding on little-endian x86.

Big-endian store helper: `BE! ( val addr -- )` stores a 32-bit value
in big-endian byte order. `BE-W! ( val addr -- )` stores 16-bit.

### Section 3: Sink infrastructure (~10 lines)

```
VARIABLE 'FILE-SINK
: DO-SINK ( buf len -- ) 'FILE-SINK @ EXECUTE ;
```

Default sink: `NET-CHUNK-SINK`.

`NET-CHUNK-SINK ( buf len -- )`:
- Builds FBLK header via BUILD-HDR
- For chunk 0: copies CHUNK-HDR (20) + CHUNK-NAME (256) + payload
  into a send buffer, UDP-SEND. Max payload: 1178 bytes.
- For chunks 1+: copies CHUNK-HDR (20) + payload into send buffer,
  UDP-SEND. Max payload: 1434 bytes.
- A 4 KB batch becomes 3 UDP packets (1434 + 1434 + 1228).
- Increments CHUNK# after each packet.

`STREAM-DONE ( -- )`: sends EOF marker packet (header with flag
bit 0 set, zero payload).

Send buffer: reuses TX-BUF area from RTL8168 for frame construction.
The UDP-SEND word already expects payload addr+len and builds the
Ethernet/IP/UDP headers in TX-BUF. NET-CHUNK-SINK prepends the FBLK
header to the payload before calling UDP-SEND.

Implementation note: UDP-SEND takes `( -- )` after setting TX-PAYLOAD
and TX-PLEN. NET-CHUNK-SINK must set these variables with the
combined header+payload buffer, then call UDP-SEND.

### Section 4: FILE-STREAM (~40 lines)

The multi-run streaming reader.

`FILE-STREAM ( addr len -- )`:

1. Save filename: copy addr/len into CHUNK-NAME (NUL-padded to 256).
2. CRC32 of filename -> STREAM-SID.
3. MFT-FIND -> record#. Abort with message if not found.
4. MFT-READ -> load record into MFT-BUF.
5. Locate $DATA attribute: `ATTR-DATA MFT-ATTR`. Abort if missing.
6. Check non-resident flag: attribute+8 byte must be nonzero.
7. Extract file size: attribute + 30 (hex), low 4 bytes -> STREAM-SIZE.
8. Initialize: 0 -> CHUNK#, 0 -> STREAM-SENT, 0 -> RUN-PREV.
9. Set PR-PTR to start of run list: attribute + (attribute+20 word).
10. Send chunk 0: first AHCI-READ batch gets the filename supplement.
11. PARSE-RUN loop:
    a. Call PARSE-RUN. If returns 0, done.
    b. Check offset-size nibble (PR-OFF source):
       - If sparse (offset=0): zero-fill SEC-BUF, call DO-SINK
         with sparse flag for PR-LEN * SEC/CLUS sectors of data.
       - Else: PR-OFF + RUN-PREV -> absolute cluster.
         Update RUN-PREV. Convert to LBA (* SEC/CLUS + PART-LBA).
         Loop: AHCI-READ 8 sectors, DO-SINK, advance LBA,
         until run's sectors exhausted.
    c. Repeat until PARSE-RUN returns 0.
12. STREAM-DONE (EOF marker).

Sparse detection: before calling PARSE-RUN, peek at the header
byte at `PR-PTR @ C@` and check its high nibble (offset-size).
If high nibble = 0, the run is sparse — no disk offset encoded.
This is more reliable than checking PR-OFF after PARSE-RUN,
because LE-S@ with 0 bytes produces 0 which is indistinguishable
from a legitimate zero offset in degenerate cases. Peek first,
then call PARSE-RUN to advance PR-PTR and get PR-LEN.

## Key constraints

- **All lines <= 64 chars.** Block-loadable format.
- **No modification to NTFS, AHCI, or RTL8168 vocabs.**
- **No SHA-256 in Forth.** Receiver handles integrity.
- **No retry/ACK.** One-way emitter. Re-run on failure.
- **No large buffers.** Everything flows through SEC-BUF (4 KB).

## Dependencies on NTFS internals

These words/variables are used from NTFS vocab:

| Word | Purpose in FILE-STREAM |
|------|----------------------|
| `MFT-FIND` | Locate file by name |
| `MFT-READ` | Load MFT record into MFT-BUF |
| `MFT-BUF` | The loaded MFT record |
| `MFT-ATTR` | Find attribute by type |
| `ATTR-DATA` | Constant 0x80 ($DATA attribute type) |
| `PARSE-RUN` | Decode one data run |
| `PR-PTR` | Run-list position pointer |
| `PR-LEN` | Decoded run length (clusters) |
| `PR-OFF` | Decoded run offset (signed, relative) |
| `RUN-PREV` | Accumulated absolute cluster |
| `SEC/CLUS` | Sectors per cluster |
| `PART-LBA` | NTFS partition start LBA |
| `FOUND-REC` | MFT-FIND result record# |
| `SEC-BUF` | AHCI DMA buffer (4 KB) |

## Testing

Cannot test in QEMU (no NTFS disk + RTL8168 NIC together).

Validation on HP bare metal:

1. PXE boot, load vocabs:
   `USING RTL8168  RTL8168-INIT`
   `USING NTFS  NTFS-INIT`
   Then load file-stream vocab.
2. Start receiver: `python3 tools/net-receive.py --verbose`
3. Run: `S" i8042prt.sys" FILE-STREAM`
4. Verify: receiver reports 118,272 bytes with correct SHA-256.
5. Test fragmented file: `S" ntoskrnl.exe" FILE-STREAM`
   (always fragmented on Windows installs, exercises multi-run).

## Verification checklist

- [ ] `FILE-STREAM` streams all runs, not just run #1
- [ ] Receiver reassembles with correct SHA-256
- [ ] Chunk 0 contains filename, subsequent chunks do not
- [ ] Session ID matches CRC-32 of filename
- [ ] Sparse runs emit zeros (testable synthetically if no sparse
      files exist on HP)
- [ ] Alternate sink pluggable via `'FILE-SINK !`
- [ ] All .fth lines <= 64 chars
- [ ] Vocab ends with `ONLY FORTH DEFINITIONS DECIMAL`
- [ ] `tools/net-receive.py` handles the actual packet stream
