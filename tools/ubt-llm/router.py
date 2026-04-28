#!/usr/bin/env python3
"""UBT LLM Format Router — deterministic binary classification.

Classifies binaries by format (PE32, PE32+, .NET, COM, INF, etc.) and
maps each to a prompt class for downstream LLM analysis.  No LLM calls
happen in this module — routing is purely magic-byte + pefile logic.

Usage:
    python3 router.py PATH [PATH ...]

Prints one JSON object per line (JSONL).
"""

import dataclasses
import hashlib
import json
import struct
import sys
from pathlib import Path

import pefile

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# IMAGE_FILE_HEADER.Machine values
_MACHINE_MAP = {
    0x014C: "i386",
    0x8664: "AMD64",
    0xAA64: "ARM64",
    0x0200: "IA64",
    0x01C0: "ARM",
    0x01C4: "ARMv7",
}

# IMAGE_OPTIONAL_HEADER.Subsystem values
_SUBSYSTEM_NATIVE = 1
_SUBSYSTEM_WINDOWS_GUI = 2
_SUBSYSTEM_WINDOWS_CUI = 3

# IMAGE_FILE_HEADER.Characteristics
_IMAGE_FILE_DLL = 0x2000

# Extensions that indicate a user-mode DLL regardless of characteristics
_DLL_EXTENSIONS = {".dll", ".ocx", ".ax", ".cpl"}

# Maximum .COM file size (64KB - 256 bytes for PSP)
_MAX_COM_SIZE = 65280


# ---------------------------------------------------------------------------
# RouteDecision
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class RouteDecision:
    """Classification result for a single binary."""

    path: str
    sha256: str
    format: str        # PE32|PE32_PLUS|DOTNET|MZ_ONLY|NE|LE|LX|COM|INF|MUI|PARSE_ERROR|UNKNOWN
    machine: str | None
    subsystem: int | None
    is_dotnet: bool
    prompt_class: str  # sys_driver|user_dll|exe|com_dos|dotnet|mui|inf|unknown
    reason: str | None  # error string when format=PARSE_ERROR

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _sha256_file(path: Path) -> str:
    """Compute SHA256 of file contents without loading entire file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def _check_inf(path: Path) -> bool:
    """Check if file is an INF (text with [Version] section in first 2KB)."""
    try:
        with open(path, "rb") as f:
            head = f.read(2048)
        # Try decoding as text — INF files are ASCII/Latin-1
        try:
            text = head.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = head.decode("latin-1")
            except UnicodeDecodeError:
                return False
        # Look for [Version] section header (case-insensitive)
        return "[version]" in text.lower()
    except OSError:
        return False


def _check_mui(pe: pefile.PE) -> bool:
    """Check for MUI signature in resource directory AND no executable code.

    A true MUI file has a top-level resource entry named "MUI" AND
    contains no executable code sections.  Regular drivers often have
    MUI resources for localization but are NOT MUI-only binaries.

    NOTE: Untested against real MUI files — no fixture available.
    Re-validate when a real .mui binary becomes available for testing.
    """
    if not hasattr(pe, "DIRECTORY_ENTRY_RESOURCE"):
        return False
    has_mui_resource = False
    for entry in pe.DIRECTORY_ENTRY_RESOURCE.entries:
        if entry.name is not None and str(entry.name) == "MUI":
            has_mui_resource = True
            break
    if not has_mui_resource:
        return False
    # A real MUI file has no executable sections (IMAGE_SCN_MEM_EXECUTE)
    for section in pe.sections:
        if section.Characteristics & 0x20000000:
            return False
    return True


def _classify_pe(pe: pefile.PE, ext: str) -> tuple[str, str, str | None, int | None, bool]:
    """Classify a confirmed PE binary.

    Returns: (format, prompt_class, machine, subsystem, is_dotnet)
    """
    # Check .NET (COR20 directory)
    cor20 = pe.OPTIONAL_HEADER.DATA_DIRECTORY[14]
    if cor20.VirtualAddress != 0:
        machine = _MACHINE_MAP.get(pe.FILE_HEADER.Machine)
        subsystem = pe.OPTIONAL_HEADER.Subsystem
        return "DOTNET", "dotnet", machine, subsystem, True

    # Check MUI
    if _check_mui(pe):
        machine = _MACHINE_MAP.get(pe.FILE_HEADER.Machine)
        subsystem = pe.OPTIONAL_HEADER.Subsystem
        return "MUI", "mui", machine, subsystem, False

    # Determine PE type
    if pe.OPTIONAL_HEADER.Magic == 0x20B:
        fmt = "PE32_PLUS"
    else:
        fmt = "PE32"

    machine = _MACHINE_MAP.get(pe.FILE_HEADER.Machine)
    subsystem = pe.OPTIONAL_HEADER.Subsystem
    characteristics = pe.FILE_HEADER.Characteristics
    is_dll = bool(characteristics & _IMAGE_FILE_DLL)

    # Map to prompt class
    if subsystem == _SUBSYSTEM_NATIVE:
        # NATIVE + (.sys extension OR DLL characteristic) → sys_driver
        # NATIVE without those → exe (e.g. smss.exe)
        if ext == ".sys" or is_dll:
            prompt_class = "sys_driver"
        else:
            prompt_class = "exe"
    elif is_dll or ext in _DLL_EXTENSIONS:
        prompt_class = "user_dll"
    elif subsystem in (_SUBSYSTEM_WINDOWS_GUI, _SUBSYSTEM_WINDOWS_CUI):
        prompt_class = "exe"
    else:
        prompt_class = "unknown"

    return fmt, prompt_class, machine, subsystem, False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def route(path: Path) -> RouteDecision:
    """Classify a binary file and return its routing decision."""
    path = Path(path)
    ext = path.suffix.lower()

    # Compute SHA256
    try:
        sha = _sha256_file(path)
    except OSError as e:
        return RouteDecision(
            path=str(path), sha256="", format="PARSE_ERROR",
            machine=None, subsystem=None, is_dotnet=False,
            prompt_class="unknown", reason=str(e),
        )

    # Read header bytes
    try:
        with open(path, "rb") as f:
            header = f.read(256)
    except OSError as e:
        return RouteDecision(
            path=str(path), sha256=sha, format="PARSE_ERROR",
            machine=None, subsystem=None, is_dotnet=False,
            prompt_class="unknown", reason=str(e),
        )

    if len(header) < 2:
        return RouteDecision(
            path=str(path), sha256=sha, format="UNKNOWN",
            machine=None, subsystem=None, is_dotnet=False,
            prompt_class="unknown", reason=None,
        )

    # Step 1: Check for MZ magic
    if header[:2] != b"MZ":
        # Not MZ — could be .COM, INF, or unknown
        file_size = path.stat().st_size
        if ext == ".com" and file_size <= _MAX_COM_SIZE:
            return RouteDecision(
                path=str(path), sha256=sha, format="COM",
                machine="i386", subsystem=None, is_dotnet=False,
                prompt_class="com_dos", reason=None,
            )
        if _check_inf(path):
            return RouteDecision(
                path=str(path), sha256=sha, format="INF",
                machine=None, subsystem=None, is_dotnet=False,
                prompt_class="inf", reason=None,
            )
        return RouteDecision(
            path=str(path), sha256=sha, format="UNKNOWN",
            machine=None, subsystem=None, is_dotnet=False,
            prompt_class="unknown", reason=None,
        )

    # Step 2: Has MZ — read e_lfanew and check signature
    if len(header) < 0x40:
        return RouteDecision(
            path=str(path), sha256=sha, format="MZ_ONLY",
            machine=None, subsystem=None, is_dotnet=False,
            prompt_class="com_dos", reason=None,
        )

    e_lfanew = struct.unpack_from("<I", header, 0x3C)[0]

    # Read signature at e_lfanew (may need to seek beyond initial 256 bytes)
    try:
        with open(path, "rb") as f:
            f.seek(e_lfanew)
            sig = f.read(4)
    except OSError as e:
        return RouteDecision(
            path=str(path), sha256=sha, format="PARSE_ERROR",
            machine=None, subsystem=None, is_dotnet=False,
            prompt_class="unknown", reason=str(e),
        )

    if len(sig) < 2:
        return RouteDecision(
            path=str(path), sha256=sha, format="MZ_ONLY",
            machine=None, subsystem=None, is_dotnet=False,
            prompt_class="com_dos", reason=None,
        )

    # Check for NE/LE/LX signatures (2 bytes)
    sig2 = sig[:2]
    if sig2 == b"NE":
        return RouteDecision(
            path=str(path), sha256=sha, format="NE",
            machine=None, subsystem=None, is_dotnet=False,
            prompt_class="unknown", reason=None,
        )
    if sig2 == b"LE":
        return RouteDecision(
            path=str(path), sha256=sha, format="LE",
            machine=None, subsystem=None, is_dotnet=False,
            prompt_class="unknown", reason=None,
        )
    if sig2 == b"LX":
        return RouteDecision(
            path=str(path), sha256=sha, format="LX",
            machine=None, subsystem=None, is_dotnet=False,
            prompt_class="unknown", reason=None,
        )

    # Check for PE signature
    if sig != b"PE\x00\x00":
        return RouteDecision(
            path=str(path), sha256=sha, format="MZ_ONLY",
            machine=None, subsystem=None, is_dotnet=False,
            prompt_class="com_dos", reason=None,
        )

    # Step 3: PE signature confirmed — use pefile for detailed parsing
    try:
        pe = pefile.PE(str(path), fast_load=True)
        pe.parse_data_directories(
            directories=[
                pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_COM_DESCRIPTOR"],
                pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_RESOURCE"],
            ]
        )
    except Exception as e:
        return RouteDecision(
            path=str(path), sha256=sha, format="PARSE_ERROR",
            machine=None, subsystem=None, is_dotnet=False,
            prompt_class="unknown", reason=f"pefile: {e}",
        )

    try:
        fmt, prompt_class, machine, subsystem, is_dotnet = _classify_pe(pe, ext)
    except Exception as e:
        pe.close()
        return RouteDecision(
            path=str(path), sha256=sha, format="PARSE_ERROR",
            machine=None, subsystem=None, is_dotnet=False,
            prompt_class="unknown", reason=f"classify: {e}",
        )

    pe.close()
    return RouteDecision(
        path=str(path), sha256=sha, format=fmt,
        machine=machine, subsystem=subsystem, is_dotnet=is_dotnet,
        prompt_class=prompt_class, reason=None,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} PATH [PATH ...]", file=sys.stderr)
        sys.exit(1)

    for arg in sys.argv[1:]:
        result = route(Path(arg))
        print(json.dumps(result.to_dict()))


if __name__ == "__main__":
    main()
