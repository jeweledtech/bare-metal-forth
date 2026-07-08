# Finding: ARM64 virt dispatch fault — 2026-07-07

## Context

Phase C.1 of the metacompiler: switching the ARM64
boot test from raspi3b (broken TCP serial) to QEMU
virt machine (reliable PL011). target-arm64.fth was
parameterized with board-config variables (A64- prefix),
VIRT-CONFIG/RASPI3B-CONFIG, and BUILD-ARM64-VIRT/
BUILD-ARM64-RASPI entry words.

## Observation table

| Register | Value | Meaning |
|----------|-------|---------|
| PC | 0x0000000000000200 | EL1 sync vector (no handler) |
| ELR | 0x401A1FA4 | Faulting instruction (~648KB past 8KB image) |
| ESR | 0x2000000 | EC=0 Undefined Instruction, IL=1 (32-bit) |
| X25 (PSP) | 0x4013FFFC | Data stack init'd, one push each — |
| X26 (RSP) | 0x4014FFFC | consistent with fault inside single DOCOL nesting |
| X27 (IP) | 0x40101CB4 | Forth IP, offset 0x1CB4 in image |
| X3 | 0x09000000 | UART base — init completed |
| X0 | 0x00000090 | Working register |
| PSTATE | 0x3C5 | EL1h, FPU disabled |

Image: 8028 bytes at 0x40100000 (virt, past DTB).
Build: BUILD-ARM64-VIRT, 147 symbols.

## Thread at IP (0x40101CB4)

```
+1CB0: 0x40100D90  XT (KEY)
+1CB4: 0x40100344  XT (DUP)      <-- IP
+1CB8: 0x4010013C  XT (LIT)
+1CBC: 0x0000000D  literal 13 (CR)
+1CC0: 0x401007BC  XT (=)
+1CC4: 0x40100394  XT
+1CC8: 0x4010013C  XT (LIT)
+1CCC: 0x0000000A  literal 10 (LF)
```

This is the interpreter's CR-comparison code.

## Static decodes (verified correct)

**DOCOL** at 0x100:
```
STR W27,[X26,#-4]!    push IP to return stack
ADD X27,X0,#4          IP = XT + 4 (body start)
LDR W0,[X27],#4        NEXT: load XT
LDR W1,[X0,#0]         load code pointer
BR X1                  dispatch
```

**LIT** at 0x13C:
```
LDR W0,[X27],#4        load literal from IP
STR W0,[X25,#-4]!      push to data stack
LDR W0,[X27],#4        NEXT: load next XT
LDR W1,[X0,#0]         load code pointer
BR X1                  dispatch
```

**DUP** at 0x344:
```
LDR W0,[X25,#0]        peek TOS
STR W0,[X25,#-4]!      push copy
LDR W0,[X27],#4        NEXT
LDR W1,[X0,#0]
BR X1
```

All have correct inline NEXT with IP post-increment.

## Killed hypotheses

1. **Alignment fault** — ESR EC=0 (undefined instr),
   not EC=0x25 (data abort). Not an alignment issue.
2. **DOLIT bug** — LIT runtime decodes correct: two
   LDR-post-index (literal + NEXT XT), push, dispatch.
3. **Jumped through garbage RAM** — QEMU zero-inits
   RAM. 0x401A1FA4 doesn't exist in the image AND
   can't be read from zeroed memory (that yields 0,
   BR to 0 would fault at PC=0, not 0x401A1FA4).

## Narrowed search space

Only two sources for 0x401A1FA4 remain:

1. **Computed**: an arithmetic path producing a wild
   value — EXIT restoring a corrupted return-stack
   cell, DOCOL fed a bad X0, off-by-N in a body
   address calculation.

2. **Device-region read**: an LDR through an address
   in MMIO space (e.g., PL011 at 0x09000000). Reading
   UART registers as dictionary cells returns nonzero
   junk that decodes to wild addresses.

## DTB collision (fixed)

QEMU virt places DTB at 0x40000000-0x40100000.
Initial A64-ORG=0x40000000 caused ROM overlap error.
Fixed: A64-ORG=0x40100000 clears the DTB. Committed
to private repo as fbd17fa.

## Key insight

The virt switch did its job. This bug was always in
the ARM64 target — raspi3b's broken interactive serial
path was hiding it. "Boot verified" on raspi3b meant
banner-only: the kernel ran far enough to print "ok"
but never executed interactive Forth deep enough to
hit this dispatch fault.

## Next session: decisive experiment

```
qemu-system-aarch64 -M virt -cpu cortex-a57 -m 256M \
  -device loader,file=<img>,addr=0x40100000 \
  -device loader,addr=0x40100000,cpu-num=0 \
  -serial tcp::4593,server=on,wait=off \
  -d in_asm,int -D /tmp/qemu-exec.log \
  -display none
```

The **last in_asm block before the first Taking
exception line** names the exact faulting BR dispatch
site. Subtract 0x40100000 for the image offset.

Also verify: is ELR truly 0x401**A**1FA4 (0xA1FA4
past image) or 0x4010**1**FA4 (0x1FA4, just 72 bytes
past the 8028-byte image end)? The in_asm log settles
this — one nibble, two different diagnoses.

## Queued follow-ups

1. Run the in_asm experiment — names the faulting
   instruction in one QEMU run
2. VBAR_EL1 crash-reporting stub: emit ESR/ELR/X27
   out UART so ARM64 faults self-report instead of
   requiring monitor probes
3. Embed boundary assertion (token-stream-end
   measurement still owed from the shutdown regression)
