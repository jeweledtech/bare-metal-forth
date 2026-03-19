# Real Binary Validation

Manual validation of the UBT pipeline against real Windows/Linux binaries.

## Prerequisites

```bash
cd tools/translator && make
```

## Quick Start

```bash
python3 tools/validate_real_binary.py <path-to-binary>
```

The script runs the translator in disasm, report, and forth modes, checking each for plausibility.

## Targets

### Category 1: Windows kernel drivers (.sys)

Already validated:
- `i8042prt.sys` — PS/2 keyboard/mouse driver. 9 hardware functions, HAL port I/O via READ_PORT_UCHAR/WRITE_PORT_UCHAR. Committed as test fixture.

Good candidates:
- `serial.sys` — ReactOS serial driver (GPL). 16550 UART hardware protocol.
- `parport.sys` — parallel port driver. Direct port I/O.
- `videoprt.sys` — video port minidriver. MMIO + port I/O.

### Category 2: Windows DLLs with DeviceIoControl

- `serialui.dll` from Win9x/WinXP — serial port configuration UI
- Hardware vendor SDK DLLs that call DeviceIoControl
- Expected: translator finds DeviceIoControl in IAT, classifies as SEM_CAT_DEVICE_IO

### Category 3: Linux ELF binaries

- `/usr/sbin/setserial` — serial port utility (may use iopl/ioperm)
- Kernel modules (.ko files) — ELF relocatable objects with IN/OUT instructions
- Any iopl()-using user-space tools

### Category 4: DOS .com utilities

- Old hardware diagnostic tools that do direct IN/OUT
- BIOS utility .com files

## How to Get Test Binaries

### ReactOS (GPL, legal)
```bash
# Download ReactOS ISO from reactos.org
# Extract: system32/drivers/serial.sys, parport.sys, etc.
```

### WinXP (for reference only)
- Archive.org has WinXP SP3 ISOs for research
- Extract from `i386/` directory: `expand driver.sy_ driver.sys`
- Files: serial.sys, parport.sys, hal.dll, serialui.dll

### Linux system binaries
```bash
# Already on your system:
python3 tools/validate_real_binary.py /usr/sbin/setserial
python3 tools/validate_real_binary.py /bin/true
```

## Understanding Results

The validator checks:
1. **Disassembly** — can the decoder handle all instructions?
2. **Semantic report** — are hardware functions detected?
3. **Forth codegen** — does it produce valid, block-safe Forth?
4. **Line length** — all lines <= 64 chars for block loading?

A "WARN" on hardware function detection is normal for non-driver binaries (e.g., /bin/true has no port I/O).

## Semantic Report

```bash
# JSON output matching the Ghidra fixture schema:
./tools/translator/bin/translator -t report <binary>

# Pipe to jq for readable output:
./tools/translator/bin/translator -t report i8042prt.sys | jq .summary
```

The report includes:
- `port_operations` — detected IN/OUT instructions with port numbers
- `hardware_functions` — functions with hardware access
- `imports` — classified IAT entries (PE only)
- `scaffolding_functions` — filtered Windows boilerplate
- `summary` — counts for quick triage

## Adding New Test Binaries

Real binaries cannot be committed (license). Instead:
1. Run the validator manually, note the expected counts
2. If the binary reveals a pipeline bug, create a synthetic fixture that reproduces it
3. Add the synthetic fixture to `tools/translator/tests/data/` with a C test
