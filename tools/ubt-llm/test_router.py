#!/usr/bin/env python3
"""Tests for the UBT LLM format router."""

import struct
import tempfile
from pathlib import Path

import pytest

from router import RouteDecision, route

# ---------------------------------------------------------------------------
# Paths to real fixtures
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
HP_I3 = PROJECT_ROOT / "tests" / "hp_i3"
TRANSLATOR_DATA = PROJECT_ROOT / "tools" / "translator" / "tests" / "data"
FIXTURES = PROJECT_ROOT / "tests" / "fixtures"


# ---------------------------------------------------------------------------
# PE32+ sys_driver (Win10 x64 kernel drivers)
# ---------------------------------------------------------------------------

class TestPE32Plus:
    def test_i8042prt_sys(self):
        r = route(HP_I3 / "i8042prt.sys")
        assert r.format == "PE32_PLUS"
        assert r.machine == "AMD64"
        assert r.subsystem == 1  # NATIVE
        assert r.prompt_class == "sys_driver"
        assert r.is_dotnet is False
        assert r.reason is None

    def test_serial_sys(self):
        r = route(HP_I3 / "serial.sys")
        assert r.format == "PE32_PLUS"
        assert r.prompt_class == "sys_driver"


# ---------------------------------------------------------------------------
# PE32 sys_driver (32-bit kernel drivers)
# ---------------------------------------------------------------------------

class TestPE32:
    def test_serial_sys_32bit(self):
        r = route(TRANSLATOR_DATA / "serial.sys")
        assert r.format == "PE32"
        assert r.machine == "i386"
        assert r.subsystem == 1  # NATIVE
        assert r.prompt_class == "sys_driver"

    def test_beep_sys_dll_flag(self):
        """beep.sys has DLL flag set — should still route to sys_driver."""
        r = route(TRANSLATOR_DATA / "beep.sys")
        assert r.format == "PE32"
        assert r.prompt_class == "sys_driver"


# ---------------------------------------------------------------------------
# .NET detection
# ---------------------------------------------------------------------------

class TestDotNet:
    def test_dotnet_dll(self):
        r = route(FIXTURES / "test_dotnet.dll")
        assert r.format == "DOTNET"
        assert r.is_dotnet is True
        assert r.prompt_class == "dotnet"
        assert r.machine == "i386"


# ---------------------------------------------------------------------------
# .COM file
# ---------------------------------------------------------------------------

class TestCom:
    def test_port_access_com(self):
        r = route(FIXTURES / "test_port_access.com")
        assert r.format == "COM"
        assert r.prompt_class == "com_dos"
        assert r.machine == "i386"

    def test_large_com_rejected(self):
        """A .com file larger than 65280 bytes is not a valid COM."""
        with tempfile.NamedTemporaryFile(suffix=".com", delete=False) as f:
            f.write(b"\x90" * 70000)
            f.flush()
            r = route(Path(f.name))
        assert r.format == "UNKNOWN"
        assert r.prompt_class == "unknown"


# ---------------------------------------------------------------------------
# INF detection
# ---------------------------------------------------------------------------

class TestInf:
    def test_inf_with_version_section(self):
        content = b";\r\n; Sample driver INF\r\n;\r\n[Version]\r\nClass=Net\r\nClassGuid={123}\r\n"
        with tempfile.NamedTemporaryFile(suffix=".inf", delete=False) as f:
            f.write(content)
            f.flush()
            r = route(Path(f.name))
        assert r.format == "INF"
        assert r.prompt_class == "inf"

    def test_text_without_version_is_unknown(self):
        content = b"This is just a text file with no INF structure.\n"
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(content)
            f.flush()
            r = route(Path(f.name))
        assert r.format == "UNKNOWN"
        assert r.prompt_class == "unknown"


# ---------------------------------------------------------------------------
# MZ-only (DOS EXE with no PE/NE/LE header)
# ---------------------------------------------------------------------------

class TestMzOnly:
    def test_mz_stub_no_pe(self):
        """MZ header with e_lfanew pointing to garbage (no PE signature)."""
        stub = bytearray(256)
        stub[0:2] = b"MZ"
        # e_lfanew points to offset 0x80
        struct.pack_into("<I", stub, 0x3C, 0x80)
        # Put garbage at 0x80 (not PE/NE/LE/LX)
        stub[0x80:0x84] = b"\x00\x00\x00\x00"
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            f.write(bytes(stub))
            f.flush()
            r = route(Path(f.name))
        assert r.format == "MZ_ONLY"
        assert r.prompt_class == "com_dos"


# ---------------------------------------------------------------------------
# NE / LE / LX signatures
# ---------------------------------------------------------------------------

class TestLegacyFormats:
    def _make_mz_with_sig(self, sig: bytes, ext: str = ".exe") -> RouteDecision:
        stub = bytearray(256)
        stub[0:2] = b"MZ"
        struct.pack_into("<I", stub, 0x3C, 0x80)
        stub[0x80:0x80 + len(sig)] = sig
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
            f.write(bytes(stub))
            f.flush()
            return route(Path(f.name))

    def test_ne_format(self):
        r = self._make_mz_with_sig(b"NE")
        assert r.format == "NE"
        assert r.prompt_class == "unknown"

    def test_le_format(self):
        r = self._make_mz_with_sig(b"LE")
        assert r.format == "LE"
        assert r.prompt_class == "unknown"

    def test_lx_format(self):
        r = self._make_mz_with_sig(b"LX")
        assert r.format == "LX"
        assert r.prompt_class == "unknown"


# ---------------------------------------------------------------------------
# MUI (negative-only — no real fixture available)
# ---------------------------------------------------------------------------

class TestMui:
    def test_normal_pe_is_not_mui(self):
        """A standard .sys PE should not be classified as MUI."""
        r = route(HP_I3 / "i8042prt.sys")
        assert r.format != "MUI"
        assert r.prompt_class != "mui"


# ---------------------------------------------------------------------------
# PARSE_ERROR and edge cases
# ---------------------------------------------------------------------------

class TestParseError:
    def test_truncated_file(self):
        """A 1-byte file should return UNKNOWN (too short for any format)."""
        with tempfile.NamedTemporaryFile(suffix=".sys", delete=False) as f:
            f.write(b"\x00")
            f.flush()
            r = route(Path(f.name))
        assert r.format == "UNKNOWN"

    def test_nonexistent_file(self):
        r = route(Path("/nonexistent/binary.sys"))
        assert r.format == "PARSE_ERROR"
        assert r.reason is not None


# ---------------------------------------------------------------------------
# SHA256 determinism
# ---------------------------------------------------------------------------

class TestSha256:
    def test_same_file_same_hash(self):
        r1 = route(HP_I3 / "i8042prt.sys")
        r2 = route(HP_I3 / "i8042prt.sys")
        assert r1.sha256 == r2.sha256
        assert len(r1.sha256) == 64


# ---------------------------------------------------------------------------
# NATIVE subsystem without .sys or DLL flag → exe
# ---------------------------------------------------------------------------

class TestNativeExe:
    def test_native_exe_not_sys_driver(self):
        """NATIVE subsystem + .exe extension + no DLL flag → exe, not sys_driver."""
        # Build a minimal PE32 with correct field offsets:
        # PE sig at 0x80, FILE_HEADER at 0x84 (20 bytes), OPT_HEADER at 0x98
        stub = bytearray(512)
        stub[0:2] = b"MZ"
        struct.pack_into("<I", stub, 0x3C, 0x80)   # e_lfanew
        stub[0x80:0x84] = b"PE\x00\x00"           # PE signature
        # IMAGE_FILE_HEADER (20 bytes at 0x84)
        struct.pack_into("<H", stub, 0x84, 0x014C) # Machine = i386
        struct.pack_into("<H", stub, 0x86, 0)      # NumberOfSections = 0
        struct.pack_into("<I", stub, 0x88, 0)      # TimeDateStamp
        struct.pack_into("<I", stub, 0x8C, 0)      # PointerToSymbolTable
        struct.pack_into("<I", stub, 0x90, 0)      # NumberOfSymbols
        struct.pack_into("<H", stub, 0x94, 0x00E0) # SizeOfOptionalHeader (224)
        struct.pack_into("<H", stub, 0x96, 0x0002) # Characteristics = EXECUTABLE_IMAGE
        # IMAGE_OPTIONAL_HEADER (at 0x98)
        struct.pack_into("<H", stub, 0x98, 0x010B) # Magic = PE32
        struct.pack_into("<I", stub, 0x98 + 28, 0x00400000)  # ImageBase
        struct.pack_into("<I", stub, 0x98 + 32, 0x1000)  # SectionAlignment
        struct.pack_into("<I", stub, 0x98 + 36, 0x0200)  # FileAlignment
        struct.pack_into("<I", stub, 0x98 + 56, 0x1000)  # SizeOfImage
        struct.pack_into("<I", stub, 0x98 + 60, 0x0200)  # SizeOfHeaders
        struct.pack_into("<H", stub, 0x98 + 68, 1)       # Subsystem = NATIVE
        struct.pack_into("<I", stub, 0x98 + 92, 16)      # NumberOfRvaAndSizes
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            f.write(bytes(stub))
            f.flush()
            r = route(Path(f.name))
        assert r.prompt_class == "exe"
        assert r.format == "PE32"


# ---------------------------------------------------------------------------
# Non-binary text file (README)
# ---------------------------------------------------------------------------

class TestNonBinary:
    def test_readme_is_unknown(self):
        readme = Path(__file__).resolve().parent / "README.md"
        if readme.exists():
            r = route(readme)
            assert r.format == "UNKNOWN"
            assert r.prompt_class == "unknown"
