Project Memory:

Purpose & context
Jolly Genius Inc (jeweledtech on GitHub) is developing two interconnected systems: Bare-Metal Forth, a bare-metal Forth-83 operating system designed for space missions and critical systems, and a Universal Binary Translator for cross-platform executable analysis and translation. The project philosophy centers on the "ship builder's mindset" - prioritizing radical simplicity, reliability, and outcome-based engineering over convenience features. The OS is conceptualized as ship's systems software for long-duration space missions, emphasizing zero external dependencies and direct hardware control.
The target collaborators are professionals with backgrounds in space sciences, physics, embedded systems, and critical infrastructure - people willing to commit to serious, long-term technical work rather than casual contributors. Success is measured by creating production-quality systems that can operate independently without underlying OS layers or external dependencies.

Current state (as of 2026-02-23)
The Bare-Metal Forth system is FULLY FUNCTIONAL with block storage, vocabularies, and source loading. All 34 automated tests pass. 178+ dictionary words (added 2OVER). Kernel builds at 33280 bytes. Phase C complete: DOCREATE fix, block loading improvements, catalog-resolver committed and integration test passing (5/5). The system has been pushed to https://github.com/jeweledtech/bare-metal-forth.

Build: `make clean && make` produces bmforth.img (512-byte bootloader + 32KB kernel = 33280 bytes).
Test: `qemu-system-i386 -drive file=build/bmforth.img,format=raw,if=floppy -serial tcp::4444,server=on,wait=off -display none` then connect to TCP port 4444 for serial console.
Block storage test: `make blocks && make run-blocks` boots with IDE slave block disk attached.

Working features (verified by tests):
- 177 dictionary words including all core stack ops, arithmetic, logic, memory access
- Forth-83 floored division semantics (all sign combinations verified)
- Word definitions with : and ; (simple and nested: SQUARE, CUBE, QUADRUPLE)
- IF/ELSE/THEN control flow
- BEGIN/WHILE/REPEAT, BEGIN/UNTIL, BEGIN/AGAIN loops
- DO...LOOP with I index access (counted loops, nested loops)
- CONSTANT and VARIABLE defining words
- BASE/STATE accessible from Forth code (BASE @ ., STATE @ .)
- .S displays stack bottom-to-top (Forth convention)
- Serial I/O (COM1 0x3F8) for QEMU -nographic testing
- VGA text mode output (0xB8000) for bare-metal display
- Ctrl+C break handler with full state save/restore (ESP, EBP, STATE, HERE, LATEST)
- SP@ and SP! diagnostic words for stack pointer inspection
- WORDS lists all dictionary entries
- SEE decompiles words
- ATA PIO block storage: BLOCK, BUFFER, UPDATE, SAVE-BUFFERS, EMPTY-BUFFERS, FLUSH
- Source loading from blocks: LOAD, LIST, THRU, --> (chain-load)
- Vocabulary/search-order system: VOCABULARY, DEFINITIONS, ALSO, PREVIOUS, ONLY, FORTH, ORDER, USING
- BLK and SCR system variables for block I/O state

Architecture details:
- Register usage: ESI = Instruction Pointer (IP), EBP = Return Stack, ESP = Data Stack, EAX = working/TOS
- NEXT macro: lodsd; jmp [eax] (Direct Threaded Code)
- Memory map: kernel at 0x7E00, data stack at 0x10000, return stack at 0x20000, dictionary at 0x30000, VGA at 0xB8000
- System vars at 0x28000 (STATE, HERE, LATEST, BASE, TIB, TOIN)
- Block/vocab vars at 0x28018 (BLK, SCR, SEARCH_ORDER[8], SEARCH_DEPTH, CURRENT, FORTH_LATEST)
- Block buffer headers at 0x28060 (4 x 12 bytes), TIB at 0x28100, block buffers at 0x28200 (4 x 1KB)
- DEFCODE/DEFWORD/DEFVAR/DEFCONST macros build dictionary entries
- cold_start loop: INTERPRET, BRANCH, -8 (infinite interpreter loop)
- ATA PIO uses IDE slave (0xF0 in drive register, QEMU -drive if=ide,index=1)
- Block buffers: 4-slot LRU cache, each header = [block#(4)][flags(4)][age(4)], flags bit0=valid bit1=dirty

Block storage design:
- Each Forth block = 1KB = 2 ATA sectors. LBA = block# * 2. Lines are 64 chars padded with spaces (NO newlines).
- LOAD saves TIB/TOIN/BLK/ESI on return stack, redirects INTERPRET to block buffer. VAR_BLOCK_LOADING flag (0x2804C) prevents premature block exhaustion: LOAD sets flag=1, INTERPRET clears it on first entry and starts parsing. When TOIN=0 + BLK!=0 + flag=0, block is truly exhausted.
- `\` and `(` comment words check VAR_BLK: in block mode, `\` advances TOIN to next 64-byte boundary; `(` scans the block buffer for `)`. In interactive mode, they read from serial as before.
- tools/write-block.py writes host text files into block disk images in 16x64 screen format.
- tools/write-catalog.py scans forth/dict/ for .fth files, computes block layout, writes catalog to block 1 and all vocabs to blocks 2+.
- CRITICAL: All .fth source lines MUST be ≤ 64 characters. Longer lines are silently truncated in block format, causing mysterious parse errors (e.g., `THEN` becomes `THE`).

Vocabulary/search-order design:
- find_ walks VAR_SEARCH_ORDER[0..depth-1], each entry is address of a vocab's LATEST cell.
- find_ has FORTH fallback: if word not found in search order, always tries FORTH vocabulary last — prevents core words from becoming invisible when search order changes.
- create_ links new words into [VAR_CURRENT] vocabulary and also updates global VAR_LATEST.
- At boot: search order = [VAR_FORTH_LATEST], depth=1, identical to pre-vocabulary single-chain behavior.
- DOVOC runtime: vocabulary words replace top of search order when executed.
- USING = ALSO + execute-vocab-word (friendly syntax for "USING GRAPHICS").

Universal Binary Translator status (as of 2026-02-25): Phase A COMPLETE, Phase B validation framework COMPLETE, parametric codegen COMPLETE. The driver extraction pipeline produces parametric Forth words with correct stack effects from HAL IAT calls. A PE binary can be fed through `translator -t forth driver.sys` and a complete Forth vocabulary source file comes out with real word bodies (e.g., `( port -- byte ) C@-PORT`) instead of empty stubs. 91 tests across 8 suites, all passing. Validated end-to-end against real i8042prt.sys: 9 hardware functions → 9 parametric Forth words with C@-PORT, C!-PORT, US-DELAY, DPC-QUEUE, IRQ-CONNECT bodies.

Phase B validation framework: Ghidra serves as the oracle ("measuring stick, not mechanism"). A synthetic 16550 UART driver PE (serial16550_synth.sys, ~3KB) is processed by both Ghidra and the translator. Ghidra's headless analyzer (ExportSemanticReport.java) exports a JSON semantic report (port operations, hardware functions, imports, scaffolding). The comparison test (test_ghidra_compare.c) validates that the translator finds everything Ghidra found (asymmetric: no false negatives, but translator may find more). JSON fixtures are cached in the repo so `make test` works without Ghidra installed. `make ghidra-fixtures` regenerates them when needed.

Pipeline components (all in tools/translator/):
- PE Loader (src/loaders/pe_loader.c): Parses PE32/PE32+ headers, sections, imports, exports. Resolves RVAs to raw pointers.
- x86 Decoder (src/decoders/x86_decoder.c): Table-driven, 55+ instruction types, ModR/M+SIB, two-byte 0x0F prefix, all condition codes. ~1100 lines.
- UIR Lifter (src/ir/uir.c): Three-pass algorithm — collect branch targets, create blocks, link edges. IN/OUT → UIR_PORT_IN/UIR_PORT_OUT with port preserved. ~400 lines.
- Semantic Analyzer (src/ir/semantic.c): 100+ Windows driver API entries classified as hardware (PORT_IO, MMIO, DMA, TIMING, INTERRUPT, PCI_CONFIG) or scaffolding (IRP, PNP, POWER, etc.). Each API entry carries arg_count/ret_count for HAL function signatures. Functions with port I/O or hardware API calls kept; scaffolding filtered. IAT cross-reference records matched HAL calls (sem_hal_call_t) with full signature info for codegen. ~320 lines.
- Forth Code Generator (src/codegen/forth_codegen.c): Generates vocabulary source matching serial-16550.fth pattern — catalog header with REQUIRES:, register constants, base variable/accessors, function words. Parametric codegen: HAL calls produce words with correct stack effects (e.g., C@-PORT → `( port -- byte )`, C!-PORT → `( byte port -- )`). Multi-HAL functions get per-call stack effect comments. ~310 lines.
- Pipeline Integration (src/main/translator.c): translate_buffer() wires all five stages. Supports -t disasm, -t uir, -t forth. CLI -s/-i/-e flags print PE info.

Key architecture decisions:
- Bridge structs (uir_x86_input_t, sem_pe_import_t, sem_uir_input_t) keep components decoupled without circular header dependencies. Each component compiles and tests independently.
- API recognition table duplicated in semantic.c (from driver_extract.c) for self-containment — conscious trade-off.
- driver-extract stub headers replaced with redirects to translator's canonical implementations (pe_loader.h, x86_decoder.h, uir.h).

Build/test: `cd tools/translator && make clean && make` builds the translator. `make test` runs all 91 tests across 8 suites. Individual: `make test-pe`, `make test-x86`, `make test-uir`, `make test-semantic`, `make test-forth-codegen`, `make test-pipeline`, `make test-16550`, `make test-ghidra-compare`.

tools/floored-division has complete 3-arch codegen with tests.

Key bugs fixed in latest session (11 bugs total):
1. word_ TOIN off-by-one: lodsb advanced ESI past NUL terminator in TIB buffer, causing reads of stale data from previous commands. Fix: dec esi in .end_word.
2. /MOD floored division: checked quotient sign (eax) instead of remainder sign (edx) against divisor. Only failed when dividend positive, divisor negative.
3. ELSE compilation: xchg trick left BRANCH instruction address instead of offset address on stack for THEN to patch. Rewrote with clean pop/push.
4. DO/LOOP/+LOOP compiled code_XXX (native code address) instead of XXX (XT/code field address). NEXT needs double indirection: lodsd gets XT, jmp [eax] reads code field.
5. LOOP reserved an uninitialized 4-byte cell after the backward offset, putting garbage between loop and EXIT. Removed spurious add HERE, 4.
6. DOCON used lodsd (reads ESI = instruction stream) instead of [eax+4] (reads parameter field via XT). Constants returned wrong values.
7. S" and ." overwrote DOSQUOTE XT with string length. Fixed by reserving a length cell between XT and string data.
8. DEFVAR created private storage (var_STATE etc.) but kernel used EQU addresses (VAR_STATE = 0x28000). Forth code and kernel read different locations. Fixed DEFVAR to push EQU address directly.
9. .S printed top-to-bottom instead of standard bottom-to-top. Reversed iteration.
10. .S had no depth cap; corrupted ESP caused thousands of zeros. Added cap at 64.
11. serial_getchar used test al,al (ZF) which broke on NULL characters. Changed to clc/stc (CF).

Critical DTC Forth lesson: In threaded code, compiled cells must contain the XT (code field address), NOT the native code address. NEXT does lodsd to get XT, then jmp [eax] reads through the code field. Only the code field of a word header (first cell) should contain the native code address.

Key bugs fixed in block loading session (2026-02-21, 6 bugs):
12. THRU DOLOOP backward offset: was -12 (wrong), needed -16. DOLOOP does `lodsd; add esi,eax` — lodsd advances ESI 4 bytes past the offset cell BEFORE adding the offset. So the offset must account for this extra 4 bytes. With -12, the loop branched to LOAD (skipping I), causing LOAD to pop garbage from the data stack and load a random block, which set STATE=1. THIS WAS THE ROOT CAUSE of all THRU failures.
13. LOAD was a no-op: INTERPRET saw TOIN=0 + BLK!=0 and immediately triggered block_exhausted before any block content was processed. Fix: added VAR_BLOCK_LOADING flag (0x2804C). LOAD sets flag=1. INTERPRET: if TOIN=0 + BLK!=0 + flag=1, clears flag and starts parsing.
14. `\` comment in block mode called read_key: would hang waiting for serial input. Fix: check VAR_BLK, advance TOIN to next 64-byte boundary in block mode.
15. `(` comment in block mode called read_key: same issue. Fix: scan block buffer for `)` when in block mode.
16. THRU off-by-one: Forth DO excludes the limit, so `2 5 THRU` only loaded blocks 2-4. Fix: added INCR (1+) to include last block.
17. find_ lost core words: executing a vocabulary word replaces ORDER[0]; with depth=1, the entire search order becomes the (possibly empty) new vocabulary. Fix: FORTH fallback in find_ always searches FORTH as last resort.

Key bugs fixed in Phase C session (2026-02-22, 1 bug):
18. CREATE missing CFA: create_ builds dictionary headers (link, flags+len, name, align) but does NOT write a CFA. COLON and CONSTANT manually write their CFA after create_, but CREATE (the Forth word) did not — so VARIABLE (which uses CREATE) wrote 0 at the CFA position as its "initial value". Executing such a variable did `jmp [0]` → crash at EIP=0x7. Fix: added DOCREATE runtime (`lea eax,[eax+4]; push eax; NEXT`) and modified CREATE to write `code_DOCREATE` as default CFA. This also fixes any word built with CREATE...DOES> or CREATE...ALLOT patterns.

Critical CREATE/CFA lesson: In DTC Forth, every executable word needs a CFA as its first cell. The helper `create_` only builds the header (link, flags, name) — it does NOT write a CFA. Any defining word that calls `create_` must write its own CFA: COLON writes DOCOL, CONSTANT writes code_DOCON, CREATE writes code_DOCREATE. The CFA determines runtime behavior: DOCOL enters colon defs, DOCON pushes value at [CFA+4], DOCREATE pushes address of [CFA+4].

Critical DOLOOP offset lesson: When computing backward branch offsets in hand-written DEFWORD bodies, the offset is calculated from ESI AFTER lodsd (= offset_cell_address + 4), NOT from the offset cell itself. For `dd I / dd LOAD / dd DOLOOP / dd offset / dd EXIT`: to branch back to I, offset = I_position - (offset_position + 4). The LOOP compilation word calculates this correctly (`sub ebx, ecx; sub ebx, 4`), but hand-written offsets must match.

Critical BRANCH vs DOLOOP difference: BRANCH uses `add esi, [esi]` (reads offset without advancing ESI). DOLOOP uses `lodsd; add esi, eax` (advances ESI past offset, then adds). This means BRANCH offset = target - offset_cell, while DOLOOP offset = target - (offset_cell + 4). cold_start's `dd -8` is correct for BRANCH.

Key bugs fixed in four-features session (2026-03-04, 1 bug):
19. BEGIN/WHILE/REPEAT backward branch offset: UNTIL, AGAIN, and REPEAT all had `sub ebx, 4` when calculating backward branch offsets, but BRANCH uses `add esi, [esi]` (no lodsd), so the offset should be `target - offset_cell` without the extra -4. The -4 was incorrectly copied from DO/LOOP's offset calculation (DOLOOP uses `lodsd; add esi, eax` which DOES advance ESI). This caused every compiled word using BEGIN/WHILE/REPEAT, BEGIN/UNTIL, or BEGIN/AGAIN to branch 4 bytes before the intended target — typically into DOCOL or a prior instruction, crashing the system. Fix: removed `sub ebx, 4` from all three words.

Phase C COMPLETE (catalog-resolver, 2026-02-23):
- catalog-resolver.fth written, restructured for block loading: all lines ≤64 chars, `?DO` replaced with guarded `DO` (kernel lacks `?DO`), `3+`/`4+`/.../`8+` replaced with `3 +`/`4 +`/.../`8 +` (kernel lacks N+ for N>2), mutual recursion (RESOLVE-DEPS ↔ LOAD-VOCAB-INNER) resolved via `VARIABLE 'RESOLVE-DEPS` deferred execution pattern.
- 2OVER added to kernel (was missing, needed by catalog-resolver).
- write-catalog.py tool created: scans forth/dict/ for .fth files, builds catalog block (block 1), writes all vocabs to sequential blocks.
- test-catalog-resolver.sh integration test: 5/5 passing (arithmetic, BLOCK/WORDS, catalog listing, THRU loading, ORDER display).
- DOCREATE fix verified: `VARIABLE TESTVAR` / `42 TESTVAR !` / `TESTVAR @ .` → 42. Full `2 17 THRU` loads catalog-resolver from blocks successfully.

Completed milestones
- Block storage with ATA PIO driver and 4-buffer LRU cache (2026-02-15)
- Vocabulary/search-order system with USING syntax (2026-02-15)
- Source loading from blocks: LOAD, THRU, --> (2026-02-15)
- Reference analysis of Andy Valencia's ForthOS in docs/REFERENCES.md (2026-02-15)
- Driver extraction pipeline Phase A complete (2026-02-21): PE loader, x86 decoder, UIR lifter, semantic analyzer, Forth codegen — all wired end-to-end with 76 tests passing
- Hand-written 16550 UART reference vocabulary (forth/dict/serial-16550.fth) — serves as the "gold standard" for pipeline output validation
- Phase C COMPLETE: catalog-resolver committed, integration test 5/5 passing, DOCREATE fix applied. Full THRU loads from clean boot (2026-02-23).
- Phase B validation framework COMPLETE: Ghidra-as-oracle with hybrid fixture approach. Synthetic .sys builder, headless export script, JSON fixtures, asymmetric comparison test. 80 tests total (2026-02-23).
- Parametric HAL codegen COMPLETE: sem_api_entry_t carries arg_count/ret_count, IAT cross-reference records sem_hal_call_t, codegen emits parametric Forth words. Validated against i8042prt.sys: 9 functions with C@-PORT/C!-PORT/US-DELAY/DPC-QUEUE/IRQ-CONNECT bodies. 91 tests total (2026-02-25).
- Four-features implementation (2026-03-04): Interrupt infrastructure (IDT+PIC+ISR), 6 driver vocabularies, block editor, x86 assembler, metacompiler. BEGIN/WHILE/REPEAT kernel bug fixed (bug #19). Integration test 16/16 passing. Makefile test targets added (`make test`).

On the horizon
Phase B stretch goal — Real-world validation: Find ReactOS's serial.sys driver (GPL, real 16550 UART hardware), run `make ghidra-fixtures` on it, run the comparison test, iterate until the Forth output captures the same hardware semantics. This is the "proof of concept" moment.

Validation framework details:
- Ghidra headless: `JAVA_HOME=/snap/ghidra/35/usr/lib/jvm/java-21-openjdk-amd64 /snap/ghidra/35/ghidra_12.0_PUBLIC/support/analyzeHeadless`
- Export script: `tools/ghidra/ExportSemanticReport.java` — JSON with port ops, hw functions, imports, scaffolding
- Fixture: `tools/translator/tests/data/fixtures/serial16550_synth.ghidra.json` — schema_version 1, extensible
- Comparison: asymmetric — translator must find everything Ghidra found, but may find more
- `make ghidra-fixtures` regenerates, `make test` uses cached fixtures (no Ghidra needed)

Other key development areas: block editor (Vi-like screen editor for blocks), metacompiler (two-pass bootstrap following ForthOS pattern — see docs/REFERENCES.md), expanding architecture portability beyond x86 (Pi/ARM64 is a priority).
User has expressed interest in: CPU detection via CPUID for installer lookup tables, Raspberry Pi boot (SD/SSD adapter), and the fact that most PCs are x86-compatible (Apple Silicon is ARM64, not 68000).
Community feedback (Facebook Forth group, 2026-02-15): Andy Valencia's ForthOS confirmed as key reference, QEMU validated as right environment, expert runs colorForth on real 386/486 hardware.

Driver development methodology (from stakeholder meeting 2026-02-17):
1. Mind-map the hardware — document port addresses, register layouts, command sequences
2. Mind-map the software — what the program/driver does, which subsystems it accesses
3. Name the interfaces — each subsystem becomes a Forth word (e.g., DISK-READ, MOUSE-POSITION)
4. Define the workflow — describe operations as natural language steps; each step becomes a word with testable state (on/off, safe/not safe, zeroed/not zeroed)
5. Bridge hardware and software — connect workflow words to port I/O words
6. Wrap in a VOCABULARY — standard pattern:
```
VOCABULARY SERIAL-PORT
SERIAL-PORT DEFINITIONS
HEX
3F8 CONSTANT COM1-BASE
: COM1-STATUS ( -- byte ) COM1-BASE 5 + INB ;
: COM1-SEND ( char -- ) BEGIN COM1-TX-READY? UNTIL COM1-BASE OUTB ;
FORTH DEFINITIONS
```
Usage: main program says "USING SERIAL-PORT", "USING PRINTERS", "USING VGA-DISPLAY". Omit a USING line to drop that subsystem entirely and save space.

Vocabulary catalog header convention: Every .fth vocabulary file starts with a structured comment block (\ CATALOG:, \ CATEGORY:, etc.). Dependencies use `\ REQUIRES: <vocab-name> ( word1 word2 ... )` format — one line per dependency, listing the specific words consumed. This is the `apt` model: vocabularies share base primitives through dependencies rather than bundling copies. The resolver (Phase C) will auto-load dependencies; Phase A just emits the metadata. See docs/plans/2026-02-21-driver-extraction-pipeline-design.md for full spec.

Driver decompilation workflow (connects UIR translator to Forth OS dictionaries):
1. Load driver binary: `translator -t forth -a driver.sys`
2. Semantic analysis categorizes functions (VIDEO, DISK, NETWORK)
3. Filter out Windows kernel scaffolding, keep hardware protocol (port I/O, register ops)
4. Generate Forth vocabulary from UIR output
5. Load vocabulary into Forth, redefine words as needed, save as new dictionary version

Priority driver sequence for QEMU:
- P1: Serial port (16550 UART, COM1 0x3F8-0x3FF) — host communication, dictionary transfer
- P1: PIT Timer (i8254, 0x40-0x43) — cooperative multitasking, delays, watchdog
- P2: PS/2 Mouse (i8042 aux, 0x60/0x64) — GUI interaction
- P2: PCI Bus enumeration (0xCF8/0xCFC) — device discovery
- P3: NE2000 Network (ne2k_pci) — network communication, dictionary sharing
- P3: VGA Graphics (Bochs VBE, 0x01CE-0x01CF + framebuffer) — graphical output

Key learnings & principles
The project has validated that Forth-83's floored division semantics require special handling since most CPUs use symmetric division - the correction must check (remainder XOR divisor) < 0 to detect when symmetric division gave the wrong result, then adjust: quotient -= 1, remainder += divisor.
The "ship builder's manifesto" principle has proven effective as both a technical guideline and collaborator filter. Direct hardware access without HAL layers is achievable and provides the control needed for critical systems applications.
State save/restore philosophy: "best way is to save an image before interpreting a new file or command set - then restore it if ctrl C escapement is triggered so that the system returns to stable." This is implemented via save_esp/save_ebp/save_state/save_here/save_latest snapshots before each read_line.

Critical ATA PIO lesson: rep insw (read) uses EDI only (safe), but rep outsw (write) clobbers ESI which is our Forth IP. Any DEFCODE calling ata_write_sector must PUSHRSP esi / POPRSP esi. Same pattern as CMOVE.
Critical LOAD lesson: LOAD redirects the interpreter by changing VAR_TIB and VAR_TOIN. VAR_BLOCK_LOADING flag distinguishes "block just set up" from "block exhausted" when TOIN=0 AND BLK!=0. State restore pops TIB/TOIN/BLK/ESI from return stack. Nested LOAD works because each pushes its own state.
Critical vocabulary lesson: find_ must dereference TWO levels — search order entry is the *address* of a LATEST cell (e.g. VAR_FORTH_LATEST), then that cell contains the actual word pointer. create_ must update BOTH the current vocab's LATEST cell AND the global VAR_LATEST (needed by ; IMMEDIATE etc.).
Critical block-mode lesson: Any word that reads from serial/keyboard (read_key) MUST check VAR_BLK and handle block mode differently. Known words requiring this: `\` (skip to next 64-byte boundary), `(` (scan block buffer for `)`). S" and ." were also fixed to read from TIB instead of read_key (works for both interactive and block mode). The full THRU "hang" turned out to be a CRASH caused by missing CFA in CREATE'd words (bug #18), not a read_key issue.
QEMU testing pattern: Use Bash `run_in_background: true` to start QEMU, then separate Bash calls for Python test scripts. Backgrounding with `&` in regular Bash calls often causes silent failures. Always `pkill -9 -f qemu || true` before starting new instances. Use unique TCP ports per test to avoid conflicts. Verify port is listening with `ss -tlnp | grep PORT` before connecting.
Dictionary chain management: when adding new DEFCODE/DEFWORD entries, the NASM `link` macro variable auto-threads them. But kernel_start must set VAR_LATEST and VAR_FORTH_LATEST to name_XXXX of the LAST defined word. Check with: grep for last DEF* entry in forth.asm.
Forth source constraints for block loading: (1) all lines ≤ 64 chars, (2) no forward references (Forth compiles top-down), (3) mutual recursion needs VARIABLE + EXECUTE deferred pattern, (4) kernel lacks `?DO` — use `DUP 0> IF 0 DO ... LOOP ELSE DROP THEN`, (5) `N+` words for N>2 don't exist — use `N +`.

Critical pipeline lessons (2026-02-21):
- Bridge struct pattern: uir_x86_input_t mirrors x86_decoded_t field-for-field but lives in uir.h, breaking circular dependency. Cost is a field-by-field copy in the pipeline glue, but each component compiles and tests independently.
- open_memstream() for string output: when print functions write to FILE* but you need the output as a string (e.g. for translate_buffer returning char*), open_memstream gives a dynamically-allocated buffer. Requires _POSIX_C_SOURCE 200809L.
- typeof() is not portable in C11 with -Wpedantic — use direct field access instead.
- Header redirect pattern: when consolidating duplicate type definitions across directories, redirect headers with unique guards (#ifndef DRV_PE_LOADER_COMPAT_H) and compatibility typedefs avoid guard conflicts with the canonical headers.
- Three-pass UIR lifting: (1) scan for branch targets, (2) create blocks splitting at targets and lift instructions, (3) link blocks with fall-through/branch edges. This avoids forward-reference problems where a branch target hasn't been seen yet.
- IN/OUT with immediate port vs DX register: immediate port (E4/E6) has the port in the instruction byte; DX port (EC/EE) has the port in the DX register at runtime, which can't be statically resolved. The lifter records uses_dx_port=true for these cases.

Phase B validation lessons (2026-02-23):
- Ghidra headless via snap requires explicit JAVA_HOME pointing to bundled JDK: `/snap/ghidra/35/usr/lib/jvm/java-21-openjdk-amd64`. System Java version mismatch causes "unsupported java version" error.
- Ghidra's GhidraScript API: `currentProgram.getListing().getInstructionAt()` then `.getInstructionAfter()` to walk instructions. `.getBytes()` returns raw opcode bytes for IN/OUT detection.
- Asymmetric oracle testing: validate completeness (no false negatives) without requiring exactness (allowing false positives from the translator finding more). This avoids noise from the decoder handling opcodes Ghidra represents differently.
- JSON fixture schema versioning: `schema_version` field enables forward-compatible evolution. New comparison dimensions (register patterns, data flow) added as new top-level arrays without breaking old fixtures.
- Synthetic PE as committed test artifact: deterministic ~3KB binary serves both Ghidra and translator, anyone can `make test` without the builder or Ghidra.

Parametric codegen lessons (2026-02-25):
- HAL function signatures are well-known from the Windows DDK: READ_PORT_UCHAR(1 arg, 1 ret), WRITE_PORT_UCHAR(2 args, 0 ret), etc. Encoding these in the API table makes the semantic analyzer the single source of truth for both classification and calling convention.
- Bridge struct pattern extends to codegen: sem_hal_call_t (semantic) → forth_hal_call_t (codegen) keeps components decoupled. Each pipeline stage has its own struct type.
- Dual-counter bug: when adding a new array field (hal_calls) alongside an existing counter (hw_call_count), the recording code incremented the old counter but never set the new hal_call_count field. Unit tests passed because they constructed inputs directly with correct counts, but the real driver path went through sem_function_t where hal_call_count stayed 0. Lesson: when a struct has an array + count pair, always keep them in sync at the point of insertion.
- Stack effect mapping from cdecl to Forth: READ_PORT_UCHAR(PUCHAR Port) → `( port -- byte )`, WRITE_PORT_UCHAR(PUCHAR Port, UCHAR Value) → `( byte port -- )`. The Forth convention puts the address on top (matching `value addr C!`), which reverses the cdecl argument order.
- Synthetic test drivers use direct IN/OUT instructions (port ops path), not IAT-based HAL calls. Real Windows drivers call HAL functions through the IAT. Both paths must be tested independently — unit tests for HAL path, synthetic PE for port ops path, real drivers for end-to-end validation.

Dictionary sharing pattern: historically, Forth developers zipped dictionaries, shared them, recipients unzipped/ran/evaluated/edited to create customized versions. One developer might have an optimized single-printer driver, another a thousand-printer universal driver — both interchangeable. This is the model for GitHub-based dictionary distribution.
Dictionary versioning: when redefining words, save the current dictionary as a revision (block range) before modifying. Enables rollback. Add to Phase 1 after MARKER/FORGET.
Cross-compilation via "sister interpreter": Forth can run an interpreter that operates in the host environment but interprets as if running on a different architecture. When transferred, code goes as a "refactored file" ready for native execution. This is exactly what the UIR pipeline does, described from the practitioner side.
Multi-CPU parallel processing: CPUs have addresses and ports. A Forth word can distribute work across 4/6/12 CPUs by loading data into each CPU's port, checking completion, pulling results back. Cooperative multitasking at hardware level, not OS-mediated threading. Phase 4 task switching should use direct port-level CPU targeting.
Memory swapping: if memory is insufficient, chunk programs and swap to/from disk with temp files. Loop: load new piece -> preserve current piece to temp -> zero out -> load new content. Estimated ~40ms on modern hardware. Maps to existing BLOCK/BUFFER words.
"Room packets" concept: originated at Borland International, adopted in Windows 95/98. Chunking strategy for modular program execution — program broken into loadable segments individually swapped in/out of memory. Maps directly to Forth's block-based architecture. Dictionary vocabularies are composable modules.
Forth and AI potential: writing AI in Forth is natural because dictionary definitions are already structured as natural language words. Not an immediate priority, but worth noting for future phases.
Performance confirmation: "A computer that would not be able to run Windows can easily run a Forth operating environment." Forth runs in a fraction of Linux's space. Validates the ship systems mission for minimal hardware.

Approach & patterns
Development follows a systematic five-phase roadmap from Genesis through Production deployment. Technical implementation uses Direct Threaded Code interpretation for real-time compilation capabilities, with assembly-language kernels providing primitives that extend through Forth definitions.
The binary translator employs a multi-stage pipeline: binary format parsing (PE/ELF) -> intermediate representation -> optimization passes -> target architecture code generation.
Collaboration strategy targets specific communities (Forth enthusiasts, space systems developers, embedded systems engineers) rather than general programming audiences.

Tools & resources
Primary development tools: NASM assembler, QEMU emulator, gcc, make, git, python3. All installed on the development machine (Linux).
Build: `make` in project root. Test: launch QEMU with serial TCP, connect with Python script or netcat.
Block storage: `make blocks` creates 1MB disk, `make run-blocks` boots with it, `python3 tools/write-block.py build/blocks.img <block#> <file>` writes source.
GitHub repo: https://github.com/jeweledtech/bare-metal-forth (remote: origin)
Project directory: /home/bbrown/projects/forthos
IMPORTANT: Do not add AI/Claude/Anthropic attribution to git commits.
Worktree convention: use `.worktrees/` directory (gitignored) for feature branch isolation.
Regression testing: start QEMU on a TCP port, send Forth commands via Python socket, check output contains expected results. Port numbers should be unique per test run to avoid conflicts from lingering QEMU processes. Kill with `pkill -f "qemu.*bmforth"` if needed.
Kernel size check: `python3 -c "with open('build/kernel.bin','rb') as f: d=f.read()" ...` find last non-zero byte to get actual code size vs 32KB padded.

Project Instructions:

Taking into account what we've built in the Initial Build conversation: 
The biggest problems with this project are: 1. It requires someone that has written Operating systems before and is familiar with the various microprocessor architecture. 2. The person also needs to be familiar with the Forth 83 standard language and has been able to run it on window's 95 or other non HAL protected-OS'es. The forth that I'm after can compile and execute running code in real time. Not, stop the program -> recompile -> then restart. The earlier forth could write directly to live memory in the buffers and execute code instantly. That is part of what I'm after here. Forth uses RPN (Reverse Polish Notation) so it takes info like the CPU and its registers do. So we want to be able to get around the HAL issues with Windows 98 and-on and the registry piece of crap among other things in this design. It should just run direct forth OS code. No linux layer, no windows layer, no Apple layer. Clean from scratch starting with machine code. Direct BIOS communications with the various CPUs out there now, that may be a major undertaking to ensure you get the right instruction set. And the extended instruction set that is available on some of these devices. Ideally, we would have a transcode table for different processors and the forth OS would build itself for that CPU. But that would assume having a version of this specific OS already running.

When forth loaded you would tell it what dictionary to use using Amiga, using Linux, using Telecom 85. All of which were forth code files that loaded the library collection of definitions. Forth would take, moveax <address from> <address to>  and it pops and pushes onto registers directly (modem, network card, video GPU, ...). The feature we want to build is that you can directly edit any memory address, pointer or register in the system directly. Which is of course dangerous if you don't know what you are doing. The main solution we are after is where this comes in handy is reading a file on a drive, de-compiling it into a translatable version for use on a different CPU (cross-interpreter stuff) that would make moving programs out of windows and onto any other mapped language possible. You could also build an analyzer that could say, "video dll code", "disc access code" ... and name the DLL content as a threaded library. Please reference the "chat gpt produced.docx" for an example. Imagine being able to map the dot-net dll collection and remove all insecurity crap from it so you can just call it like a regular DLL - treat it as a plug and play code module which is what we used to be able to do.
