# Ghidra Validation Framework — Design Document

Date: 2026-02-23
Status: Approved
Prerequisite: Phase C completion (catalog-resolver commit)

## Purpose

Establish Ghidra as the validation oracle ("measuring stick, not mechanism") for the
Universal Binary Translator pipeline. The framework validates that the translator's
semantic extraction matches what Ghidra discovers in the same binary — same ports,
same hardware functions, same import categories — without requiring Ghidra at test time.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  Test Comparison Layer                        │
│  tools/translator/tests/test_ghidra_compare.c                │
│  Loads ghidra_report.json + runs translator → compares       │
│  semantics: ports, hardware functions, import categories     │
└────────────┬──────────────────────────┬─────────────────────┘
             │                          │
   ┌─────────▼───────────┐   ┌─────────▼───────────────┐
   │ Ghidra JSON Fixture  │   │ Translator Pipeline      │
   │ tests/data/fixtures/  │   │ translate_buffer()       │
   │ *.ghidra.json        │   │ → Forth output           │
   └─────────┬────────────┘   └──────────────────────────┘
             │
   ┌─────────▼────────────┐
   │ Ghidra Export Script  │  (runs via analyzeHeadless)
   │ tools/ghidra/          │
   │ ExportSemanticReport  │
   │ .java                 │
   └─────────┬────────────┘
             │
   ┌─────────▼────────────┐
   │ Test .sys Binaries    │
   │ tests/data/           │
   │ synthetic + real      │
   └──────────────────────┘
```

### Data Flow

1. `make ghidra-fixtures` runs Ghidra headless on each .sys in tests/data/ →
   produces .ghidra.json in tests/data/fixtures/
2. `make test` runs test_ghidra_compare which loads the cached JSON fixture,
   runs translate_buffer() on the same .sys, and compares semantic output
3. No Ghidra dependency at normal test time

## JSON Fixture Schema (Version 1)

```json
{
    "schema_version": 1,
    "generator": "ghidra",
    "ghidra_version": "12.0",
    "binary": {
        "filename": "serial16550_synth.sys",
        "sha256": "<hex>",
        "format": "PE32",
        "machine": "i386",
        "image_base": "0x10000"
    },
    "port_operations": [
        {
            "address": "0x11000",
            "port": "0xF8",
            "direction": "write",
            "width": "byte",
            "function": "UART_INIT"
        }
    ],
    "hardware_functions": [
        {
            "name": "UART_INIT",
            "address": "0x11000",
            "size": 11,
            "ports_accessed": ["0xF8", "0xF9", "0xFA", "0xFB"],
            "classification": "PORT_IO"
        }
    ],
    "imports": [
        {
            "dll": "HAL.dll",
            "function": "READ_PORT_UCHAR",
            "category": "PORT_IO"
        }
    ],
    "scaffolding_functions": [
        {
            "name": "DriverEntry",
            "address": "0x11100",
            "reason": "IRP/PNP scaffolding"
        }
    ]
}
```

### Extensibility

The schema_version field enables forward-compatible evolution. Future versions add
new top-level arrays (register_access_patterns, initialization_sequences, data_flow)
without breaking existing fixtures. Comparison code checks schema_version and skips
dimensions absent in the fixture.

## Synthetic .sys Binary

A standalone builder (tests/data/build_synthetic_drivers.c) generates
serial16550_synth.sys — a proper PE32 file (~3KB) with:

- DriverEntry export (scaffolding — should be filtered)
- UART_INIT, UART_SEND, UART_RECV exports (hardware — should be kept)
- READ_PORT_UCHAR and WRITE_PORT_UCHAR imports from HAL.dll
- IN/OUT instructions at ports 0xF8-0xFD (16550 register range)
- Structurally identical to existing build_16550_pe() in test_16550_driver.c

The generated .sys file is committed to the repo so anyone can run make test
without the builder. The builder source is there for regeneration.

## Ghidra Export Script

tools/ghidra/ExportSemanticReport.java — a Ghidra post-analysis script that:

1. Iterates all functions, records name/address/size
2. For each instruction, checks for IN/OUT opcodes → records port operations
3. Walks the import table → categorizes each import
4. Classifies functions as hardware (has port I/O or hardware imports) vs scaffolding
5. Writes JSON report to output path specified via script arguments

Invocation:
```bash
JAVA_HOME=/snap/ghidra/35/usr/lib/jvm/java-21-openjdk-amd64 \
  /snap/ghidra/35/ghidra_12.0_PUBLIC/support/analyzeHeadless \
  /tmp/ghidra_project GhidraProject \
  -import tests/data/serial16550_synth.sys \
  -postScript ExportSemanticReport.java \
  -scriptPath tools/ghidra \
  -scriptlog /tmp/ghidra_script.log \
  -deleteProject
```

## Comparison Test

tools/translator/tests/test_ghidra_compare.c loads the cached .ghidra.json fixture
and runs translate_buffer() on the same .sys binary, then compares:

- **Ports:** Every port in Ghidra's port_operations appears in the Forth output
  as a CONSTANT REG-XX or port reference
- **Functions:** Every hardware function in Ghidra appears as a : FUNCNAME word
  in the Forth output. Every scaffolding function does NOT appear.
- **Imports:** HAL.dll port I/O imports map to C@-PORT/C!-PORT in REQUIRES line

### Asymmetric Comparison

The comparison checks that the translator found everything Ghidra found (no false
negatives in hardware detection), but does NOT penalize for finding more. The
translator detects IN/OUT instructions directly; Ghidra may miss port operations
through indirect addressing. Symmetric comparison would create false failures.

## Makefile Integration

```makefile
# Build synthetic .sys
build/tests/data/serial16550_synth.sys: tests/data/build_synthetic_drivers.c
    $(CC) -o build/tests/build_synth $<
    build/tests/build_synth

# Regenerate Ghidra fixtures (requires Ghidra)
ghidra-fixtures: build/tests/data/serial16550_synth.sys
    $(GHIDRA_HEADLESS) /tmp/ghidra_proj GhidraProj \
        -import $< -postScript ExportSemanticReport.java \
        -scriptPath tools/ghidra -overwrite -deleteProject
    cp /tmp/ghidra_output/*.ghidra.json tests/data/fixtures/

# Normal test — no Ghidra required
test-ghidra-compare: build/tests/test_ghidra_compare
    ./build/tests/test_ghidra_compare
```

## Real-World Stretch Goal

After synthetic validation works, the next target is ReactOS's serial.sys driver
(GPL-licensed, real 16550 UART hardware). This is the proof-of-concept moment:
run make ghidra-fixtures on it, run the comparison test, iterate until the Forth
output captures the same hardware semantics Ghidra identifies.

## Implementation Sequence

1. **Phase C completion** — run integration test, fix issues, commit clean
2. **Synthetic .sys builder** — extract build_16550_pe() to standalone, add
   DriverEntry scaffolding function, write to file
3. **Ghidra export script** — Java script for headless analysis
4. **Generate fixture** — run Ghidra on synthetic .sys, commit JSON fixture
5. **Comparison test** — test_ghidra_compare.c with minimal JSON parser
6. **Makefile wiring** — ghidra-fixtures target, test-ghidra-compare target
7. **ReactOS stretch** — real driver validation
