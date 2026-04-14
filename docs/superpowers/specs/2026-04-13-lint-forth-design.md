# lint-forth.py — Unified Forth Source Validator

**Date**: 2026-04-13
**Location**: `tools/lint-forth.py` in the public kernel repo (`~/projects/forthos`)

## Context

ForthOS has five documented constraints that produce silent failures — no error messages, wrong values, or crashes at unrelated locations. All five bugs have been fixed in the kernel, but nothing prevents a vocabulary author or kernel developer from reintroducing them. This tool catches all five at build time, before code reaches QEMU.

## Interface

```bash
# Lint vocabulary files (checks #1 + #2)
python3 tools/lint-forth.py forth/dict/*.fth

# Lint kernel assembly (checks #3 + #4 + #5)
python3 tools/lint-forth.py --asm src/kernel/forth.asm

# Both at once
make lint
```

Exit code 0 = all clear. Exit code 1 = errors found.

## Five Checks

### Check 1: Line Length (vocabulary mode)

**Bug**: Lines > 64 chars are silently truncated in block format. `THEN` becomes `THE`.

**Implementation**: For each `.fth` file, check every line. Error on any line > 64 characters. Report the line number, actual length, and show the truncation point.

**Output**:
```
forth/dict/ps2-mouse.fth:42: ERROR line is 71 chars (max 64)
  | : SET-WIDTH  640 XMAX !  480 YMAX !  12 PACKET-SIZE ! ;
  |                                                         ^^^^^^^
```

### Check 2: BASE Tracking (vocabulary mode)

**Bug**: `HEX` and `DECIMAL` are runtime words, not IMMEDIATE. Numeric literals in colon definitions are parsed using whatever BASE is active at compile time, not when the word executes. `640` after `HEX` is silently parsed as 0x640 (1600 decimal).

**Implementation**: Simulate BASE state through the file:
- Default BASE = 10 (`DECIMAL`)
- Track `HEX` (sets BASE=16) and `DECIMAL` (sets BASE=10) as top-level statements
- Track colon definition state (`:` opens, `;` closes)
- Inside colon definitions, when BASE=16, flag numeric literals that contain only decimal digits (0-9) and are > 9 as warnings
- The heuristic: if it's all-decimal-digits and > 9, it probably wasn't meant as hex

**What this catches**: The real PS2-MOUSE bug — `640`, `480`, `12` inside a colon def after `HEX`.

**What this skips**: Legitimate hex constants like `3F8`, `FF`, `A0` (contain A-F digits). Also skips single-digit numbers (0-9 are the same in any base).

**Output**:
```
forth/dict/ps2-mouse.fth:42: WARN literal '640' in colon def while BASE=HEX
  | Will be parsed as 0x640 (1600). Define as CONSTANT outside colon def.
```

### Check 3: DTC Threading (assembly mode)

**Bug**: Compiled cells in DEFWORD bodies must contain the XT (code field address via `name_*` labels), not the native code address (`code_*` labels). Using `code_*` skips the double indirection that NEXT expects.

**Implementation**: Parse DEFWORD blocks in `forth.asm`. For each `dd` directive, extract the symbol. Flag any `dd code_*` reference.

**Known safe patterns to skip**:
- `dd 0` — initial values
- `dd LIT` followed by a numeric `dd` — the number after LIT is data, not an XT
- Raw negative numbers like `dd -8` — branch offsets
- Raw positive numbers — loop offsets, counts

**Output**:
```
src/kernel/forth.asm:1684: ERROR DEFWORD VARIABLE uses 'dd code_CREATE' (should be 'dd CREATE')
```

### Check 4: CREATE CFA Verification (assembly mode)

**Bug**: `create_` only builds the dictionary header. Every defining word must write its own CFA. If CREATE doesn't write `code_DOCREATE`, variables and CREATE'd words crash with `jmp [0]`.

**Implementation**: Find the `DEFCODE "CREATE"` block. Verify it contains a store of `code_DOCREATE` to `[eax]` or `[VAR_HERE]`. This is already fixed (bug #18) but the check prevents regression.

**Output**:
```
src/kernel/forth.asm: OK — CREATE writes code_DOCREATE at line 1131
```

### Check 5: Branch Offset Validation (assembly mode)

**Bug**: BRANCH uses `add esi, [esi]` (offset = target - offset_cell). DOLOOP uses `lodsd; add esi, eax` (offset = target - offset_cell - 4). Wrong offset calculations cause branches to wrong locations.

**Implementation**: For hand-written DEFWORD bodies (those containing DOLOOP, DOPLOOP, BRANCH, or ZBRANCH):
1. Build an ordered list of `dd` entries in the body
2. Identify branch instructions (DOLOOP, DOPLOOP, BRANCH, ZBRANCH)
3. The `dd` immediately after a branch instruction is its offset
4. Calculate expected offset:
   - For DOLOOP/DOPLOOP: count cells from offset back to target, multiply by -4, subtract 4
   - For BRANCH/ZBRANCH: count cells from offset back to target, multiply by -4
5. Compare expected vs actual

**Scope**: Only validates hand-written DEFWORD bodies (like THRU). Compiled code (from `:` definitions at runtime) is already correct — the compilation words LOOP, REPEAT, UNTIL, AGAIN all calculate offsets correctly post-bug-19.

**Output**:
```
src/kernel/forth.asm:2513: OK — DEFWORD THRU: DOLOOP offset -16 is correct
```

## Integration

### Makefile targets

```makefile
lint:
	python3 tools/lint-forth.py forth/dict/*.fth
	python3 tools/lint-forth.py --asm src/kernel/forth.asm

test: lint test-smoke test-loops test-vocabs test-integration
```

`make lint` becomes a prerequisite of `make test`. Every test run validates source first.

### write-catalog.py integration

`write-catalog.py` imports lint-forth and runs vocabulary checks before writing blocks. If any file fails, the catalog write aborts:

```
$ python3 tools/write-catalog.py build/blocks.img forth/dict/
Linting ahci.fth... OK
Linting ps2-mouse.fth... FAILED
  ps2-mouse.fth:42: ERROR line is 71 chars (max 64)
Aborting: fix lint errors before writing catalog.
```

## File Structure

Single file: `tools/lint-forth.py` (~300-400 lines estimated).

Internal structure:
- `lint_fth_file(filepath)` — runs checks 1 + 2, returns list of errors/warnings
- `lint_asm_file(filepath)` — runs checks 3 + 4 + 5, returns list of errors/warnings
- `check_line_lengths(lines, filepath)` — check 1
- `check_base_tracking(lines, filepath)` — check 2
- `check_dtc_threading(asm_text, filepath)` — check 3
- `check_create_cfa(asm_text, filepath)` — check 4
- `check_branch_offsets(asm_text, filepath)` — check 5
- `main()` — CLI: parse args, dispatch to vocabulary or assembly mode

## Verification

1. Run `python3 tools/lint-forth.py forth/dict/*.fth` — all 13 existing vocabularies should pass clean (they were already written carefully)
2. Run `python3 tools/lint-forth.py --asm src/kernel/forth.asm` — kernel should pass clean (all bugs already fixed)
3. Create a test `.fth` file with deliberate violations (line > 64 chars, decimal literal after HEX in colon def) — verify the linter catches them
4. `make lint` exits 0 on clean codebase
5. `make test` now includes lint as first step
