# Floored Division for Forth-83 Semantics

## Overview

This package implements **floored (Euclidean) division** as required by the Forth-83 standard, for integration into:

1. **Universal Binary Translator** - Native code generation for x86-64, ARM64, and RISC-V
2. **Bare-Metal Forth Kernel** - Assembly primitives for bare-metal Forth

### The Problem

Most modern CPUs use **symmetric (truncated)** division where the quotient rounds toward zero. Forth-83 requires **floored** division where the quotient rounds toward negative infinity.

```
Example: -7 / 3

Symmetric (most CPUs):  quotient = -2, remainder = -1
Floored (Forth-83):     quotient = -3, remainder =  2

Both satisfy: dividend = quotient × divisor + remainder
But floored ensures: remainder has same sign as divisor (or is zero)
```

This difference only matters when dividend and divisor have opposite signs AND the division is not exact.

### Why Floored Division?

Floored division has mathematical advantages:

1. **Consistent modulo behavior** - The remainder always has the same sign as the divisor, which is useful for:
   - Hash table indexing
   - Modular arithmetic
   - Coordinate system wrapping
   - Time/calendar calculations

2. **Euclidean division** - Matches the mathematical definition more closely

3. **Forth-83 Standard** - Required for compliance with the Forth-83 specification that your project is targeting

## Files

| File | Purpose |
|------|---------|
| `floored_div.h` | Header with pure C reference implementation |
| `codegen_floored_x64.c` | x86-64 native code generation |
| `codegen_floored_arm64.c` | ARM64 native code generation |
| `codegen_floored_riscv64.c` | RISC-V 64-bit native code generation |
| `forth_division_primitives.asm` | Multi-architecture Forth kernel primitives |
| `test_floored_div.c` | Comprehensive test suite |

## Quick Start

### Build and Test

```bash
# Compile the test suite
gcc -o test_floored_div test_floored_div.c -Wall -Wextra -O2

# Run tests
./test_floored_div
```

Expected output:
```
Symmetric vs Floored Division Comparison
============================================================
Expression   | Symmetric (CPU)  | Floored (F83)    | Diff?
-------------|------------------|------------------|-------
   7 / 3     | q=2    r=1       | q=2    r=1       | no
  -7 / 3     | q=-2   r=-1      | q=-3   r=2       | YES
   7 / -3    | q=-2   r=1       | q=-3   r=-2      | YES
  -7 / -3    | q=2    r=-1      | q=2    r=-1      | no
...
✓ All tests passed - floored division is correct!
```

## Integration

### Universal Binary Translator

Add these UIR opcodes to `uir.h`:

```c
typedef enum {
    // ... existing opcodes ...
    UIR_FDIV    = 0x40,   // Floored division (Forth-83)
    UIR_FMOD    = 0x41,   // Floored modulo (Forth-83)
    UIR_FDIVMOD = 0x42,   // Combined floored div/mod
} uir_opcode_t;
```

In `codegen.c`, add cases for the new opcodes:

```c
#include "codegen_floored_x64.c"
#include "codegen_floored_arm64.c"
#include "codegen_floored_riscv64.c"

// In your compile_instruction switch:
case UIR_FDIV:
    if (cg->target == CODEGEN_TARGET_X64) {
        // Pop divisor to R10, dividend stays in RAX
        x86_emit_mov_reg_reg(&cg->code, X64_R10, X64_RAX);
        x86_emit_pop(&cg->code, X64_RAX);
        
        size_t needed = emit_floored_div_x64(NULL, 0);
        ensure_code_space(&cg->code, needed);
        cg->code.size += emit_floored_div_x64(
            cg->code.data + cg->code.size,
            cg->code.capacity - cg->code.size);
    }
    else if (cg->target == CODEGEN_TARGET_ARM64) {
        // ARM64: dividend in X0, divisor in X1
        arm64_emit_pop(&cg->code, 0);  // X0 = dividend
        arm64_emit_pop(&cg->code, 1);  // X1 = divisor
        
        cg->code.size += emit_floored_div_arm64(
            cg->code.data + cg->code.size,
            cg->code.capacity - cg->code.size);
            
        arm64_emit_push(&cg->code, 0);  // Push result
    }
    else if (cg->target == CODEGEN_TARGET_RISCV64) {
        // RISC-V: dividend in a0, divisor in a1
        riscv_emit_ld(&cg->code, RV_A0, 8, RV_SP);
        riscv_emit_ld(&cg->code, RV_A1, 0, RV_SP);
        riscv_emit_addi(&cg->code, RV_SP, RV_SP, 16);
        
        cg->code.size += emit_floored_div_riscv64(
            cg->code.data + cg->code.size,
            cg->code.capacity - cg->code.size);
            
        riscv_emit_addi(&cg->code, RV_SP, RV_SP, -8);
        riscv_emit_sd(&cg->code, RV_A0, 0, RV_SP);
    }
    break;
```

### Bare-Metal Forth Kernel

For the x86 bare-metal kernel, copy the `ARCH_X86` section from `forth_division_primitives.asm` into your `forth.asm` file. Make sure your `DEFWORD` and `NEXT` macros are defined.

If you're using the existing kernel structure:

```nasm
; In your forth.asm, after your other word definitions:

%include "forth_division_primitives.asm"
```

Or manually copy the `/`, `MOD`, `/MOD`, `*/`, and `*/MOD` definitions.

## Algorithm Explained

### Correction Logic

Given symmetric division results `(q, r)` from the CPU:

```
if r ≠ 0 AND sign(dividend) ≠ sign(divisor):
    q = q - 1
    r = r + divisor
```

This works because when we decrease the quotient by 1, we need to add the divisor back to the remainder to maintain the invariant:
```
dividend = quotient × divisor + remainder
```

### Code Size

| Architecture | DIV (bytes) | MOD (bytes) | DIVMOD (bytes) |
|--------------|-------------|-------------|----------------|
| x86-64 | ~30 | ~32 | ~36 |
| ARM64 | ~28 | ~28 | ~40 |
| RISC-V | ~28 | ~28 | ~40 |

The overhead versus raw hardware division is about 12-20 bytes per operation (for the test and correction).

## Forth-83 Division Words

The following Forth words use floored semantics:

| Word | Stack Effect | Description |
|------|--------------|-------------|
| `/` | ( n1 n2 -- q ) | Floored quotient |
| `MOD` | ( n1 n2 -- r ) | Floored remainder |
| `/MOD` | ( n1 n2 -- r q ) | Both remainder and quotient |
| `*/` | ( n1 n2 n3 -- q ) | n1×n2/n3 with 64-bit intermediate |
| `*/MOD` | ( n1 n2 n3 -- r q ) | Scaled with both values |

Note: Forth-83 uses 16-bit cells by default, but this implementation supports both 32-bit and 64-bit cell sizes.

## Unsigned Division

This package only implements **signed** floored division. For **unsigned** division, no correction is needed since there are no sign differences to handle. Use the CPU's native unsigned division instructions:

- x86: `DIV` (vs `IDIV`)
- ARM64: `UDIV` (vs `SDIV`)
- RISC-V: `DIVU` (vs `DIV`)

Forth-83's `U/` and `U/MOD` words should use unsigned division directly.

## References

1. **Forth-83 Standard** - Section on division semantics
2. **"Division and Modulus for Computer Scientists"** - Daan Leijen, 2003
3. **Philae lander Forth implementation** - ESA documentation on space-qualified Forth

## License

Copyright © 2026 Jolly Genius Inc.

Ship's Systems Software - Built for reliability, not convenience.

---

*"In the ship builder's tradition: measure twice, divide once, correct always."*
