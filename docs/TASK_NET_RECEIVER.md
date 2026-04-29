# TASK: Network Chunk Receiver

## Purpose

Implement a Python UDP receiver that reassembles chunked binary
transfers from ForthOS into complete files on the dev machine.
This is the receiving end of the FBLK framing protocol defined in
`docs/2026-04-28-substrate-design.md` and sent by the Forth-side
`FILE-STREAM` word specified in `TASK_NTFS_BULK_STREAM.md`.

## Success criteria

1. New script `tools/net-receive.py` listens on UDP, parses FBLK
   headers, reassembles chunks into files, verifies SHA-256.
2. CLI: `python3 tools/net-receive.py [--port 6666] [--outdir ./extracted/]`
3. Outputs one JSON line per completed file to stdout (pipeable).
4. Detects and logs gaps (missing chunk indices).
5. Handles concurrent sessions (multiple files in flight).
6. Test suite validates parsing and reassembly without network I/O.
7. No external dependencies beyond Python stdlib + hashlib.

## CLI interface

```
python3 tools/net-receive.py [OPTIONS]

Options:
  --port PORT       UDP port to listen on (default: 6666)
  --outdir DIR      Directory for extracted files (default: ./extracted/)
  --timeout SECS    Stale session timeout (default: 30)
  --verbose         Print chunk-level progress
  --json-log FILE   Write JSON log to file (default: stdout)
```

## Packet format (received from ForthOS)

Common header (all packets, 20 bytes, big-endian):

```
Offset  Size  Field
------  ----  -----
0       4     Magic: 0x46424C4B ("FBLK")
4       4     Session ID
8       4     Total file size (bytes)
12      4     Chunk index (0-based)
16      2     Payload byte count
18      2     Flags: bit 0 = EOF, bit 1 = sparse
```

Chunk-0 supplement (after common header, before payload):

```
20      256   Filename (NUL-padded UTF-8)
```

Payload follows at offset 20 (chunks 1+) or 276 (chunk 0).

## Internal design

```python
@dataclass
class Session:
    session_id: int
    filename: str
    total_size: int
    received_chunks: dict[int, bytes]  # index -> payload
    max_chunk_seen: int
    last_activity: float  # time.time()
    complete: bool

sessions: dict[int, Session] = {}
```

### Reassembly logic

1. On each datagram: parse header, validate magic.
2. If session_id not in `sessions` and chunk_index == 0:
   create new Session, extract filename from chunk-0 supplement.
3. If session_id not in `sessions` and chunk_index != 0:
   log warning (missed chunk 0), buffer anyway with placeholder name.
4. Store payload in `received_chunks[chunk_index]`.
5. If EOF flag set OR total received bytes ≥ total_size:
   trigger reassembly.

### Reassembly

1. Sort chunks by index.
2. Detect gaps: any missing indices between 0 and max_chunk_seen.
3. Concatenate payloads in order.  Sparse-flagged chunks are zeros.
4. Truncate to total_size (last chunk may carry padding).
5. Compute SHA-256 of reassembled bytes.
6. Write to `<outdir>/<filename>`.
7. Emit JSON log line.

### JSON log format (one line per completed file)

```json
{
  "filename": "i8042prt.sys",
  "size": 118272,
  "sha256": "e1887a4e678b...",
  "chunks_received": 84,
  "chunks_expected": 84,
  "gaps": [],
  "duration_ms": 312,
  "session_id": "0x1a2b3c4d"
}
```

If gaps exist:
```json
{
  "filename": "serial.sys",
  "size": 90624,
  "sha256": null,
  "chunks_received": 62,
  "chunks_expected": 64,
  "gaps": [12, 47],
  "duration_ms": 245,
  "session_id": "0x5e6f7a8b",
  "status": "incomplete"
}
```

## What NOT to do

- **Do not send ACKs back to ForthOS.** No receive path exists.
- **Do not require any non-stdlib Python packages.**
- **Do not block indefinitely on one session.** Use the timeout to
  detect stale sessions and emit partial results.
- **Do not assume chunk ordering.** UDP can reorder — store by index,
  reassemble in order.
- **Do not overwrite existing files silently.** If `<filename>` exists
  in outdir, append `.1`, `.2`, etc.

## Testing

Unit tests in `tools/test_net_receive.py` exercise the parsing and
reassembly logic directly (no socket I/O needed):

1. `test_parse_header` — struct unpacking of 24-byte header
2. `test_parse_chunk0_filename` — filename extraction + NUL strip
3. `test_reassemble_small_file` — 3 chunks → correct bytes
4. `test_reassemble_with_gap` — gap detection and logging
5. `test_sha256_verification` — hash matches expected
6. `test_sparse_flag` — sparse chunks produce zeros
7. `test_concurrent_sessions` — two interleaved sessions
8. `test_eof_flag` — EOF triggers reassembly + cleanup

## Done criteria

- Receiver script runs, listens, reassembles.
- 8/8 unit tests pass.
- JSON log output is parseable (validated in tests).
- No external dependencies.
- Committed to public repo (`tools/net-receive.py`).
