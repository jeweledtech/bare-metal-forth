# LMI (Laboratory Microsystems Inc.) Reference

## Status: PENDING PHYSICAL MANUAL RECOVERY

A physical LMI manual is believed to be in storage and is a priority
archival target. Do not implement the ASM/DISASM vocabulary until this
manual has been recovered and reviewed.

## Background

Laboratory Microsystems Inc. (LMI) produced some of the most
sophisticated commercial Forth implementations from the late 1970s
through the 1990s. Their products included:

- **UR/Forth** — their flagship x86 Forth system
- **LMI Forth** — earlier versions for various platforms
- Laboratory and scientific extensions for instrumentation control

### Customer Base

LMI's customer base included organizations with demanding real-time
and scientific computing requirements:

- **NASA Jet Propulsion Laboratory (JPL)** — spacecraft and instrument control
- **Caltech** — scientific computing and laboratory automation
- **Industrial control laboratories** — real-time process control
- **Defense contractors** — embedded systems

This customer profile validates the technical depth of their tools.
When JPL trusts your assembler for spacecraft code, that assembler has
been battle-tested at the highest level.

## The ASM Vocabulary

LMI's `ASM` vocabulary was a complete x86 assembler embedded in the
Forth interpreter. This is architecturally different from our current
`X86-ASM` vocabulary, which emits bytes into a target buffer for
cross-compilation.

### How CODE...END-CODE Works in LMI

In LMI Forth, `CODE` creates a new dictionary entry and switches the
interpreter into assembly mode. The assembler words (`MOV,` `PUSH,`
`POP,` etc.) emit machine code directly into the live dictionary at
`HERE`. `END-CODE` terminates the assembly and switches back to
normal interpretation.

```forth
CODE MY-DOUBLE  ( n -- 2n )
    EAX POP,
    EAX EAX ADD,
    EAX PUSH,
    NEXT,
END-CODE
```

After `END-CODE`, `MY-DOUBLE` is immediately executable — no separate
compilation or linking step. The machine code lives in the dictionary
alongside Forth colon definitions.

### Key Differences from Our X86-ASM

| Feature | LMI ASM | Our X86-ASM |
|---------|---------|-------------|
| Target | Live dictionary (HERE) | Separate buffer (T-HERE) |
| Execution | Immediately executable | Requires META-COMPILER |
| Register syntax | `EAX POP,` | `%EAX POP,` |
| Context | CODE...END-CODE | Standalone assembler |
| Labels | Built-in forward references | None yet |
| Control flow | `IF,` `ELSE,` `THEN,` etc. | None |

### Assembler Word Patterns

LMI used postfix notation for assembler instructions:

```forth
\ Operand(s) then instruction
EAX PUSH,          \ PUSH EAX
EAX EBX MOV,       \ MOV EBX, EAX (note: reversed from Intel syntax)
# 42 EAX MOV,      \ MOV EAX, 42 (immediate)
EAX 0 [EBP] MOV,   \ MOV [EBP+0], EAX (memory)
```

### Structured Assembler Control Flow

One of LMI's most powerful innovations was structured control flow at
the assembly level, mirroring Forth's high-level control structures:

```forth
CODE CHECK-ZERO  ( n -- flag )
    EAX POP,
    EAX EAX TEST,
    0= IF,
        # -1 EAX MOV,    \ TRUE
    ELSE,
        # 0 EAX MOV,     \ FALSE
    THEN,
    EAX PUSH,
    NEXT,
END-CODE

CODE COUNT-DOWN  ( n -- )
    EAX POP,
    BEGIN,
        EAX DEC,
        0= UNTIL,
    NEXT,
END-CODE
```

The assembler control flow words (`IF,` `ELSE,` `THEN,` `BEGIN,`
`UNTIL,` `WHILE,` `REPEAT,`) handle branch offset calculation
automatically, including forward references. This eliminated the
most error-prone aspect of hand-written assembly.

## The DISASM Vocabulary

LMI's `DISASM` vocabulary provided live memory disassembly at the
Forth prompt:

```forth
' MY-DOUBLE DISASM    \ Disassemble a single word
$7E00 $7E40 DISASM-RANGE  \ Disassemble address range
```

### How This Differs from SEE

Our kernel's `SEE` decompiles at the Forth level — it walks the
threaded code and prints word names. LMI's `DISASM` worked at the
machine code level — it decoded x86 instructions and printed
assembly mnemonics.

| Feature | Our SEE | LMI DISASM |
|---------|---------|------------|
| Level | Forth threaded code | x86 machine code |
| Output | Word names | Assembly mnemonics |
| Scope | Colon definitions only | Any memory address |
| Use case | Understanding Forth words | Debugging CODE words, kernel |

For our project, `DISASM` would be invaluable for:
- Verifying CODE words emit correct machine code
- Debugging kernel primitives
- Validating the binary translator's output
- Inspecting driver code extracted from Windows binaries

## What to Extract When Manual Is Recovered

Priority information to capture from the physical LMI manual:

1. **Complete ASM word list** — every assembler mnemonic and its
   stack effect
2. **Addressing mode syntax** — how they handle all x86 modes
   (register, immediate, memory, SIB)
3. **DISASM implementation** — how they decode instructions
4. **Label system** — how forward references work
5. **Structured control flow** — exact semantics of IF,/ELSE,/THEN,
   etc. at the assembly level
6. **CODE...END-CODE** protocol — how the dictionary entry is
   created and finalized
7. **Error handling** — what happens on invalid opcodes or
   addressing modes

## Connection to Our Architecture

Our system currently has:
- `X86-ASM` vocabulary — opcode emitters to a target buffer
- `META-COMPILER` — builds a new kernel image using X86-ASM
- `SEE` — Forth-level decompiler

What we're missing (and LMI perfected):
- `CODE...END-CODE` in Forth — assemble directly into dictionary
- Structured assembler control flow
- Forward reference labels
- Machine-level disassembly

The LMI pattern would bridge our current X86-ASM (cross-compiler
oriented) with live-in-dictionary assembly (the traditional Forth
approach). Both have their place: X86-ASM for building kernel
images, LMI-style ASM for defining hardware primitives at runtime.

## References

- LMI was founded by Ray Duncan in the late 1970s
- UR/Forth was their primary x86 product
- The Forth Interest Group (FIG) archives may contain LMI documentation
- Charles Moore's colorForth uses a different but related approach
  to inline assembly
