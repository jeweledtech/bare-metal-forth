# Ghidra Validation Framework Implementation Plan

> **Note:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Ghidra-as-oracle validation framework that proves the translator pipeline extracts the same hardware semantics from a .sys binary as Ghidra does.

**Architecture:** Hybrid fixture approach — Ghidra headless generates JSON semantic reports, cached as committed fixtures. Normal `make test` compares translator output against fixtures without requiring Ghidra. Asymmetric comparison: translator must find everything Ghidra found (no false negatives), but may find more.

**Tech Stack:** C (test harness, synthetic PE builder), Java (Ghidra headless script), Make (build integration), JSON (fixture format)

**Prerequisite:** Phase C must be committed first (Tasks 1-2).

---

### Task 1: Phase C — Verify kernel changes and run integration test

**Files:**
- Test: `tests/test-catalog-resolver.sh`
- Verify: `src/kernel/forth.asm` (uncommitted: DOCREATE, BLOCK_LOADING, 2OVER, \\/( block-mode, find_ FORTH fallback, THRU offset, S" TIB-based)
- Verify: `forth/dict/catalog-resolver.fth` (uncommitted restructure)

**Step 1: Build the kernel**

Run: `cd /home/bbrown/projects/forthos && make clean && make`
Expected: `bmforth.img` built successfully, no errors.

**Step 2: Quick smoke test — verify VARIABLE works with DOCREATE fix**

Start QEMU on a unique port, send commands via Python:

```bash
pkill -9 -f 'qemu.*bmforth' || true
qemu-system-i386 -drive file=build/bmforth.img,format=raw,if=floppy \
  -serial tcp::5555,server=on,wait=off -display none &
sleep 2
```

```python
# Quick test: VARIABLE should work now
import socket, time
s = socket.socket()
s.connect(('127.0.0.1', 5555))
time.sleep(1)
s.recv(4096)  # flush banner

s.sendall(b'VARIABLE TESTVAR\r')
time.sleep(0.5)
s.sendall(b'42 TESTVAR !\r')
time.sleep(0.5)
s.sendall(b'TESTVAR @ .\r')
time.sleep(0.5)
out = s.recv(4096).decode()
assert '42' in out, f"Expected 42, got: {out}"
print("PASS: VARIABLE works")
s.close()
```

Expected: `42` appears in output.

**Step 3: Build block disk and test THRU with small range**

```bash
dd if=/dev/zero of=build/test-blocks.img bs=1024 count=1024
python3 tools/write-catalog.py build/test-blocks.img forth/dict/
```

Start QEMU with block disk:
```bash
pkill -9 -f 'qemu.*bmforth' || true
qemu-system-i386 -drive file=build/bmforth.img,format=raw,if=floppy \
  -drive file=build/test-blocks.img,format=raw,if=ide,index=1 \
  -serial tcp::5556,server=on,wait=off -display none &
sleep 2
```

Test: `1 LIST` to verify catalog block is readable, then `2 3 THRU` for a small range.

**Step 4: Run the full integration test**

Run: `cd /home/bbrown/projects/forthos && bash tests/test-catalog-resolver.sh`
Expected: Test completes (may need fixes — see Step 5).

**Step 5: Fix any failures**

Common issues to watch for:
- THRU hanging: check if any block source has lines >64 chars
- Unknown word errors: check if catalog-resolver.fth uses words not in kernel
- Prompt detection: test script may need timing adjustments

After all issues fixed, verify test passes cleanly.

**Step 6: Commit Phase C**

```bash
git add src/kernel/forth.asm forth/dict/catalog-resolver.fth tests/test-catalog-resolver.sh
git commit -m "Phase C: DOCREATE fix, block loading improvements, catalog-resolver

Kernel changes:
- DOCREATE runtime for CREATE'd words (bug #18 fix)
- VAR_BLOCK_LOADING flag prevents LOAD no-op (bug #13)
- Block-mode \\ and ( comments (bugs #14, #15)
- find_ FORTH fallback (bug #17)
- THRU offset fix -16 and INCR for inclusive range (bugs #12, #16)
- S\" reads from TIB instead of read_key
- 2OVER added to kernel

Catalog-resolver: vocabulary dependency resolver for block loading.
Integration test: test-catalog-resolver.sh."
```

---

### Task 2: Phase C — Run existing translator tests (regression check)

**Files:**
- Test: `tools/translator/Makefile` (test target)

**Step 1: Run all translator tests**

Run: `cd /home/bbrown/projects/forthos/tools/translator && make clean && make && make test`
Expected: All 76 tests pass, no regressions. Build warnings about unused functions in translator.c are expected.

**Step 2: Verify clean git status**

Run: `git status`
Expected: Clean working tree (or only untracked test files from earlier sessions).

---

### Task 3: Synthetic .sys builder — write the file to disk

**Files:**
- Create: `tools/translator/tests/data/build_synthetic_drivers.c`
- Output: `tools/translator/tests/data/serial16550_synth.sys` (committed binary)

**Step 1: Write the builder program**

This extracts the `build_16550_pe()` logic from `tests/test_16550_driver.c` into a standalone program that writes the PE to a file. Adds a DriverEntry scaffolding function (just RET) to exercise the semantic filter.

```c
/* build_synthetic_drivers.c — Generate synthetic .sys test binaries
 *
 * Usage: build_synthetic_drivers [output_dir]
 * Default output: current directory
 *
 * Generates serial16550_synth.sys — a PE32 with 16550 UART port I/O
 * plus Windows scaffolding, for Ghidra validation testing.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

#include "../../include/pe_format.h"

static int build_serial16550(const char* output_dir) {
    /* Identical to build_16550_pe() in test_16550_driver.c,
     * but also adds a DriverEntry function (scaffolding) and
     * writes result to a file. */

    size_t file_size = 0xC00;
    uint8_t* buf = calloc(1, file_size);

    /* [PE construction code — same as test_16550_driver.c build_16550_pe()
     *  with these additions:
     *  1. DriverEntry at text offset 0x28: just MOV EAX,0 / RET (scaffolding)
     *  2. Export table includes DriverEntry as 4th export
     *  3. Import table includes IoCompleteRequest from ntoskrnl.exe (scaffolding)] */

    /* ... (full PE construction) ... */

    char path[512];
    snprintf(path, sizeof(path), "%s/serial16550_synth.sys", output_dir);
    FILE* f = fopen(path, "wb");
    if (!f) { free(buf); return 1; }
    fwrite(buf, 1, file_size, f);
    fclose(f);
    free(buf);

    printf("Wrote %s (%zu bytes)\n", path, file_size);
    return 0;
}

int main(int argc, char** argv) {
    const char* dir = argc > 1 ? argv[1] : ".";
    return build_serial16550(dir);
}
```

The actual implementation must include the complete PE construction inline (copy from `test_16550_driver.c:build_16550_pe()`, lines 73-274), plus:
- A DriverEntry function at text offset 0x28: `B8 00 00 00 00 C3` (MOV EAX,0; RET)
- A 4th export "DriverEntry" pointing to RVA 0x1028
- A 2nd import DLL "ntoskrnl.exe" with "IoCompleteRequest" (scaffolding API)

**Step 2: Build and run the builder**

Run:
```bash
cd /home/bbrown/projects/forthos/tools/translator
gcc -Wall -Wextra -O2 -std=c11 -Iinclude -Isrc \
    tests/data/build_synthetic_drivers.c -o build/tests/build_synth
./build/tests/build_synth tests/data/
```
Expected: `Wrote tests/data/serial16550_synth.sys (3072 bytes)`

**Step 3: Verify the translator can process the .sys file**

Run:
```bash
./bin/translator -t forth -n SERIAL-16550 tests/data/serial16550_synth.sys
```
Expected: Forth vocabulary output with UART_INIT, UART_SEND, UART_RECV functions. DriverEntry should NOT appear (filtered as scaffolding).

**Step 4: Verify Ghidra can load the .sys file**

Run:
```bash
JAVA_HOME=/snap/ghidra/35/usr/lib/jvm/java-21-openjdk-amd64 \
  /snap/ghidra/35/ghidra_12.0_PUBLIC/support/analyzeHeadless \
  /tmp/ghidra_synth_test SynthTest \
  -import tests/data/serial16550_synth.sys \
  -overwrite -deleteProject 2>&1 | tail -5
```
Expected: Ghidra imports and auto-analyzes without errors.

**Step 5: Commit the builder and generated .sys**

```bash
git add tests/data/build_synthetic_drivers.c tests/data/serial16550_synth.sys
git commit -m "Add synthetic 16550 driver .sys for Ghidra validation

Standalone PE builder generates serial16550_synth.sys (~3KB) with:
- UART_INIT, UART_SEND, UART_RECV (hardware, 16550 port I/O)
- DriverEntry (scaffolding, should be filtered)
- HAL.dll imports (READ/WRITE_PORT_UCHAR)
- ntoskrnl.exe import (IoCompleteRequest, scaffolding)"
```

---

### Task 4: Ghidra export script

**Files:**
- Create: `tools/ghidra/ExportSemanticReport.java`

**Step 1: Write the Ghidra post-analysis script**

```java
/* ExportSemanticReport.java — Ghidra headless post-analysis script
 *
 * Exports a JSON semantic report for pipeline validation.
 * Identifies: port I/O operations, hardware functions, imports,
 * scaffolding functions.
 *
 * Usage: analyzeHeadless ... -postScript ExportSemanticReport.java <output.json>
 */

import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import ghidra.program.model.address.*;
import java.io.*;
import java.util.*;

public class ExportSemanticReport extends GhidraScript {

    /* Port I/O opcodes (x86): IN AL,imm8 = 0xE4, OUT imm8,AL = 0xE6,
     * IN AL,DX = 0xEC, OUT DX,AL = 0xEE */
    private static final Set<Integer> PORT_IN_OPCODES = Set.of(0xE4, 0xEC);
    private static final Set<Integer> PORT_OUT_OPCODES = Set.of(0xE6, 0xEE);

    /* Hardware-related imports (from HAL.dll) */
    private static final Set<String> HW_IMPORTS = Set.of(
        "READ_PORT_UCHAR", "READ_PORT_USHORT", "READ_PORT_ULONG",
        "WRITE_PORT_UCHAR", "WRITE_PORT_USHORT", "WRITE_PORT_ULONG"
    );

    /* Scaffolding imports */
    private static final Set<String> SCAFFOLDING_IMPORTS = Set.of(
        "IoCompleteRequest", "IoCreateDevice", "IoDeleteDevice",
        "KeInitializeEvent", "KeSetEvent"
    );

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String outputPath = args.length > 0 ? args[0] : "/tmp/semantic_report.json";

        /* ... iterate functions, detect IN/OUT instructions,
         * classify imports, write JSON ... */

        PrintWriter pw = new PrintWriter(new FileWriter(outputPath));
        pw.println("{");
        pw.println("  \"schema_version\": 1,");
        /* ... build JSON output ... */
        pw.println("}");
        pw.close();

        println("Semantic report written to: " + outputPath);
    }
}
```

The full implementation must:
1. Iterate `currentProgram.getFunctionManager().getFunctions(true)`
2. For each function, iterate instructions via `getInstructionAt()`/`getInstructionAfter()`
3. Check opcode bytes for 0xE4, 0xE6, 0xEC, 0xEE (port I/O)
4. For immediate port ops (0xE4/0xE6), extract port number from next byte
5. Walk external symbols for import classification
6. Build JSON arrays for port_operations, hardware_functions, imports, scaffolding_functions
7. Include binary metadata (filename, image base, format)

**Step 2: Test the script with Ghidra headless**

Run:
```bash
mkdir -p tools/translator/tests/data/fixtures
JAVA_HOME=/snap/ghidra/35/usr/lib/jvm/java-21-openjdk-amd64 \
  /snap/ghidra/35/ghidra_12.0_PUBLIC/support/analyzeHeadless \
  /tmp/ghidra_test GhidraTest \
  -import tools/translator/tests/data/serial16550_synth.sys \
  -postScript ExportSemanticReport.java \
    tools/translator/tests/data/fixtures/serial16550_synth.ghidra.json \
  -scriptPath tools/ghidra \
  -overwrite -deleteProject 2>&1 | tail -10
```
Expected: `Semantic report written to: .../serial16550_synth.ghidra.json`

**Step 3: Inspect the generated JSON**

Verify it contains:
- `port_operations` with ports 0xF8, 0xF9, 0xFA, 0xFB, 0xFD
- `hardware_functions` with UART_INIT, UART_SEND, UART_RECV
- `imports` with READ_PORT_UCHAR, WRITE_PORT_UCHAR from HAL.dll
- `scaffolding_functions` with DriverEntry (if Ghidra discovers it)

**Step 4: Commit the Ghidra script**

```bash
git add tools/ghidra/ExportSemanticReport.java
git commit -m "Add Ghidra headless export script for semantic reports

Java script for analyzeHeadless that exports JSON with:
port operations, hardware functions, imports, scaffolding.
Used by make ghidra-fixtures to generate validation fixtures."
```

---

### Task 5: Generate and commit the JSON fixture

**Files:**
- Create: `tools/translator/tests/data/fixtures/serial16550_synth.ghidra.json`

**Step 1: Run Ghidra headless to generate the fixture**

(Same command as Task 4, Step 2 — but now we're committing the output.)

**Step 2: Validate the JSON is well-formed**

Run: `python3 -c "import json; json.load(open('tools/translator/tests/data/fixtures/serial16550_synth.ghidra.json'))"`
Expected: No errors.

**Step 3: Commit the fixture**

```bash
git add tools/translator/tests/data/fixtures/serial16550_synth.ghidra.json
git commit -m "Add Ghidra-generated fixture for serial16550_synth.sys

JSON semantic report: ports, hardware functions, imports.
Committed so make test works without Ghidra installed."
```

---

### Task 6: Comparison test — minimal JSON parser and semantic comparison

**Files:**
- Create: `tools/translator/tests/test_ghidra_compare.c`

**Step 1: Write the comparison test**

The test needs a minimal JSON parser. Since the schema is flat and predictable (arrays of objects with string values), a hand-rolled parser targeting just our schema fields is sufficient. It does NOT need to be a general JSON parser.

Key structures:
```c
typedef struct {
    char port[16];
    char direction[8];   /* "read" or "write" */
    char function[64];
} ghidra_port_op_t;

typedef struct {
    char name[64];
    char classification[32];
    char ports_accessed[8][16];
    int port_count;
} ghidra_hw_func_t;

typedef struct {
    char dll[64];
    char function[64];
    char category[32];
} ghidra_import_t;

typedef struct {
    int schema_version;
    ghidra_port_op_t port_ops[64];
    int port_op_count;
    ghidra_hw_func_t hw_funcs[16];
    int hw_func_count;
    ghidra_import_t imports[32];
    int import_count;
    char scaffolding_names[16][64];
    int scaffolding_count;
} ghidra_report_t;
```

Comparison logic:
1. Parse `serial16550_synth.ghidra.json` into `ghidra_report_t`
2. Load `tests/data/serial16550_synth.sys` as a buffer
3. Call `translate_buffer()` with `TARGET_FORTH`
4. For each `ghidra_report.port_ops[i].port`, verify that port hex value appears in Forth output (as `CONSTANT REG-XX` or in a port I/O reference)
5. For each `ghidra_report.hw_funcs[i].name`, verify that name appears as `: <NAME>` in Forth output
6. For each `ghidra_report.scaffolding_names[i]`, verify that name does NOT appear as `: <NAME>` in Forth output
7. Verify `REQUIRES: HARDWARE` appears (HAL.dll port I/O imports detected)

Tests:
- `test_all_ghidra_ports_found_in_forth` — no port false negatives
- `test_all_ghidra_hw_funcs_found_in_forth` — no function false negatives
- `test_scaffolding_filtered_out` — scaffolding not in Forth output
- `test_hal_imports_generate_requires` — REQUIRES: HARDWARE present

**Step 2: Build and run the comparison test**

Run:
```bash
cd /home/bbrown/projects/forthos/tools/translator
gcc -Wall -Wextra -Wpedantic -O2 -std=c11 -D_POSIX_C_SOURCE=200809L \
    -Isrc -Iinclude -DTRANSLATOR_NO_MAIN \
    tests/test_ghidra_compare.c \
    src/main/translator.c \
    src/loaders/pe_loader.c \
    src/decoders/x86_decoder.c \
    src/ir/uir.c \
    src/ir/semantic.c \
    src/codegen/forth_codegen.c \
    -o build/tests/test_ghidra_compare
./build/tests/test_ghidra_compare
```
Expected: All 4 tests pass.

**Step 3: Commit the comparison test**

```bash
git add tests/test_ghidra_compare.c
git commit -m "Add Ghidra comparison test for semantic validation

Loads cached .ghidra.json fixture, runs translator on same .sys,
compares: ports found, hardware functions kept, scaffolding filtered.
Asymmetric: translator must find everything Ghidra found."
```

---

### Task 7: Makefile integration

**Files:**
- Modify: `tools/translator/Makefile`

**Step 1: Add new targets**

Add after the `test-16550` target (around line 160):

```makefile
# Ghidra headless analyzer configuration
GHIDRA_JAVA_HOME = /snap/ghidra/35/usr/lib/jvm/java-21-openjdk-amd64
GHIDRA_HEADLESS = JAVA_HOME=$(GHIDRA_JAVA_HOME) \
    /snap/ghidra/35/ghidra_12.0_PUBLIC/support/analyzeHeadless

# Build synthetic .sys test binaries
.PHONY: build-synth
build-synth: | $(BUILDDIR)
	@mkdir -p $(BUILDDIR)/tests
	$(CC) $(CFLAGS) -o $(BUILDDIR)/tests/build_synth \
		tests/data/build_synthetic_drivers.c
	./$(BUILDDIR)/tests/build_synth tests/data/

# Regenerate Ghidra fixtures (requires Ghidra installed)
.PHONY: ghidra-fixtures
ghidra-fixtures: build-synth
	@echo "$(CYAN)Generating Ghidra fixtures...$(NC)"
	@mkdir -p tests/data/fixtures
	$(GHIDRA_HEADLESS) /tmp/ghidra_fixture GhidraFixture \
		-import tests/data/serial16550_synth.sys \
		-postScript ExportSemanticReport.java \
			tests/data/fixtures/serial16550_synth.ghidra.json \
		-scriptPath ../../tools/ghidra \
		-overwrite -deleteProject
	@echo "$(GREEN)Ghidra fixtures generated$(NC)"

# Ghidra comparison test (uses cached fixtures, no Ghidra needed)
.PHONY: test-ghidra-compare
test-ghidra-compare: | $(BUILDDIR)
	@echo "$(CYAN)Testing Ghidra comparison...$(NC)"
	@mkdir -p $(BUILDDIR)/tests
	$(CC) $(CFLAGS) -DTRANSLATOR_NO_MAIN -o $(BUILDDIR)/tests/test_ghidra_compare \
		tests/test_ghidra_compare.c \
		$(SRCDIR)/main/translator.c \
		$(SRCDIR)/loaders/pe_loader.c \
		$(SRCDIR)/decoders/x86_decoder.c \
		$(SRCDIR)/ir/uir.c \
		$(SRCDIR)/ir/semantic.c \
		$(SRCDIR)/codegen/forth_codegen.c
	./$(BUILDDIR)/tests/test_ghidra_compare
```

**Step 2: Add test-ghidra-compare to the test-all target**

Change line 175:
```makefile
test-all: test-pe test-x86 test-uir test-semantic test-forth-codegen test-pipeline test-16550 test-ghidra-compare
```

**Step 3: Run make test to verify all targets work**

Run: `make clean && make && make test`
Expected: 76 existing tests + 4 new Ghidra comparison tests = 80 total, all pass.

**Step 4: Commit Makefile changes**

```bash
git add Makefile
git commit -m "Add ghidra-fixtures and test-ghidra-compare to Makefile

make ghidra-fixtures: regenerate JSON fixtures (needs Ghidra)
make test-ghidra-compare: compare translator vs Ghidra (no Ghidra)
make test now includes Ghidra comparison in the full suite."
```

---

### Task 8: End-to-end verification

**Step 1: Full clean build and test from scratch**

```bash
cd /home/bbrown/projects/forthos/tools/translator
make clean && make && make test
```
Expected: All tests pass (80 total).

**Step 2: Verify make ghidra-fixtures works**

```bash
make ghidra-fixtures
```
Expected: Ghidra runs headless, regenerates the fixture, output matches committed fixture.

**Step 3: Verify the translator output against hand-written reference**

```bash
./bin/translator -t forth -n SERIAL-16550 tests/data/serial16550_synth.sys > /tmp/pipeline_output.fth
diff <(grep 'CONSTANT\|C@-PORT\|C!-PORT' /tmp/pipeline_output.fth | sort) \
     <(grep 'CONSTANT\|C@-PORT\|C!-PORT' ../../forth/dict/serial-16550.fth | sort)
```
Expected: Port constants and I/O patterns overlap significantly (not identical — the synthetic binary uses low-byte ports 0xF8-0xFD while the reference uses full 0x3F8-0x3FF with base+offset).

**Step 4: Update project docs with Phase B status**

Add to the "Current state" section:
- Phase B validation framework: synthetic .sys builder, Ghidra export script, cached JSON fixtures, comparison test. 80 tests total.

**Step 5: Final commit**

```bash
git add docs/
git commit -m "Update project memory with Phase B validation framework status"
```
