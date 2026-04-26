#!/usr/bin/env python3
"""Heuristic prefilter for UBT LLM classification pipeline.

Inspects each function's disassembly for hardware-I/O signals before
calling the LLM.  Functions with no signal are auto-classified as OTHER
at zero token cost.

The prefilter is conservative: false positives (sending non-hardware
functions to the LLM) are cheap; false negatives (skipping HARDWARE_IO
functions) are unacceptable.

**Parallel-state caveat:** This module stores IAT data in module-level
variables set by ``init()``.  It is NOT safe to call ``init()`` for two
different binaries concurrently in the same process.  Each ``init()``
call overwrites the previous binary's state.  If parallel-binary
analysis is needed in the future, refactor the state into a context
object passed to ``should_call_llm()``.
"""

import re
from pathlib import Path

import pefile

# ---------------------------------------------------------------------------
# Module-level state (set by init, read by should_call_llm)
# ---------------------------------------------------------------------------

# Set of hex-formatted IAT addresses for HAL port-I/O imports, e.g.
# {"0x1c0011000"}.  Matched via string-contains on the full function text.
_hal_iat_strs: set[str] = set()

# Current PE type string ("PE32" or "PE32+")
_pe_type: str = ""

# Whether init() has been called
_initialized: bool = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Import name prefixes that indicate direct hardware port I/O.
_HAL_IMPORT_PREFIXES = (
    "READ_PORT_",
    "WRITE_PORT_",
    "READ_REGISTER_",
    "WRITE_REGISTER_",
    "HalGet",
    "HalSet",
)

# Exact import names classified as HAL hardware-access functions.
_HAL_IMPORT_EXACT = {
    "KeStallExecutionProcessor",
}

# ---------------------------------------------------------------------------
# Compiled regex patterns
# ---------------------------------------------------------------------------

# Rule 1+2: I/O port read/write instructions.
_IO_RE = re.compile(
    r"\b(?:"
    r"in\s+(?:al|ax|eax)\s*,\s*(?:dx|0x[0-9a-f]+)"
    r"|out\s+(?:dx|0x[0-9a-f]+)\s*,\s*(?:al|ax|eax)"
    r")\b",
    re.IGNORECASE,
)

# Rule 3: Control register and MSR access.
_CR_RE = re.compile(
    r"\b(?:mov\b[^;]*\bcr[02348]\b|rdmsr|wrmsr)\b",
    re.IGNORECASE,
)

# Rule 6 (PE32+ only): Byte immediate loaded into DL (second argument
# register in x64 ABI) followed within 5 lines by a call instruction.
# Catches __outbyte(port, value) wrapper call sites where the actual
# in/out lives in an indirect dispatch chain that can't be resolved
# statically.
#
# Verified on i8042prt.sys first-50: 6.4% false positive rate on
# non-HARDWARE_IO functions (3/47), catches func_1c0002b38 which has
# no inline in/out but calls an I/O dispatch wrapper with port 0xD4.
_PORT_LOAD_CALL_RE = re.compile(
    r"mov\s+dl,0x[0-9a-f]{1,2}\b"
    r".*?\n(?:.*\n){0,4}.*"
    r"\bcall\s",
    re.IGNORECASE | re.DOTALL,
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def init(binary_path: Path, pe_type: str) -> None:
    """Parse the binary's import table and cache HAL-related IAT addresses.

    Must be called once before any ``should_call_llm()`` calls.
    """
    global _hal_iat_strs, _pe_type, _initialized

    _pe_type = pe_type
    _hal_iat_strs = set()

    pe = pefile.PE(str(binary_path))
    if hasattr(pe, "DIRECTORY_ENTRY_IMPORT"):
        for entry in pe.DIRECTORY_ENTRY_IMPORT:
            for imp in entry.imports:
                if imp.name is None:
                    continue
                name = imp.name.decode()
                is_hal = (
                    any(name.startswith(p) for p in _HAL_IMPORT_PREFIXES)
                    or name in _HAL_IMPORT_EXACT
                )
                if is_hal:
                    _hal_iat_strs.add(f"0x{imp.address:x}")
    pe.close()

    _initialized = True


def should_call_llm(function_text: str, pe_type: str) -> tuple[bool, str]:
    """Decide whether a function's disassembly warrants an LLM call.

    Returns ``(True, reason)`` if the function should be sent to the
    model, or ``(False, "no_io_signal")`` if it can be auto-classified
    as OTHER.

    Requires ``init()`` to have been called first for HAL import
    detection (rule 4).  Rules 1-3 and 5-6 work without init but
    rule 4 will produce no matches.
    """
    # Rule 1+2: Direct I/O port read/write instructions.
    if _IO_RE.search(function_text):
        return True, "direct_io"

    # Rule 3: Control register or MSR access.
    if _CR_RE.search(function_text):
        return True, "cr_msr_access"

    # Rule 4: Call to a HAL import (READ_PORT_*, KeStallExecution*, etc.)
    # Matched by checking whether any known HAL IAT address string appears
    # anywhere in the function text.  objdump annotates indirect calls with
    # "# 0x<rebased_addr>" comments that contain these addresses.
    for addr_str in _hal_iat_strs:
        if addr_str in function_text:
            return True, f"hal_import:{addr_str}"

    # Rule 5: Short I/O thunk — under 6 instructions AND matches rules 1-3.
    # This is a safety net: if MIN_INSTRUCTIONS is ever raised above 3,
    # short I/O thunks that slip through the splitter still get flagged.
    # Currently redundant with rules 1-3 but included for spec compliance.
    inst_count = sum(
        1 for line in function_text.split("\n")
        if re.match(r"\s+[0-9a-f]+:\s+[0-9a-f]{2}", line)
    )
    if inst_count < 6:
        if _IO_RE.search(function_text) or _CR_RE.search(function_text):
            return True, "short_io_thunk"

    # Rule 6 (PE32+ only): Port-loading pattern — byte immediate into DL
    # before a call.  Catches intrinsic wrapper call sites.
    if pe_type == "PE32+" and _PORT_LOAD_CALL_RE.search(function_text):
        return True, "port_load_call_pattern"

    return False, "no_io_signal"
