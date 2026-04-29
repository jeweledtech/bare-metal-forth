#!/usr/bin/env python3
"""Tests for the ForthOS FBLK chunk receiver.

Tests parsing and reassembly logic directly — no socket I/O needed.
"""

import hashlib
import json
import struct
import tempfile
from pathlib import Path

import pytest

# Import from sibling module
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))

from importlib.machinery import SourceFileLoader
# net-receive.py has a hyphen, so import by path
_loader = SourceFileLoader("net_receive", str(Path(__file__).resolve().parent / "net-receive.py"))
net_receive = _loader.load_module()

parse_header = net_receive.parse_header
parse_chunk0_filename = net_receive.parse_chunk0_filename
extract_payload = net_receive.extract_payload
reassemble = net_receive.reassemble
finalize_session = net_receive.finalize_session
Session = net_receive.Session
FBLK_MAGIC = net_receive.FBLK_MAGIC
HEADER_SIZE = net_receive.HEADER_SIZE
HEADER_STRUCT = net_receive.HEADER_STRUCT
FILENAME_SIZE = net_receive.FILENAME_SIZE
FLAG_EOF = net_receive.FLAG_EOF
FLAG_SPARSE = net_receive.FLAG_SPARSE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def build_header(session_id: int, total_size: int, chunk_index: int,
                 payload_len: int, flags: int = 0) -> bytes:
    """Build a 24-byte FBLK common header."""
    return HEADER_STRUCT.pack(
        FBLK_MAGIC, session_id, total_size, chunk_index, payload_len, flags
    )


def build_chunk0(session_id: int, total_size: int, filename: str,
                 payload: bytes) -> bytes:
    """Build a complete chunk-0 datagram."""
    header = build_header(session_id, total_size, 0, len(payload), 0)
    name_bytes = filename.encode("utf-8")[:255].ljust(FILENAME_SIZE, b"\x00")
    return header + name_bytes + payload


def build_chunk(session_id: int, total_size: int, chunk_index: int,
                payload: bytes, flags: int = 0) -> bytes:
    """Build a chunk N>0 datagram."""
    header = build_header(session_id, total_size, chunk_index, len(payload), flags)
    return header + payload


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestParseHeader:
    def test_valid_header(self):
        data = build_header(0x12345678, 1024, 5, 512, 0)
        result = parse_header(data)
        assert result is not None
        assert result["session_id"] == 0x12345678
        assert result["total_size"] == 1024
        assert result["chunk_index"] == 5
        assert result["payload_len"] == 512
        assert result["flags"] == 0
        assert result["eof"] is False
        assert result["sparse"] is False

    def test_eof_flag(self):
        data = build_header(0xAABBCCDD, 2048, 10, 256, FLAG_EOF)
        result = parse_header(data)
        assert result["eof"] is True
        assert result["sparse"] is False

    def test_invalid_magic(self):
        data = struct.pack(">IIIIHH", 0xDEADBEEF, 1, 100, 0, 50, 0)
        assert parse_header(data) is None

    def test_too_short(self):
        assert parse_header(b"\x00" * 10) is None


class TestParseChunk0Filename:
    def test_basic_filename(self):
        data = build_chunk0(1, 100, "i8042prt.sys", b"\x00" * 50)
        filename = parse_chunk0_filename(data)
        assert filename == "i8042prt.sys"

    def test_nul_padded(self):
        data = build_chunk0(1, 100, "test.dll", b"\x00" * 50)
        filename = parse_chunk0_filename(data)
        assert filename == "test.dll"
        assert "\x00" not in filename

    def test_max_length_filename(self):
        long_name = "a" * 255
        data = build_chunk0(1, 100, long_name, b"")
        filename = parse_chunk0_filename(data)
        assert filename == long_name


class TestReassembleSmallFile:
    def test_three_chunks(self):
        """3 chunks of data reassemble into correct bytes."""
        payload0 = b"AAAA" * 100  # 400 bytes
        payload1 = b"BBBB" * 100  # 400 bytes
        payload2 = b"CC" * 100    # 200 bytes
        total_size = 1000

        session = Session(
            session_id=0x11111111,
            filename="test.bin",
            total_size=total_size,
        )
        session.received_chunks = {0: payload0, 1: payload1, 2: payload2}
        session.max_chunk_seen = 2

        result, gaps = reassemble(session)
        assert gaps == []
        assert len(result) == total_size
        assert result == payload0 + payload1 + payload2


class TestReassembleWithGap:
    def test_missing_chunk_detected(self):
        """Missing chunk index produces a gap entry."""
        session = Session(
            session_id=0x22222222,
            filename="gapped.sys",
            total_size=3000,
        )
        # Chunks 0, 1, 3 present — chunk 2 missing
        session.received_chunks = {
            0: b"A" * 1000,
            1: b"B" * 1000,
            3: b"D" * 1000,
        }
        session.max_chunk_seen = 3

        result, gaps = reassemble(session)
        assert gaps == [2]
        # Chunk 2 is empty (gap fill)
        assert b"A" * 1000 in result
        assert b"B" * 1000 in result
        assert b"D" * 1000 in result


class TestSha256Verification:
    def test_correct_hash(self):
        """Reassembled file has correct SHA-256."""
        content = b"Hello from ForthOS! " * 50  # 1000 bytes
        expected_hash = hashlib.sha256(content).hexdigest()

        session = Session(
            session_id=0x33333333,
            filename="hello.bin",
            total_size=len(content),
        )
        # Split into 3 chunks
        session.received_chunks = {
            0: content[:400],
            1: content[400:800],
            2: content[800:],
        }
        session.max_chunk_seen = 2

        with tempfile.TemporaryDirectory() as tmpdir:
            log_entry = finalize_session(session, Path(tmpdir))
            assert log_entry["sha256"] == expected_hash
            assert log_entry["status"] == "complete"
            # Verify file was written
            written = (Path(tmpdir) / "hello.bin").read_bytes()
            assert written == content


class TestSparseFlag:
    def test_sparse_chunks_are_zeros(self):
        """Sparse-flagged chunks should be stored as zeros by caller."""
        # Simulate what the receiver does: sparse payload = zeros
        session = Session(
            session_id=0x44444444,
            filename="sparse.bin",
            total_size=3000,
        )
        session.received_chunks = {
            0: b"A" * 1000,
            1: b"\x00" * 1000,  # sparse chunk stored as zeros by receiver
            2: b"C" * 1000,
        }
        session.max_chunk_seen = 2

        result, gaps = reassemble(session)
        assert gaps == []
        assert result[0:1000] == b"A" * 1000
        assert result[1000:2000] == b"\x00" * 1000
        assert result[2000:3000] == b"C" * 1000


class TestConcurrentSessions:
    def test_two_sessions_interleaved(self):
        """Two sessions with different IDs reassemble independently."""
        session_a = Session(
            session_id=0xAAAAAAAA,
            filename="file_a.sys",
            total_size=500,
        )
        session_a.received_chunks = {0: b"A" * 500}
        session_a.max_chunk_seen = 0

        session_b = Session(
            session_id=0xBBBBBBBB,
            filename="file_b.dll",
            total_size=300,
        )
        session_b.received_chunks = {0: b"B" * 300}
        session_b.max_chunk_seen = 0

        with tempfile.TemporaryDirectory() as tmpdir:
            outdir = Path(tmpdir)
            log_a = finalize_session(session_a, outdir)
            log_b = finalize_session(session_b, outdir)

            assert log_a["filename"] == "file_a.sys"
            assert log_a["size"] == 500
            assert log_b["filename"] == "file_b.dll"
            assert log_b["size"] == 300

            # Both files written
            assert (outdir / "file_a.sys").exists()
            assert (outdir / "file_b.dll").exists()


class TestEofFlag:
    def test_eof_triggers_completion(self):
        """EOF flag in header indicates final chunk."""
        header = build_header(0x55555555, 100, 2, 34, FLAG_EOF)
        result = parse_header(header)
        assert result["eof"] is True
        assert result["chunk_index"] == 2

    def test_finalize_marks_complete(self):
        """Finalized session with all chunks has status=complete."""
        session = Session(
            session_id=0x66666666,
            filename="complete.bin",
            total_size=100,
        )
        session.received_chunks = {0: b"X" * 100}
        session.max_chunk_seen = 0

        with tempfile.TemporaryDirectory() as tmpdir:
            log_entry = finalize_session(session, Path(tmpdir))
            assert log_entry["status"] == "complete"
            assert log_entry["gaps"] == []
            assert log_entry["sha256"] is not None
