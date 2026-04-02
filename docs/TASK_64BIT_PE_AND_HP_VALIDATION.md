# UBT: 64-bit PE32+ Fix + beep.sys + HP Real Hardware Validation
**Date:** 2026-03-21  
**Status:** Ready for the toolchain  
**Commit base:** `93f7142` (234 tests / 20 suites, all passing)  
**Priority:** Task A (64-bit fix) blocks Task C (HP validation). Tasks A and B are independent.

---

## Background

The binary campaign (commits `74c9ce6` → `93f7142`) validated 11 real-world binaries and added BIOS interrupt support. The HP Laptop 15-bs0xx (Kaby Lake i5-7200U) provided 8 real Windows 10/11 x64 drivers from `C:\Windows\System32\drivers\`. Running them through the pipeline revealed two bugs:

1. **64-bit decode broken** — REX prefixes (`0x48`, `0x49`, `0x41`) are being decoded as 32-bit single-byte instructions (`DEC EAX`, `INC ECX`, `INC ESP`) instead of as REX prefix bytes. The pipeline is running in `X86_MODE_32` for all PE files regardless of machine type.

2. **No function boundaries for stripped 64-bit PE** — 64-bit Windows drivers have no exports and no symbols. The entire `.text` section is treated as one function. `i8042prt.sys` (which should show ~9 hardware functions) returns `total_functions: 1`. Fix: parse the `.pdata` section which contains `RUNTIME_FUNCTION` structures with exact function start/end RVAs.

Evidence:
```
bin/translator -t disasm tests/hp_i3/i8042prt.sys | head shows:
  1c0001010:  dec    eax        ← 0x48 = REX.W misread as DEC EAX
  1c0001015:  dec    eax        ← same
  1c0001024:  inc    ecx        ← 0x41 = REX.B misread as INC ECX

bin/translator -t semantic-report tests/hp_i3/i8042prt.sys shows:
  Total functions: 1             ← entire driver = 1 function
  HW functions: 1                ← should be ~9
```

HP drivers are in `tests/hp_i3/` (gitignored, already on disk):
- `i8042prt.sys`, `serial.sys`, `pci.sys`, `disk.sys`
- `ACPI.sys`, `HDAudBus.sys`, `storport.sys`, `usbxhci.sys`

---

## TASK A: Fix 64-bit PE Decode Mode

### A1: Pass X86_MODE_64 for PE32+ binaries

**File:** `tools/translator/src/main/translator.c`

Find the `translate_pe()` function. Locate where `x86_decoder_init()` is called. Change:

```c
// Current (wrong):
x86_decoder_init(&dec, X86_MODE_32, ...);

// Fix: use pe.is_64bit to select mode
x86_mode_t mode = pe.is_64bit ? X86_MODE_64 : X86_MODE_32;
x86_decoder_init(&dec, mode, ...);
```

`pe.is_64bit` is already populated by the PE loader (`machine == 0x8664`).

**Verify the fix:** After rebuilding, run:
```bash
bin/translator -t disasm tests/hp_i3/i8042prt.sys 2>/dev/null | head -20
```
Should show valid x86-64 instructions (`mov rsp`, `push rbx`, etc.) instead of `dec eax`/`inc ecx` garbage.

### A2: Parse .pdata for Function Boundaries

**File:** `tools/translator/src/loaders/pe_loader.c` and `include/pe_loader.h`

The `.pdata` section in 64-bit PE files contains an array of `RUNTIME_FUNCTION` structures:

```c
typedef struct {
    uint32_t BeginAddress;   /* RVA of function start */
    uint32_t EndAddress;     /* RVA of function end (exclusive) */
    uint32_t UnwindData;     /* RVA of UNWIND_INFO (ignore for our purposes) */
} RUNTIME_FUNCTION;          /* 12 bytes each */
```

Add to `pe_context_t` in `include/pe_loader.h`:

```c
/* Function boundaries from .pdata (64-bit PE only) */
typedef struct {
    uint64_t start_rva;
    uint64_t end_rva;
} pe_func_boundary_t;

pe_func_boundary_t* func_boundaries;   /* array, sorted by start_rva */
size_t              func_boundary_count;
```

In `pe_loader.c`, after parsing section headers, find the `.pdata` section:

```c
/* Parse .pdata for 64-bit function boundaries */
if (pe->is_64bit) {
    for (int i = 0; i < section_count; i++) {
        if (memcmp(sections[i].name, ".pdata", 6) == 0) {
            size_t entry_count = sections[i].size / 12;  /* 12 bytes per entry */
            pe->func_boundaries = calloc(entry_count, sizeof(pe_func_boundary_t));
            pe->func_boundary_count = 0;
            const uint8_t* pdata = data + sections[i].offset;
            for (size_t j = 0; j < entry_count; j++) {
                uint32_t begin = read_u32(pdata + j*12 + 0);
                uint32_t end   = read_u32(pdata + j*12 + 4);
                if (begin == 0 || begin >= end) continue;
                pe->func_boundaries[pe->func_boundary_count].start_rva = begin;
                pe->func_boundaries[pe->func_boundary_count].end_rva   = end;
                pe->func_boundary_count++;
            }
            break;
        }
    }
}
```

In `pe_cleanup()`, add `free(pe->func_boundaries)`.

### A3: Use .pdata Boundaries in translate_pe()

In `translate_pe()`, after decoding instructions, use the `.pdata` boundaries to split the instruction stream into per-function groups before UIR lifting:

```c
if (pe.func_boundary_count > 0) {
    /* Use .pdata boundaries — iterate over each function */
    for (size_t f = 0; f < pe.func_boundary_count; f++) {
        uint64_t func_start = pe.image_base + pe.func_boundaries[f].start_rva;
        uint64_t func_end   = pe.image_base + pe.func_boundaries[f].end_rva;
        /* Find instructions within [func_start, func_end) */
        /* Lift to UIR, analyze, add to results */
    }
} else {
    /* Fallback: treat entire .text as one function (existing behavior) */
}
```

The existing `sem_discover_functions()` / `sem_function_map_t` infrastructure already handles function boundary input — check how `translate_elf()` uses it and follow the same pattern.

### A4: Tests for 64-bit Fix

Add to `tests/test_pe_loader.c`:
```
test_pdata_parsing()       // synthetic PE64 with .pdata → func_boundary_count > 0
test_pdata_boundaries()    // BeginAddress/EndAddress correctly read
test_64bit_mode_selected() // pe.is_64bit=true → translate uses X86_MODE_64
```

Add to `tests/test_x86_decoder.c`:
```
test_rex_w_prefix()     // 0x48 0x89 0xE5 = MOV RBP, RSP (not DEC EAX)
test_rex_b_prefix()     // 0x41 0x50 = PUSH R8 (not INC ECX + PUSH EAX)
test_rex_mov_r64()      // 0x48 0xB8 + 8 bytes = MOV RAX, imm64
```

---

## TASK B: beep.sys Validation

Extract `beep.sys` from the ReactOS Live CD (same pycdlib workflow as `serial.sys`). This is the simplest possible Windows driver — PIT timer + PC speaker gate.

### B1: Extract beep.sys

```python
# tools/extract_beep.py
import pycdlib, os

iso_path = '/tmp/reactos/ReactOS-0.4.14-release-125-g5b02d38-Live.iso'
# If ISO not present, download it:
# curl -L -o /tmp/reactos/reactos-live.zip \
#   "https://sourceforge.net/projects/reactos/files/ReactOS/0.4.14/\
#    ReactOS-0.4.14-release-125-g5b02d38-live.zip/download"
# unzip /tmp/reactos/reactos-live.zip -d /tmp/reactos/

iso = pycdlib.PyCdlib()
iso.open(iso_path)
iso.get_file_from_iso(
    local_path='tests/data/beep.sys',
    iso_path='/REACTOS/SYSTEM32/DRIVERS/BEEP.SYS;1'
)
iso.close()
print(f"Extracted beep.sys: {os.path.getsize('tests/data/beep.sys')} bytes")
```

### B2: Validate Expected Hardware Functions

beep.sys should contain:
- Functions accessing port `0x42` (PIT channel 2 counter — frequency)
- Functions accessing port `0x43` (PIT mode/command register)
- Functions accessing port `0x61` (PC speaker gate — bit 0 = gate, bit 1 = speaker enable)

Expected: 2-4 hardware functions, all HAL-based (`WRITE_PORT_UCHAR`).

### B3: Create test_beep_validation.c

Follow `tests/test_serial_validation.c` pattern. 7 tests:
1. `pipeline_succeeds` — translator returns success
2. `hw_function_count` — semantic report shows >= 2 hardware functions
3. `pit_port_detected` — Forth output contains port `42` or `43`
4. `speaker_port_detected` — Forth output contains port `61`
5. `requires_hardware` — REQUIRES: HARDWARE in vocab header
6. `line_length_ok` — all lines <= 64 chars
7. `driver_entry_filtered` — `DriverEntry` not in hardware functions

Add `test-beep-validation` target to Makefile, wire into `test-all`.

---

## TASK C: HP Real Hardware Validation

**Depends on: Task A complete**

After the 64-bit fix, re-run the pipeline against all 8 HP drivers and write validation tests.

### C1: Run Pipeline Against HP Drivers

```bash
cd tools/translator
for f in tests/hp_i3/*.sys; do
    echo "=== $(basename $f) ==="
    bin/translator -t semantic-report "$f" 2>/dev/null | \
        python3 -c "
import sys, json
d = json.load(sys.stdin)
s = d['summary']
print(f'  HW: {s[\"hardware_functions\"]}, Scaffolding: {s[\"scaffolding_functions\"]}, Total: {s[\"total_functions\"]}')
for f in d.get('hardware_functions', [])[:5]:
    print(f'    {f[\"address\"]}: {f[\"name\"]}')
" 2>/dev/null || echo "  (failed)"
done
```

**Expected results after fix:**

| Driver | Expected HW Funcs | Notes |
|---|---|---|
| `i8042prt.sys` | ~9 | PS/2 keyboard/mouse — matches ReactOS version |
| `serial.sys` | ~9 | 16550 UART — matches ReactOS version |
| `pci.sys` | ~7 | PCI config space |
| `disk.sys` | ~5 | ATA/SCSI disk operations |
| `HDAudBus.sys` | ~3-8 | Intel HD Audio MMIO |
| `storport.sys` | ~20 | Already partially working |
| `usbxhci.sys` | ~5-15 | xHCI MMIO operations |
| `ACPI.sys` | TBD | May use MMIO — could still be 0 |

### C2: Create test_hp_drivers.c

Runtime-load from `tests/hp_i3/` (skip gracefully if absent — same pattern as `test_elf_drivers.c`). Use `>=` thresholds since Windows version may vary.

Tests per driver (2-3 each):
1. `pipeline_succeeds` — translator returns success, exit 0
2. `hw_function_count_gte` — hardware functions >= expected minimum
3. `line_length_ok` — all Forth output lines <= 64 chars

For `i8042prt.sys` and `serial.sys`, add stronger assertions matching the known ReactOS equivalents:
- Same port addresses (0x60/0x64 for i8042, 0x3F8-0x3FF for serial)
- Similar function count (within ±2 of ReactOS version)

### C3: Makefile

Add `test-hp-drivers` target (skips gracefully if `tests/hp_i3/` absent), wire into `test-all`.

---

## TASK D: ACPI.sys Investigation (Optional)

`ACPI.sys` returned `(parse failed)` — likely a parse error, not just 0 hardware functions. Check:

```bash
bin/translator -t forth tests/hp_i3/ACPI.sys 2>&1 | head -5
```

If it's a genuine parse failure, check why — ACPI.sys may have an unusual PE structure (resource-only sections, unusual alignment). Document the failure mode if it can't be fixed easily.

---

## Execution Order

```
Task B (beep.sys)          ← independent, do first or in parallel
Task A1 (64-bit mode)      ← one-line fix, verify with disasm output
Task A2 (pdata parsing)    ← adds pe_func_boundary_t, parse .pdata
Task A3 (use in pipeline)  ← wire boundaries into translate_pe()
Task A4 (tests)            ← unit tests for decoder + PE loader
Task C (HP validation)     ← depends on A complete
Task D (ACPI)              ← optional, last
```

## Verification Gates

After each task:
```bash
cd tools/translator && make clean && make && make test
```
Must stay green. Current baseline: 234/234 across 20 suites.

After Task A:
```bash
bin/translator -t disasm tests/hp_i3/i8042prt.sys 2>/dev/null | head -5
# Must show valid x86-64, NOT dec eax / inc ecx

bin/translator -t semantic-report tests/hp_i3/i8042prt.sys 2>/dev/null | \
    python3 -c "import sys,json; d=json.load(sys.stdin); \
    print('Functions:', d['summary']['total_functions'])"
# Must show > 1 (ideally ~50-100 from .pdata boundaries)
```

After Task C:
```bash
python3 tools/validate_real_binary.py tests/hp_i3/i8042prt.sys tests/hp_i3/serial.sys
# Must show PASS for both
```

## Commit Messages

- Task A: `"UBT: fix 64-bit PE decode — X86_MODE_64 + .pdata function boundaries"`
- Task B: `"UBT: add beep.sys validation (PIT/speaker driver)"`
- Task C: `"UBT: HP real hardware validation — 8 Windows 10/11 x64 drivers"`
