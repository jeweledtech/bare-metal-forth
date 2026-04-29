# TASK: NTFS Bulk File Streaming

## Purpose

Close the 4 KB read gap in the NTFS vocabulary.  Today `FILE-READ`
reads at most 8 sectors of run #1 of any file.  This task implements
a multi-run streaming reader that walks all data runs and delivers
complete files to a configurable sink word.

The first (and default) sink sends file data as chunked UDP packets
to the dev machine using the framing protocol defined in
`docs/2026-04-28-substrate-design.md`.  The receiver is implemented
separately in `TASK_NET_RECEIVER.md`.

## Success criteria

1. New vocabulary `forth/dict/file-stream.fth` loads after NTFS and
   RTL8168, exposes `FILE-STREAM ( addr len -- )` that extracts a
   complete file from the HP NTFS partition and sends it over UDP.
2. Validated on HP bare metal: `S" i8042prt.sys" FILE-STREAM` produces
   118,272 bytes on the dev machine with correct SHA-256.
3. Multi-run files (fragmented) stream correctly — all data runs are
   walked, not just run #1.
4. Sparse runs (offset-size nibble = 0) emit zeros rather than
   reading from a garbage LBA.
5. The sink is a deferred word: `VARIABLE 'FILE-SINK` / `@ EXECUTE`.
   Alternate sinks can be plugged in without modifying the reader.
6. Block-loadable: all lines ≤ 64 chars.

## Architecture

```
FILE-STREAM ( addr len -- )
    ├── MFT-FIND → record#
    ├── MFT-READ → load record into MFT-BUF
    ├── Locate $DATA attribute (ATTR-DATA MFT-ATTR)
    ├── Extract total file size from $DATA header (+30)
    ├── Compute session ID: CRC32 of filename
    ├── Send chunk 0 (header + filename + first payload)
    ├── For each data run (PARSE-RUN loop):
    │   ├── Accumulate absolute cluster → LBA
    │   ├── If sparse (offset-size = 0):
    │   │   └── Zero-fill SEC-BUF, call sink for run-length
    │   ├── Else: For each 8-sector batch in this run:
    │   │   ├── AHCI-READ → SEC-BUF (4 KB)
    │   │   └── 'FILE-SINK @ EXECUTE
    │   └── Advance chunk index
    └── STREAM-DONE → send EOF marker packet
```

## Dependencies

```
\ REQUIRES: NTFS ( MFT-FIND MFT-READ ATTR-DATA MFT-ATTR )
\ REQUIRES: NTFS ( PARSE-RUN PR-PTR PR-LEN PR-OFF RUN-PREV )
\ REQUIRES: NTFS ( SEC/CLUS PART-LBA MFT-BUF )
\ REQUIRES: RTL8168 ( UDP-SEND RTL-FOUND )
\ REQUIRES: AHCI ( AHCI-READ SEC-BUF )
\ REQUIRES: HARDWARE ( PHYS-ALLOC )
```

## New words

### CRC-32

```
CRC32-TABLE         ( -- addr )    256 × 4-byte lookup table
CRC32               ( addr len -- crc )  Standard CRC-32
```

Implementation: table-driven, polynomial 0xEDB88320 (reflected).
The table is 1 KB (256 × 4 bytes), allocated with CREATE + data
in the vocabulary source.  ~20 lines of Forth.

### Framing

```
CHUNK-HDR           ( -- addr )    20-byte header buffer
CHUNK-NAME          ( -- addr )    256-byte filename buffer
CHUNK#              ( -- addr )    Variable: current chunk index
STREAM-SID          ( -- addr )    Variable: session ID (CRC-32)
STREAM-SIZE         ( -- addr )    Variable: total file size
STREAM-SENT         ( -- addr )    Variable: bytes sent so far
```

### Sink infrastructure

```
VARIABLE 'FILE-SINK              \ Holds XT of sink word
: DO-SINK ( buf len -- )         \ Call the current sink
    'FILE-SINK @ EXECUTE ;
```

### Net-chunk sink (default)

```
NET-CHUNK-SINK      ( buf len -- )
    Builds FBLK header into CHUNK-HDR
    Sends header + payload as UDP packet(s)
    Increments CHUNK#
```

For chunk 0: sends 20-byte header + 256-byte filename + payload
(limited to fit in one UDP packet: 1458 - 280 = 1178 bytes max).

For chunks 1+: sends 20-byte header + payload
(up to 1434 bytes per packet).

A 4 KB SEC-BUF batch becomes 3 UDP packets (1434 + 1434 + 1228).

### Top-level

```
FILE-STREAM         ( addr len -- )   Stream a file by name
STREAM-DONE         ( -- )            Send EOF marker
```

## Framing protocol (byte layout)

Common header (all packets, 20 bytes, big-endian):

```
Offset  Size  Field
------  ----  -----
0       4     Magic: 0x46424C4B ("FBLK")
4       4     Session ID (CRC-32 of filename)
8       4     Total file size (bytes)
12      4     Chunk index (0-based, monotonic)
16      2     Payload byte count
18      2     Flags: bit 0 = EOF, bit 1 = sparse chunk
20      ...   Payload (or chunk-0 supplement)
```

Chunk-0 supplement (between header and payload):

```
20      256   Filename, NUL-padded, case-preserved from MFT
276     ...   Payload (≤ 1182 bytes)
```

## Sparse-run handling

In `PARSE-RUN`, after decoding the header byte:
- Low nibble = length-size (how many bytes encode cluster count)
- High nibble = offset-size (how many bytes encode offset)

If offset-size = 0, the run is sparse (no on-disk allocation).
The correct behavior:
1. Zero-fill SEC-BUF (4096 bytes of 0x00)
2. Call DO-SINK with appropriate byte count
3. Set flag bit 1 in the chunk header so receiver knows

For .sys/.dll/.exe binaries, sparse never fires in practice.

## What NOT to do

- **Do not modify AHCI-READ or SET-PRD.** Keep using SEC-BUF as-is.
- **Do not modify NTFS vocab words.** Reuse PARSE-RUN, MFT-FIND,
  MFT-ATTR directly — they're battle-tested.
- **Do not implement SHA-256 in Forth.** The receiver handles
  integrity verification.
- **Do not add a receive path.** This is one-way: ForthOS → dev.
- **Do not add retry/ACK.** Reliability is "re-run on failure."

## Testing

Cannot test in QEMU (no NTFS disk with RTL8168 NIC).  Validation
is on HP bare metal:

1. PXE boot HP, load vocabs: `USING RTL8168  RTL8168-INIT`
   then `USING NTFS  NTFS-INIT`  then load file-stream vocab.
2. Start receiver on dev machine: `python3 tools/net-receive.py`
3. Run: `S" i8042prt.sys" FILE-STREAM`
4. Verify: receiver reports 118,272 bytes, SHA-256 matches known
   fixture hash `e1887a4e678bba7226e7ebe5b49ec821c2f23642d321a9e1513f7477e4b9340d`.
5. Test fragmented file: find one via `MFT-MAP.` analysis or
   extract `ntoskrnl.exe` (always fragmented on Windows installs).

## Done criteria

- `FILE-STREAM` streams complete files (all runs) over UDP.
- Python receiver reassembles correctly with SHA-256 match.
- Sparse detection works (even if never triggered on real .sys).
- Sink is pluggable via VARIABLE pattern.
- All .fth lines ≤ 64 chars.
- Committed to public repo.
