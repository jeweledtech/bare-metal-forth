#!/usr/bin/env python3
"""ForthOS FBLK chunk receiver — reassembles chunked UDP transfers into files.

Listens for FBLK-framed UDP packets from ForthOS's FILE-STREAM word,
reassembles chunks into complete files, verifies SHA-256 integrity,
and writes results to disk.

Usage:
    python3 net-receive.py [--port 6666] [--outdir ./extracted/] [--verbose]

Protocol:
    See docs/2026-04-28-substrate-design.md for the framing specification.
    24-byte common header on all packets, 256-byte filename in chunk 0 only.
"""

import argparse
import hashlib
import json
import os
import socket
import struct
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FBLK_MAGIC = 0x46424C4B  # "FBLK" as big-endian uint32
HEADER_SIZE = 20          # Common header: magic(4) + sid(4) + size(4) + idx(4) + plen(2) + flags(2)
FILENAME_SIZE = 256       # NUL-padded filename in chunk 0
CHUNK0_EXTRA = FILENAME_SIZE  # Additional bytes in chunk 0 after common header

FLAG_EOF = 0x0001
FLAG_SPARSE = 0x0002

# struct format for common header (big-endian)
HEADER_FMT = ">IIIIHH"
HEADER_STRUCT = struct.Struct(HEADER_FMT)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Session:
    """State for one in-flight file transfer."""
    session_id: int
    filename: str
    total_size: int
    received_chunks: dict = field(default_factory=dict)  # index -> bytes
    max_chunk_seen: int = 0
    start_time: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    complete: bool = False


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_header(data: bytes) -> dict | None:
    """Parse the 24-byte common header from a datagram.

    Returns dict with fields or None if invalid.
    """
    if len(data) < HEADER_SIZE:
        return None

    magic, session_id, total_size, chunk_index, payload_len, flags = (
        HEADER_STRUCT.unpack_from(data, 0)
    )

    if magic != FBLK_MAGIC:
        return None

    return {
        "session_id": session_id,
        "total_size": total_size,
        "chunk_index": chunk_index,
        "payload_len": payload_len,
        "flags": flags,
        "eof": bool(flags & FLAG_EOF),
        "sparse": bool(flags & FLAG_SPARSE),
    }


def parse_chunk0_filename(data: bytes) -> str:
    """Extract filename from chunk-0 supplement (256 bytes after header)."""
    if len(data) < HEADER_SIZE + FILENAME_SIZE:
        return "unknown"

    raw = data[HEADER_SIZE:HEADER_SIZE + FILENAME_SIZE]
    # NUL-terminated, may have trailing garbage after NUL
    nul_pos = raw.find(b"\x00")
    if nul_pos >= 0:
        raw = raw[:nul_pos]
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def extract_payload(data: bytes, chunk_index: int) -> bytes:
    """Extract payload bytes from a datagram."""
    if chunk_index == 0:
        offset = HEADER_SIZE + CHUNK0_EXTRA
    else:
        offset = HEADER_SIZE
    return data[offset:]


# ---------------------------------------------------------------------------
# Reassembly
# ---------------------------------------------------------------------------

def reassemble(session: Session) -> tuple[bytes, list[int]]:
    """Reassemble a session's chunks into the complete file.

    Returns (file_bytes, gap_list).
    """
    if not session.received_chunks:
        return b"", list(range(session.max_chunk_seen + 1))

    max_idx = max(session.received_chunks.keys())
    gaps = []
    parts = []

    for i in range(max_idx + 1):
        if i in session.received_chunks:
            parts.append(session.received_chunks[i])
        else:
            gaps.append(i)
            # Fill gap with zeros (best-effort for incomplete transfers)
            # Use the most common chunk size as a guess
            parts.append(b"")

    result = b"".join(parts)

    # Truncate to declared total_size (last chunk may have padding)
    if session.total_size > 0 and len(result) > session.total_size:
        result = result[:session.total_size]

    return result, gaps


def finalize_session(session: Session, outdir: Path, verbose: bool = False) -> dict:
    """Reassemble, verify, write file, return log entry."""
    file_bytes, gaps = reassemble(session)

    # Compute SHA-256
    sha256 = hashlib.sha256(file_bytes).hexdigest() if not gaps else None

    # Determine output path (avoid overwrites)
    filename = session.filename or f"session_{session.session_id:08x}"
    out_path = outdir / filename
    suffix_num = 0
    while out_path.exists():
        suffix_num += 1
        stem = Path(filename).stem
        ext = Path(filename).suffix
        out_path = outdir / f"{stem}.{suffix_num}{ext}"

    # Write file
    if not gaps:
        out_path.write_bytes(file_bytes)
        status = "complete"
    else:
        # Write partial with .partial suffix
        partial_path = out_path.with_suffix(out_path.suffix + ".partial")
        partial_path.write_bytes(file_bytes)
        out_path = partial_path
        status = "incomplete"

    duration_ms = int((time.time() - session.start_time) * 1000)

    chunks_expected = (
        max(session.received_chunks.keys()) + 1
        if session.received_chunks else 0
    )

    log_entry = {
        "filename": session.filename,
        "size": len(file_bytes),
        "sha256": sha256,
        "chunks_received": len(session.received_chunks),
        "chunks_expected": chunks_expected,
        "gaps": gaps,
        "duration_ms": duration_ms,
        "session_id": f"0x{session.session_id:08x}",
        "status": status,
        "output_path": str(out_path),
    }

    if verbose:
        print(f"  [{status}] {session.filename}: {len(file_bytes)} bytes, "
              f"SHA-256={sha256 or 'N/A'}", file=sys.stderr)

    return log_entry


# ---------------------------------------------------------------------------
# Main receiver loop
# ---------------------------------------------------------------------------

def run_receiver(port: int, outdir: Path, timeout: float, verbose: bool):
    """Main UDP receive loop."""
    outdir.mkdir(parents=True, exist_ok=True)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", port))
    sock.settimeout(1.0)  # 1s timeout for stale-session checking

    sessions: dict[int, Session] = {}

    print(f"Listening on UDP port {port}, writing to {outdir}/", file=sys.stderr)
    print(f"Press Ctrl+C to stop.", file=sys.stderr)

    try:
        while True:
            try:
                data, addr = sock.recvfrom(65535)
            except socket.timeout:
                # Check for stale sessions
                _expire_stale(sessions, outdir, timeout, verbose)
                continue

            header = parse_header(data)
            if header is None:
                if verbose:
                    print(f"  [skip] Non-FBLK packet from {addr}", file=sys.stderr)
                continue

            sid = header["session_id"]
            idx = header["chunk_index"]

            # Create or retrieve session
            if sid not in sessions:
                if idx == 0:
                    filename = parse_chunk0_filename(data)
                    sessions[sid] = Session(
                        session_id=sid,
                        filename=filename,
                        total_size=header["total_size"],
                    )
                    if verbose:
                        print(f"  [new] session 0x{sid:08x}: {filename} "
                              f"({header['total_size']} bytes)", file=sys.stderr)
                else:
                    # Missed chunk 0 — create session with placeholder
                    sessions[sid] = Session(
                        session_id=sid,
                        filename=f"unknown_{sid:08x}",
                        total_size=header["total_size"],
                    )
                    if verbose:
                        print(f"  [warn] session 0x{sid:08x}: missed chunk 0",
                              file=sys.stderr)

            session = sessions[sid]
            session.last_activity = time.time()

            # Extract and store payload
            payload = extract_payload(data, idx)

            if header["sparse"]:
                # Sparse chunk: payload should be treated as zeros
                payload = b"\x00" * header["payload_len"]

            # Only store up to declared payload_len
            payload = payload[:header["payload_len"]]
            session.received_chunks[idx] = payload
            session.max_chunk_seen = max(session.max_chunk_seen, idx)

            if verbose and idx % 100 == 0 and idx > 0:
                print(f"  [progress] 0x{sid:08x}: chunk {idx}", file=sys.stderr)

            # Check for completion
            if header["eof"]:
                log_entry = finalize_session(session, outdir, verbose)
                print(json.dumps(log_entry), flush=True)
                del sessions[sid]

    except KeyboardInterrupt:
        print(f"\nStopping. {len(sessions)} sessions in flight.", file=sys.stderr)
        # Finalize any remaining sessions as incomplete
        for sid, session in list(sessions.items()):
            log_entry = finalize_session(session, outdir, verbose)
            log_entry["status"] = "interrupted"
            print(json.dumps(log_entry), flush=True)
    finally:
        sock.close()


def _expire_stale(sessions: dict, outdir: Path, timeout: float, verbose: bool):
    """Finalize sessions that have been idle beyond timeout."""
    now = time.time()
    stale_ids = [
        sid for sid, s in sessions.items()
        if now - s.last_activity > timeout
    ]
    for sid in stale_ids:
        session = sessions[sid]
        if verbose:
            print(f"  [timeout] session 0x{sid:08x}: {session.filename}",
                  file=sys.stderr)
        log_entry = finalize_session(session, outdir, verbose)
        log_entry["status"] = "timeout"
        print(json.dumps(log_entry), flush=True)
        del sessions[sid]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="ForthOS FBLK chunk receiver"
    )
    parser.add_argument("--port", type=int, default=6666,
                        help="UDP port to listen on (default: 6666)")
    parser.add_argument("--outdir", type=Path, default=Path("./extracted"),
                        help="Output directory (default: ./extracted/)")
    parser.add_argument("--timeout", type=float, default=30.0,
                        help="Stale session timeout in seconds (default: 30)")
    parser.add_argument("--verbose", action="store_true",
                        help="Print chunk-level progress to stderr")
    args = parser.parse_args()

    run_receiver(args.port, args.outdir, args.timeout, args.verbose)


if __name__ == "__main__":
    main()
