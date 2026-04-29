# Substrate Design — Bulk Data Movement and Output Sinks

**Date:** 2026-04-28
**Status:** Design (commits to architecture; spawns task docs)
**Scope:** Phase 7 substrate work — the layer that carries bytes from
NTFS partitions into useful output destinations.

---

## What this document is

The UBT pipeline today reaches its first hardware bottleneck at the very
first step: getting full binaries off the HP's NTFS partition. The
existing `FILE-READ` reads at most 8 sectors (4 KB) of run #1 of any
file. A 126 KB DLL gets 3% of itself extracted; a 10 MB `ntoskrnl.exe`
gets 0.04% of itself extracted. The pipeline has been operating against
14 hand-copied fixtures because of this gap.

This document commits to the architecture that closes that gap, and
also commits to the *shape* that gap-closing has so future work
(metal-install persistence, USB-boot writeback, port-monitor streaming)
can reuse the substrate without redesign.

It does **not** specify byte-level layouts or exact word signatures —
those belong in the task docs that descend from this one.

---

## What changed in the analysis

An earlier framing assumed a "read whole file into a large buffer, then
ship it" pattern. Two pieces of ground truth from the kernel and the
NTFS vocab forced a rethink:

1. **`SEC-BUF` is hardcoded into `SET-PRD`.** The AHCI read path always
   DMAs into a single 4 KB buffer. Reading into a larger arbitrary
   buffer requires a new `SET-PRD-AT` variant, which is an extra
   surface area we don't need.

2. **The throughput math doesn't reward larger buffers.** Effective
   transfer rate is bounded by the AHCI command latency
   (~1 ms per 4 KB read) plus per-packet UDP TxOK wait
   (~10–50 µs × 3 packets per 4 KB). That's roughly 4 MB/s. A 10 MB
   `ntoskrnl.exe` lands in ~2.5 seconds. The bottleneck is sequential,
   not buffer size.

3. **Boot mode matters more than transport.** The previous framing
   assumed PXE — ForthOS in RAM, NTFS on the target machine, network
   the only path back. But the commercial endpoint is metal install:
   ForthOS *is* the OS on the extraction target. In that mode the
   network is an audit trail, not a data path.

These three together point at a substrate that streams sectors into
a *deferred sink* — same reader, multiple destinations selected at
runtime.

---

## The three-layer model

```
┌─────────────────────────────────────────────────────────────────┐
│  Layer 3: Orchestration                                         │
│           File-name resolution, manifest generation,            │
│           batch extraction, resume support                      │
├─────────────────────────────────────────────────────────────────┤
│  Layer 2: Sinks (deferred words)                                │
│           NET-CHUNK-SINK   →  UDP chunked transport             │
│           BLOCK-SINK       →  ForthOS block storage (Mode C)    │
│           FAT32-SINK       →  USB writeback (Mode B, deferred)  │
├─────────────────────────────────────────────────────────────────┤
│  Layer 1: Bulk read (the missing layer)                         │
│           Multi-run NTFS reader, sector-streaming, sparse-aware │
│           Always reads into existing 4 KB SEC-BUF               │
└─────────────────────────────────────────────────────────────────┘
```

Layer 1 is what's missing today. Layer 2 has one entry that exists in
skeleton form (`UDP-SEND` works, framing protocol does not) and two
entries that are deferred until needed. Layer 3 is the workflow
surface — the words a human types or scripts call.

The unifying pattern is `DEFER FILE-SINK`. The streaming reader hands
each 4 KB batch to whatever word `FILE-SINK` is bound to. Switching
output destinations is a single `IS` reassignment.

---

## Layer 1 — bulk read

### What exists

| Word              | Status                                                                 |
|-------------------|------------------------------------------------------------------------|
| `PARSE-RUN`       | Battle-tested. Decodes one run-list entry, sets `PR-LEN` and `PR-OFF`. |
| `RUN-PREV`        | Battle-tested. Accumulates absolute cluster position.                  |
| `BUILD-MFT-MAP`   | Battle-tested. Loops `PARSE-RUN` to build the MFT's run table.         |
| `MFT-FIND`        | Works, O(n) over all records (~30 s on HP's 1.2 M-record MFT).         |
| `AHCI-READ`       | Works. Always DMAs into `SEC-BUF` (4 KB).                              |
| `FILE-READ`       | Reads run #1 only, capped at 8 sectors. The gap.                       |
| `MFT-DATA-RUNS`   | Decodes run #1 only. Doesn't loop.                                     |

### What's needed

A multi-run streaming reader. Conceptually:

```
FILE-STREAM ( name-addr name-len -- )
    MFT-FIND →  record number
    Locate $DATA attribute
    For each data run in $DATA:
        If run is sparse (offset = 0):
            Emit zeros for run-length sectors via FILE-SINK
        Else:
            For each 8-sector batch in this run:
                AHCI-READ into SEC-BUF
                FILE-SINK ( SEC-BUF batch-byte-count -- )
                Advance LBA by 8 sectors
    Emit end-of-file marker via FILE-SINK
```

The 4 KB batch size keeps `SEC-BUF` reused across the whole transfer.
No new `PHYS-ALLOC`, no `SET-PRD` modification, no resizing.

Sparse-run detection is one branch on the offset-size nibble of the
run header byte. For `.sys` / `.dll` / `.exe` binaries this branch
fires essentially never, but the safe behavior — emit zeros, log a
warning — is one line and avoids silent corruption if it ever does
fire.

### What this commits to

- The reader produces a **sequence of 4 KB chunks plus an end marker**.
  Sinks consume that sequence.
- The reader **does not retry**. If the sink fails (network drop, write
  error), the orchestration layer detects it and re-runs the whole
  transfer.
- The reader **does not buffer the full file in RAM**. The largest
  resident state is `SEC-BUF` (4 KB) plus the run table.

### What this defers

- Path-based file resolution (`C:\Windows\System32\foo.sys` → MFT
  record). Today's `MFT-FIND` is filename-only. Path traversal is a
  Layer 3 concern, deferable until the orchestration layer needs it.
- Index-accelerated MFT search. The 30 s/file scan is acceptable for
  hundreds of files, painful for tens of thousands. Optimization
  belongs in its own task once the batch workflow exists.

---

## Layer 2 — sinks

### Net-chunk sink (first sink, this design commits to it)

A length-prefixed UDP chunk format with a 20-byte common header and a
filename block carried only in chunk 0. Receiver reassembles by
session ID and writes to disk on end-of-file flag.

Common header (every packet, 20 bytes):

```
Offset  Size  Field
------  ----  -----------------------------------------
0       4     Magic "FBLK"
4       4     Session ID (CRC-32 of filename, ForthOS-computed)
8       4     Total file size in bytes
12      4     Chunk index (0-based, monotonic)
16      2     Payload byte count in this packet
18      2     Flags: bit 0 = end-of-file, bit 1 = sparse
```

Chunk-0 supplement (chunk_index == 0 only):

```
20      256   Filename, NUL-padded UTF-8
```

Payload follows the header.

**Why CRC-32 in ForthOS, SHA-256 on the receiver.** CRC-32 is ~20 lines
of table-driven Forth, fast enough to not affect the 4 MB/s rate.
SHA-256 is ~100 lines of Forth and dominates the per-chunk cost. The
session ID's job is "group these chunks together in flight" — CRC-32
is sufficient. The receiver computes SHA-256 over the reassembled file
and reports it as a separate integrity hash. Each tool stays in its
lane.

**Why filename only in chunk 0.** Putting the 256-byte filename in
every packet eats 25% of payload throughput. Putting it only in chunk
0 means subsequent packets carry 1434 bytes of payload instead of
1178. The receiver opens `<filename>.partial` on chunk 0 arrival and
appends to it as later chunks arrive; on the end-of-file flag it
renames to `<filename>`.

**Why no ACK / retry.** The network console has been 100 % reliable
since commit `a603e08`. On a direct 1 Gbps link with TxOK polling, no
switch in the path, and no contention, drops are vanishingly rare.
The receiver's gap-detection log catches the edge case; if drops are
ever observed, the response is "re-run extraction," not "build retry
into ForthOS." This decision can be revisited if data shows it's
wrong.

### Block-storage sink (Mode C primary output, deferred to follow-on task)

For metal-install operation, extracted bytes need to land on ForthOS's
own block storage. The sink interface stays the same — `FILE-SINK ( buf
len -- )` — but the implementation writes to ForthOS blocks rather than
UDP packets. A small manifest block at the start of the extraction
range lists filename → starting block, sector count, and integrity
hash, so a later session can find files without re-walking NTFS.

This is committed to as a *shape* in this design. The actual
implementation lands in `TASK_BLOCK_SINK.md` after the net-chunk path
is validated.

### FAT32-writeback sink (Mode B, explicitly deferred)

Mode B (USB boot, write extracted vocabs back to the USB stick) needs
FAT32 *write* support. Today only FAT32 read works. This is a real
gap, but it's not a substrate gap — it's a vocabulary gap that the
substrate can plug in once it exists. This design **does not commit to
building FAT32 writeback now**. If/when Mode B becomes priority, that
sink slots in alongside the other two.

### Sinks not committed to in this design

- **Receive path on ForthOS** — no RX descriptor ring, no remote command
  channel, no firmware updates over network. ForthOS is a one-way
  emitter. Anything interactive happens through serial console or the
  screen.
- **TCP transport** — UDP with gap detection is sufficient.
- **Real-time port-monitor streaming** — uses the same sinks but is a
  different consumer, owned by the port-monitor work, not the
  bulk-extract substrate.

---

## Layer 3 — orchestration

Out of scope for this design. The task docs that build orchestration
on top of the substrate will commit to specifics. What this design
needs Layer 3 to know:

- Sinks are bound by `IS`. Orchestration code chooses the sink for a
  given workflow.
- The reader is one-shot per file. Batch extraction is a loop in
  orchestration, not a primitive in the reader.
- Failures are handled by re-running. The orchestration layer is
  responsible for resume support, gap handling, and manifest
  maintenance.

---

## Boot-mode targeting

| Mode | Description                              | First-target priority           |
|------|------------------------------------------|---------------------------------|
| A    | PXE boot, ForthOS in RAM, NTFS on target | **First** — current dev workflow |
| B    | USB boot, ForthOS from stick, NTFS on    | Deferred — needs FAT32 writeback |
|      | target                                   |                                 |
| C    | Metal install, ForthOS *is* the OS       | Second — needs BLOCK-SINK       |

The substrate is built for Mode A first because that's where validation
happens — direct ethernet to the dev machine, network console, and the
existing reliability of the UDP path. Mode C is one task doc away
(`TASK_BLOCK_SINK.md`) once the streaming reader and net sink are
green. Mode B waits on FAT32 writeback as a separate vocabulary
project.

---

## Substrate scope — the five commitments

1. **Sector-streaming as the universal data movement pattern.** The
   reader produces a sequence of 4 KB chunks plus an end marker. Sinks
   are deferred words.

2. **Net-chunk transport with public framing protocol.** 20-byte common
   header, 256-byte filename in chunk 0 only, CRC-32 session ID,
   SHA-256 verification on the receiver side. Public Python receiver
   in `tools/net-receive.py`.

3. **Block-storage sink as the Mode C primary output (deferred to
   follow-on task).** Sink interface committed; implementation lands
   in `TASK_BLOCK_SINK.md`.

4. **No FAT32 writeback in substrate scope.** Re-add as a separate
   amendment if Mode B becomes priority.

5. **No receive path, no retry/ack, no real-time progress streaming.**
   ForthOS is a one-way emitter. Reliability is "re-run on failure,"
   detected by the receiver's gap log.

---

## Spawned task docs

| Task doc                          | Status        | Owner                        |
|-----------------------------------|---------------|------------------------------|
| `TASK_NTFS_BULK_STREAM.md`        | Next up       | Claude Code, drafted by Claude Desktop |
| `TASK_NET_RECEIVER.md`            | After bulk    | Public repo, tools/          |
| `TASK_BLOCK_SINK.md`              | Future        | Spawns when Mode C scheduled |
| `TASK_FAT32_WRITE.md`             | Future        | Spawns if Mode B prioritized |

---

## Open questions to revisit after first validation

These are not blockers for `TASK_NTFS_BULK_STREAM.md`, but they're the
things to look at once data exists:

- **Drop rate on real transfers.** If gaps appear in the receiver log
  during real extraction runs, the no-retry decision needs revisiting.
- **MFT search latency.** 30 s/file is fine for hundreds, painful for
  tens of thousands. Index-acceleration belongs in its own task.
- **Partial-extraction resume.** If the HP reboots mid-extraction,
  what's the recovery story? Probably "re-run, skip files whose hash
  is already in the manifest," but that requires the manifest layer.
- **Mode C block-storage layout.** How many blocks of ForthOS storage
  do we reserve for extraction output? What's the manifest format?
  Owned by `TASK_BLOCK_SINK.md`.
