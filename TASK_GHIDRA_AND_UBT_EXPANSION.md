# ForthOS: Ghidra Validation + UBT Binary Expansion
**Date:** 2026-03-17
**Status:** Ready for Claude Code
**Commit base:** `8ca63ac` (NE2000 network demo, 268 tests passing)
**Sequence:** Task A first (Ghidra), then Task B (UBT expansion). They are independent but A informs B.

---

## TASK A: Ghidra Headless Validation Against Real i8042prt.sys

### Objective

Run Ghidra headless against a real Windows `i8042prt.sys` driver to generate a ground-truth semantic baseline. Compare against the UBT pipeline's output on the same binary. Confirm the UBT meets the minimum hit-rate thresholds before extending the pipeline to new binary formats.

This is a **one-time fixture generation** task. The Ghidra output is committed as a static JSON file and kept out of CI — it never runs again automatically.

### Prerequisites

Check these before starting:

```bash
# Ghidra installed?
which ghidra || snap list ghidra

# ExportSemanticReport.java script exists?
ls tools/ghidra/ExportSemanticReport.java

# Real i8042prt.sys available?
ls tests/fixtures/i8042prt.sys

# Translator builds cleanly?
cd tools/translator && make && make test
# Expected: 145/145 passing
```

If `i8042prt.sys` is not present under `tests/fixtures/`, locate it from a Windows system32/drivers directory or a WinXP/Win7 ISO. The 32-bit (x86) version is required — not x64. Expected size: approximately 52KB–54KB.

### Step 1 — Run Ghidra Headless

```bash
# Create output directory
mkdir -p tests/fixtures/ghidra-out

# Run headless analysis
ghidra-analyzeHeadless \
    /tmp/ghidra-i8042 i8042Project \
    -import tests/fixtures/i8042prt.sys \
    -postScript tools/ghidra/ExportSemanticReport.java \
        tests/fixtures/ghidra-out/i8042prt_ground_truth.json \
    -deleteProject \
    -noanalysis false \
    2>&1 | tee tests/fixtures/ghidra-out/ghidra_run.log
```

If `ExportSemanticReport.java` does not yet exist, create it (see Step 1a below), then re-run.

### Step 1a — Create ExportSemanticReport.java (if missing)

File: `tools/ghidra/ExportSemanticReport.java`

The script must export a JSON file with this structure:

```json
{
  "binary": "i8042prt.sys",
  "analysis_date": "...",
  "functions": [
    {
      "name": "KeyboardStartIo",
      "address": "0x00011234",
      "is_hardware": true,
      "port_io_count": 3,
      "ports": [{"port": 96, "access": "read"}, {"port": 100, "access": "write"}],
      "calls_hal": true,
      "hal_functions": ["READ_PORT_UCHAR", "WRITE_PORT_UCHAR"],
      "category": "port_io"
    }
  ],
  "summary": {
    "total_functions": 47,
    "hardware_functions": 12,
    "port_io_functions": 9,
    "hal_import_count": 18
  }
}
```

Classification rules for the script:
- A function is `is_hardware: true` if it calls any HAL port I/O function (`READ_PORT_UCHAR`, `WRITE_PORT_UCHAR`, `READ_PORT_USHORT`, `WRITE_PORT_USHORT`, `READ_PORT_ULONG`, `WRITE_PORT_ULONG`) OR contains direct `IN`/`OUT` x86 instructions
- `port_io_count` = number of port read/write operations in the function
- `ports` = deduplicated list of port addresses accessed (where statically determinable)
- `calls_hal` = function imports or calls through HAL.DLL
- `category` = `"port_io"` | `"mmio"` | `"timing"` | `"interrupt"` | `"scaffolding"` | `"unknown"`

### Step 2 — Run UBT on Same Binary

```bash
# Run translator on i8042prt.sys
./tools/translator/translator \
    -t forth \
    -o tests/fixtures/ubt-out/i8042prt_ubt.fth \
    tests/fixtures/i8042prt.sys

# Also dump semantic report
./tools/translator/translator \
    -t semantic-report \
    -o tests/fixtures/ubt-out/i8042prt_ubt_semantic.json \
    tests/fixtures/i8042prt.sys
```

If `-t semantic-report` is not yet a supported target, add it to `translator.c` — it should dump the `sem_result_t` as JSON after Stage 4 (semantic analysis) without proceeding to Forth codegen.

### Step 3 — Compare and Validate

Write a comparison script: `tools/ghidra/compare_semantic.py`

```python
#!/usr/bin/env python3
"""
Compare Ghidra ground truth vs UBT semantic output.
Asymmetric: UBT finding MORE than Ghidra is fine (expected).
UBT finding LESS is the failure condition.
"""
import json, sys

def load(path):
    with open(path) as f:
        return json.load(f)

ghidra = load(sys.argv[1])   # ground truth
ubt    = load(sys.argv[2])   # ubt output

# Count hardware functions
g_hw = set(f['name'] for f in ghidra['functions'] if f['is_hardware'])
u_hw = set(f['name'] for f in ubt['functions']    if f.get('is_hardware'))

# Count port I/O operations across all functions
g_pio = sum(f['port_io_count'] for f in ghidra['functions'])
u_pio = sum(f.get('port_io_count', 0) for f in ubt['functions'])

# Hit rate: what fraction of Ghidra's hardware functions did UBT find?
found_hw = len(g_hw & u_hw)
hw_rate  = found_hw / len(g_hw) if g_hw else 1.0

# Port I/O coverage: UBT must find >= 95% of Ghidra's port ops
pio_rate = min(u_pio / g_pio, 1.0) if g_pio else 1.0

print(f"Hardware functions: Ghidra={len(g_hw)}, UBT={len(u_hw)}, overlap={found_hw}")
print(f"Hardware hit rate:  {hw_rate:.1%} (threshold: 90%)")
print(f"Port I/O ops:       Ghidra={g_pio}, UBT={u_pio}")
print(f"Port I/O coverage:  {pio_rate:.1%} (threshold: 95%)")

# Functions Ghidra found that UBT missed
missed = g_hw - u_hw
if missed:
    print(f"\nMissed by UBT ({len(missed)}):")
    for name in sorted(missed):
        print(f"  - {name}")

# Functions UBT found that Ghidra missed (expected/fine)
extra = u_hw - g_hw
if extra:
    print(f"\nExtra in UBT (not a failure, {len(extra)}):")
    for name in sorted(extra):
        print(f"  + {name}")

PASS = hw_rate >= 0.90 and pio_rate >= 0.95
print(f"\n{'PASS' if PASS else 'FAIL'}: hw={hw_rate:.0%} pio={pio_rate:.0%}")
sys.exit(0 if PASS else 1)
```

Run it:

```bash
python3 tools/ghidra/compare_semantic.py \
    tests/fixtures/ghidra-out/i8042prt_ground_truth.json \
    tests/fixtures/ubt-out/i8042prt_ubt_semantic.json
```

### Step 4 — Thresholds and Expected Result

| Metric | Threshold | Notes |
|--------|-----------|-------|
| Hardware function hit rate | ≥ 90% | UBT finding more than Ghidra is fine |
| Port I/O operation coverage | ≥ 95% | Port ops are the core signal |

`i8042prt.sys` is a keyboard/PS2 controller driver. Known hardware functions to expect:
- Functions calling `READ_PORT_UCHAR(0x60)` — keyboard data port
- Functions calling `READ_PORT_UCHAR(0x64)` / `WRITE_PORT_UCHAR(0x64)` — status/command port
- IRQ connect/disconnect (keep as hardware: interrupt setup)
- Any function with direct `IN AL, DX` / `OUT DX, AL` instructions

### Step 5 — Commit the Fixture

```bash
# Commit ground truth as static fixture (never auto-regenerated)
git add tests/fixtures/i8042prt.sys \
        tests/fixtures/ghidra-out/i8042prt_ground_truth.json \
        tools/ghidra/ExportSemanticReport.java \
        tools/ghidra/compare_semantic.py
git commit -m "Add Ghidra ground-truth fixture for i8042prt.sys validation"
```

Add to `.gitignore`:
```
tests/fixtures/ubt-out/   # regenerated on demand, not committed
tests/fixtures/ghidra-out/ghidra_run.log
/tmp/ghidra-i8042/
```

### Step 6 — Add to Makefile (Optional)

```makefile
# Run UBT vs Ghidra comparison (requires fixture to already exist)
test-ghidra-validate:
    ./tools/translator/translator -t semantic-report \
        -o /tmp/i8042_ubt.json tests/fixtures/i8042prt.sys
    python3 tools/ghidra/compare_semantic.py \
        tests/fixtures/ghidra-out/i8042prt_ground_truth.json \
        /tmp/i8042_ubt.json
```

This target is NOT added to `make test` — it's on-demand only.

### Success Criteria for Task A

- [ ] `i8042prt_ground_truth.json` committed to `tests/fixtures/ghidra-out/`
- [ ] `compare_semantic.py` reports PASS (≥90% hw, ≥95% port I/O)
- [ ] `make test` still 268/268 (nothing regressed)
- [ ] If UBT fails thresholds: file specific issues in a `GHIDRA_GAPS.md` doc, do not hack the comparison script to pass

---

## TASK B: Extend UBT Pipeline to .exe / .dll / .com Binaries

### Background and Vision

The UBT pipeline currently handles Windows **kernel drivers** (`.sys` files). These use the HAL pattern — hardware access goes through `HAL.DLL` imports (`READ_PORT_UCHAR` etc.), which the semantic analyzer already understands perfectly.

The next phase extends this to **user-space binaries**:

- **DOS `.com` files**: Flat binary, no PE header, direct `IN`/`OUT` instructions in the code (no HAL layer). These are the *oldest* and most direct — exactly the kind Brenden described from the Forth-83 / Win95 era.
- **Win32 `.dll` files**: PE format (already handled by PE loader), but may use `DeviceIoControl` or direct port access. The `.NET` DLL case requires IL detection but not full translation yet.
- **Win32 `.exe` files**: PE format, same as `.dll` but with an entry point. Console apps may do direct port I/O. Useful for extracting hardware init sequences from standalone tools.

The goal is NOT to run these binaries. The goal is to **analyze and classify** what hardware operations they perform and emit a Forth vocabulary (or classification report) the same way the driver pipeline does.

### Architecture Change: Format Detection

The current pipeline assumes PE format. The first change is a **format detector** that routes to the right loader before decoding.

Add to `tools/translator/src/loaders/`:

**`format_detect.h` / `format_detect.c`**

```c
typedef enum {
    FORMAT_UNKNOWN = 0,
    FORMAT_PE_DRIVER,    /* .sys — kernel driver, HAL pattern */
    FORMAT_PE_DLL,       /* .dll — user-space, may have IAT or direct IN/OUT */
    FORMAT_PE_EXE,       /* .exe — user-space executable */
    FORMAT_DOS_COM,      /* .com — flat binary, origin 0x100 */
    FORMAT_ELF,          /* future: Linux ELF */
    FORMAT_DOTNET,       /* PE with CLR header — .NET assembly */
} binary_format_t;

typedef struct {
    binary_format_t format;
    bool            is_64bit;
    bool            is_dotnet;
    const char*     description;
} format_info_t;

format_info_t detect_format(const uint8_t* data, size_t size);
```

Detection logic:
- If first two bytes are `MZ` (`0x4D 0x5A`): PE family
  - Read `e_lfanew`, check for `PE\0\0` signature
  - If PE: check `Characteristics` field: `IMAGE_FILE_DLL` (0x2000) → `FORMAT_PE_DLL`, else `FORMAT_PE_EXE`
  - If `.sys` extension or `IMAGE_FILE_SYSTEM` characteristic → `FORMAT_PE_DRIVER`
  - If CLR data directory entry is non-zero → `FORMAT_DOTNET`
  - If `Machine == 0x8664` → `is_64bit = true`
- If first byte is any valid x86 opcode AND size ≤ 65280 bytes: `FORMAT_DOS_COM`
  - `.com` files have no header — they load at CS:0100 and execute from offset 0x100

### DOS .com Loader

**`tools/translator/src/loaders/com_loader.h` / `com_loader.c`**

A `.com` file is a flat binary image. There is no PE header, no import table, no sections. The entire file IS the code+data, loaded at virtual address `0x100` (COM origin).

```c
typedef struct {
    const uint8_t* code;       /* points into raw data at offset 0 */
    size_t         code_size;  /* entire file */
    uint32_t       load_addr;  /* always 0x100 for COM */
    bool           is_16bit;   /* COM files are 16-bit real mode */
} com_context_t;

int  com_load(com_context_t* ctx, const uint8_t* data, size_t size);
void com_cleanup(com_context_t* ctx);
```

**Critical:** `.com` files are **16-bit real mode** x86. The existing x86 decoder handles 32-bit protected mode. For `.com` analysis, the decoder must be told to operate in 16-bit mode. Add a mode flag to `x86_decoder_init()`:

```c
typedef enum {
    X86_MODE_16 = 16,
    X86_MODE_32 = 32,
    X86_MODE_64 = 64,
} x86_mode_t;
```

The 16-bit mode differences that matter for hardware extraction:
- `IN AL, DX` / `OUT DX, AL` — same opcodes as 32-bit (0xEC/0xEE), no change needed
- `IN AL, imm8` / `OUT imm8, AL` — same opcodes (0xE4/0xE6), no change needed
- Address size prefix (0x67) and operand size prefix (0x66) behave differently
- For the purpose of hardware extraction, `IN`/`OUT` detection works identically — these opcodes are the same in all x86 modes

In practice: add `X86_MODE_16` to the enum and pass it through, but the `IN`/`OUT` detection code path doesn't need changes. Flag it as 16-bit in the output metadata only.

### Semantic Analyzer Changes for User-Space Binaries

The current semantic analyzer assumes HAL imports for hardware access. User-space binaries use different patterns:

**Pattern 1: Direct IN/OUT (DOS .com, old Win32)**
Already detected by the UIR lifter via `UIR_PORT_IN` / `UIR_PORT_OUT` nodes. The semantic analyzer already marks these as `SEM_CAT_PORT_IO`. No change needed for basic detection.

**Pattern 2: DeviceIoControl (Win32 .exe/.dll)**
Add to `SEM_API_TABLE` in `semantic.c`:

```c
{"DeviceIoControl",     SEM_CAT_DEVICE_IO, "IOCTL",      "Win32 device IOCTL"},
{"CreateFile",          SEM_CAT_DEVICE_IO, "OPEN-DEV",   "Open device handle"},
{"ReadFile",            SEM_CAT_DEVICE_IO, "READ-DEV",   "Read from device"},
{"WriteFile",           SEM_CAT_DEVICE_IO, "WRITE-DEV",  "Write to device"},
{"CloseHandle",         SEM_CAT_DEVICE_IO, "CLOSE-DEV",  "Close device handle"},
```

**Pattern 3: NT native API (Win32 that calls kernel directly)**
```c
{"NtDeviceIoControlFile", SEM_CAT_DEVICE_IO, "NT-IOCTL",  "NT device IOCTL"},
{"ZwDeviceIoControlFile", SEM_CAT_DEVICE_IO, "NT-IOCTL",  "NT device IOCTL"},
```

**Pattern 4: .NET detection (do not translate, flag only)**
If `FORMAT_DOTNET` is detected, emit a classification report noting it's a managed assembly and skip Forth codegen. Do not attempt IL translation — that's a future phase.

Add `SEM_CAT_DOTNET` to the category enum and a check in the pipeline entry point:

```c
if (fmt.is_dotnet) {
    result.success = true;
    result.output = strdup("\ .NET assembly detected. IL translation not yet supported.\n"
                           "\ Use: translator -t dotnet-report <file> for metadata.\n");
    return result;
}
```

### Pipeline Wiring Changes

In `tools/translator/src/main/translator.c`, the `translate_buffer()` entry point:

**Before** (current):
```c
pe_context_t pe;
if (pe_load(&pe, data, size) != 0) {
    return error("Failed to parse PE file");
}
```

**After**:
```c
format_info_t fmt = detect_format(data, size);

switch (fmt.format) {
    case FORMAT_DOS_COM: {
        com_context_t com;
        if (com_load(&com, data, size) != 0)
            return error("Failed to load .com file");
        return translate_com(&com, opts);
    }
    case FORMAT_DOTNET:
        return translate_dotnet_report(data, size);  /* stub: emit notice */
    case FORMAT_PE_DRIVER:
    case FORMAT_PE_DLL:
    case FORMAT_PE_EXE: {
        pe_context_t pe;
        if (pe_load(&pe, data, size) != 0)
            return error("Failed to parse PE file");
        return translate_pe(&pe, opts, fmt.format);  /* existing path */
    }
    default:
        return error("Unknown binary format");
}
```

Extract the existing PE translation path into `translate_pe()` to keep the switch clean.

### New Test Fixtures

**DOS .com test fixture** — create a minimal synthetic `.com` file for testing:

`tests/fixtures/test_port_access.com` — synthesized, not from a real binary:

```python
# tools/make_test_com.py — generates a minimal COM file with known port I/O
import struct

# COM file: loads at 0x100
# IN AL, 0x60     ; E4 60 — read keyboard port
# OUT 0x61, AL    ; E6 61 — write speaker port
# IN AL, DX       ; EC    — read variable port
# OUT DX, AL      ; EE    — write variable port
# RET             ; C3

code = bytes([
    0xE4, 0x60,   # IN AL, 0x60
    0xE6, 0x61,   # OUT 0x61, AL
    0xEC,         # IN AL, DX
    0xEE,         # OUT DX, AL
    0xC3,         # RET
])
with open('tests/fixtures/test_port_access.com', 'wb') as f:
    f.write(code)
print(f"Written {len(code)} bytes")
```

Run this once: `python3 tools/make_test_com.py`

**Win32 .dll test fixture** — use the existing PE fixture infrastructure. The synthetic PE in `test_pipeline.c` already works. Add a variant that uses `DeviceIoControl` in its import table.

### New Tests

**`tests/test_format_detect.c`** — unit tests for format detector:

```c
test_detect_com()      // bytes[0] != MZ, size < 65280 → FORMAT_DOS_COM
test_detect_pe_sys()   // MZ + PE + driver characteristics → FORMAT_PE_DRIVER
test_detect_pe_dll()   // MZ + PE + IMAGE_FILE_DLL → FORMAT_PE_DLL
test_detect_pe_exe()   // MZ + PE + no DLL flag → FORMAT_PE_EXE
test_detect_dotnet()   // MZ + PE + CLR directory → FORMAT_DOTNET
test_detect_unknown()  // random bytes → FORMAT_UNKNOWN
```

**`tests/test_com_loader.c`** — unit tests for COM loader:

```c
test_com_load_minimal()       // 1-byte COM file loads correctly
test_com_load_address()       // load_addr == 0x100
test_com_port_detection()     // IN/OUT in test_port_access.com detected
test_com_port_addresses()     // ports 0x60, 0x61 found
```

**`tests/test_ubt_expansion.py`** — end-to-end test of the new formats:

```python
# Test 1: COM file produces valid Forth output with port constants
result = run(['./tools/translator/translator', '-t', 'forth',
              'tests/fixtures/test_port_access.com'])
assert '0060' in result or '60' in result  # port 0x60 present
assert 'C@-PORT' in result or 'PORT' in result

# Test 2: .dll file with DeviceIoControl in IAT produces report
result = run(['./tools/translator/translator', '-t', 'forth',
              'tests/fixtures/test_deviceioctl.dll'])
assert 'IOCTL' in result or 'DEVICE-IO' in result

# Test 3: .NET assembly produces graceful notice, not crash
result = run(['./tools/translator/translator', '-t', 'forth',
              'tests/fixtures/test_dotnet.dll'])
assert '.NET' in result or 'managed' in result.lower()
assert result.returncode == 0  # clean exit, not crash
```

### Forth Codegen Output for .com Files

The generated vocabulary should look like this for `test_port_access.com`:

```forth
\ ====================================================================
\ CATALOG: TEST-PORT-ACCESS
\ CATEGORY: input
\ SOURCE: extracted
\ SOURCE-BINARY: test_port_access.com
\ FORMAT: dos-com
\ ARCH: x86-16
\ PORTS: 0x60-0x61
\ CONFIDENCE: high
\ REQUIRES: HARDWARE ( C@-PORT C!-PORT )
\ ====================================================================

VOCABULARY TEST-PORT-ACCESS
TEST-PORT-ACCESS DEFINITIONS
HEX

\ ---- Port Constants ----
60 CONSTANT KBD-DATA    \ Keyboard data port (read)
61 CONSTANT SPK-CTRL    \ Speaker control port (write)

\ ---- Extracted Operations ----
: COM-OP-0100  ( -- byte )  KBD-DATA C@-PORT ;
: COM-OP-0102  ( byte -- )  SPK-CTRL C!-PORT ;

FORTH DEFINITIONS
```

### File Layout Summary

New files to create:

```
tools/translator/
  src/
    loaders/
      format_detect.c      ← NEW
      format_detect.h      ← NEW
      com_loader.c         ← NEW
      com_loader.h         ← NEW
  tests/
    test_format_detect.c   ← NEW
    test_com_loader.c      ← NEW
  Makefile                 ← MODIFY (add new sources + tests)

tests/
  fixtures/
    test_port_access.com   ← NEW (generated by make_test_com.py)
    test_deviceioctl.dll   ← NEW (synthetic PE with DeviceIoControl IAT)
    test_dotnet.dll        ← NEW (minimal PE with CLR directory set)
  test_ubt_expansion.py   ← NEW

tools/
  make_test_com.py         ← NEW (one-time fixture generator)
```

Modified files:
```
tools/translator/src/ir/semantic.c     ← add DeviceIoControl/Win32 API entries
tools/translator/src/main/translator.c ← add format_detect dispatch
tools/translator/src/decoders/x86_decoder.c ← add X86_MODE_16 enum value
```

### Build Order

Work in this order — each step is independently testable:

1. `format_detect.c` + `test_format_detect.c` — no other dependencies
2. `com_loader.c` + `test_com_loader.c` — depends on format_detect
3. Wire `format_detect` into `translator.c` dispatch — existing PE path unchanged
4. Add Win32 API entries to `semantic.c` — unit test with existing test infra
5. `test_ubt_expansion.py` end-to-end — validates the whole chain
6. Run `make test` — must still be 268/268 before adding new passing tests

### Success Criteria for Task B

- [ ] `make test` starts at 268/268, ends higher (new tests added)
- [ ] `translator test_port_access.com -t forth` produces valid Forth with port 0x60 and 0x61 present
- [ ] `translator <any_pe_dll> -t forth` still works (no regression on PE path)
- [ ] `.NET` assembly produces clean notice, exit 0 (no crash)
- [ ] Format detector correctly classifies all 5 format types in unit tests
- [ ] `git commit -m "UBT: add .com/.dll/.exe format detection and COM loader"`

### Known Constraints (Do Not Violate)

- **No 2\* in Forth source** — use `DUP +` instead
- **HEX/DECIMAL discipline** — all new `.fth` output must explicitly set numeric base
- **64-character line limit** in block format — applies to any Forth output targeting block storage
- **Kernel primitives only** in hardware vocabularies — `INB`/`OUTB`/`INL`/`OUTL`, no CODE words
- **`make test` is the gate** — do not commit if any existing test regresses

---

## Handoff Checklist

Before starting, confirm in the repo:

```bash
git log --oneline -3
# Should show: 8ca63ac as most recent

make test
# Should show: 105/105 (plus translator 145/145 = 268 total)

ls CLAUDE_CODE_TASK_GHIDRA_VALIDATION.md
# If this exists, read it first — this doc supersedes/extends it
```

Execute Task A fully (fixture committed, comparison passes) before starting Task B. If Task A's comparison shows the UBT missing hardware functions, open `GHIDRA_GAPS.md` and note them — do not skip to Task B with a failing baseline.
