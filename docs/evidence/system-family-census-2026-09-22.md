# The system-instruction family: a decode census (2026-09-22)

**Why it was measured** (owner ruling): direct access to control, debug and
model-specific registers is this product's stated subject. The park census
had met 12 `mov %cr8` stops in one driver. That could have been an accident
of which drivers touch CR8, so the family was counted across the whole
corpus before any decoder work was decided.

**Method.** Each binary's code section is extracted (PE `.text`, Mach-O
`__TEXT,__text` from the x86_64 slice) and swept linearly by the shipped
decoder in 64-bit mode. Every instruction whose encoding falls in the
family is recorded with the identity the decoder gave it. A hit counts only
where objdump, sweeping the same bytes, puts an instruction of the same kind
at the same offset. Scripts live outside every repository, in
`~/corpus/tools-2026-09-22/`: `decode_family.c` `3a407267`, `fam_agg.py`
`3225dfd8`, `extract_text.py` `b0ca38f6`.

**The family, fixed before counting**, from the SDM's system-instruction
chapter and the decoder's own case comments:

- **Two-byte forms:** group 6 (`0F 00`), group 7 (`0F 01`, split by ModRM),
  `0F 05`–`09`, **the CR/DR moves `0F 20`–`23`**, `0F 30`–`35` and `37`,
  `CPUID`, `RSM`, `VMREAD`/`VMWRITE`, and the system forms of `0F C7`.
- **One-byte forms:** `HLT`, `CLI`, `STI`, `IRET`, `IN`, `OUT`, `INS`,
  `OUTS`. The decoder names most of these, so they were meant as the control
  that the counter tells named from unnamed.
- `0F AE` (fences, XSAVE) was counted separately as adjacent, not system.

## 1. The two-byte family is entirely unnamed, and it is in most drivers

| machine | two-byte system instructions | UNKNOWN | distinct forms | drivers with any | drivers with a CR/DR move |
|---|---|---|---|---|---|
| HP | 195 | **195 (100%)** | 1 | 7 of 8 | 7 |
| Dell | 5,375 | **5,375 (100%)** | 23 | 383 | 26 |
| ASUS (older) | 5,968 | **5,968 (100%)** | 24 | 228 | 204 |
| ASUS (newer) | 7,030 | **7,030 (100%)** | 58 | 436 | 46 |
| Mac (control) | 8 | 8 | 2 | 3 | **0** |

**By group:**
- **Dell:** CR/DR moves 3,378; CPUID/XGETBV 1,700; MSR/TSC 272;
  descriptor tables 12; VMX 9.
- **ASUS (older):** CR/DR 5,453; MSR/TSC 268; CPUID/XGETBV 221; descriptor
  tables 16; VMX 8.
- **ASUS (newer):** CR/DR 4,038; CPUID/XGETBV 1,943; VMX 562; MSR/TSC 405;
  descriptor tables 76.
- **HP:** all 195 are `mov %cr8` reads.

The widest single driver is `aehd.sys` on ASUS (newer): moves to or from CR0,
CR2–CR4 and DR0–DR3/DR6/DR7, VMXON through VMXOFF, and LGDT/LIDT. The full per-form lists are in
`fam-summary`, which is regenerable from the scripts above.

**Decision (owner's rule):** a real group across drivers, not twelve stops
in `mlx4_bus`. So it is **its own item with its own reds**. It is opened, and
it does not jump the queue: the lifter repair is still next.

## 2. The 26 / 204 / 46 spread is the Windows build, not the vendor

Three machines whose driver sets are mostly the same inbox binaries should
not differ nearly 8× in how many drivers contain a CR/DR move. **The
intersection** (drivers matched by name across the three non-HP machines):

| machine | drivers with a CR/DR move | same name on both others, CR/DR there too | same name on both others, CR/DR **only here** | unique to this machine | on one other |
|---|---|---|---|---|---|
| Dell | 26 | 23 | 0 | 0 | 3 |
| ASUS (older) | 204 | 23 | **165** | 8 | 8 |
| ASUS (newer) | 46 | 23 | 0 | 13 | 10 |

**The spread is carried by 165 drivers on ASUS (older) that exist under the
same name on all three machines, and 165 of 165 are byte-different from
their namesakes.** So the count is not counting the same thing on each
machine. The file-version resources of those 165 say why:

| machine | build of the 165 | the 165 importing an IRQL routine |
|---|---|---|
| HP (its 8) | **10.0.19041** (8 of 8) | 7 of 8 |
| ASUS (older) | **10.0.19041** (162 of 165) | 74 of 165 |
| ASUS (newer) | **10.0.22621** (161 of 165) | 165 of 165 |
| Dell | **10.0.26100** (161 of 165) | 165 of 165 |

On the Windows 10 build (19041), reading the IRQL compiles inline as
`mov %cr8`. On the Windows 11 builds (22621, 26100), the same drivers import
an IRQL routine instead. **The instructions are real and the count stands,
but it is Windows-build-shaped.** It measures which kernel headers the
drivers were built against.

**This applies beyond this census.** The four machines are **three Windows
builds**: HP and ASUS (older) are the same build, and ASUS (newer) and Dell
are two different Windows 11 builds. Every per-machine comparison in this
arc, the park census included, is also a comparison of Windows builds. The
vendor axis and the build axis are confounded in this corpus and cannot be
separated with it.

## 3. The control failed, and that is the most transferable result here

**The one-byte forms were meant as the control.** Instead they show that
the cross-check can fail. The Mac set is `/usr/bin` userland, which cannot
execute `CLI`, `STI` or `HLT`; they fault at ring 3. Yet the census
"confirmed" these by objdump, at the same offset, in Mac userland:

| Mac, one-byte form | "confirmed" | in files |
|---|---|---|
| `STI` | 1,677 | 132 |
| `CLI` | 1,160 | 127 |
| `OUT` | 824 | 129 |
| `IN` | 678 | 108 |
| `HLT` | 401 | 81 |

**Those are not instructions.** Objdump and the shipped decoder agreed
because both **linear sweeps misread the same data bytes in the same way**.
A linear sweep that meets data decodes it; two linear sweeps meeting the
same data decode it identically, and their agreement looks exactly like
two instruments confirming each other. On Windows the same effect is
visible in `INS`/`OUTS` (11,055 / 18,143 on Dell): `6C`–`6F` are the ASCII
letters `l`–`o`.

**The condition, stated so it can be checked for elsewhere:** *agreement
between two linear sweeps at the same offset is not evidence when the bytes
may not be code.* The two instruments share the failure mode, so on those
bytes they are one instrument. The cross-check has been read as two
independent instruments since the Ghidra oracle was pinned. The oracle is
flow-following, so it does not share this failure; objdump's linear sweep
does. **This is the first measured case where the linear cross-check does
not hold.**

**Where the condition holds, a census needs a third source** (a
flow-following disassembler, or unwind/function-table coverage), **or a
reason at section level to believe the bytes are instructions at all.**

**Why the two-byte result survives it:** the same Mac control shows **0**
CR, DR or MSR moves among 21.2 million swept instructions. A multi-byte
system encoding (`0F 20 C3`, with a ModRM that names a real control
register) rarely assembles itself from data, and it did not here. This is
reasoned from the control, not proven for every Windows hit: the one-byte
counts are withdrawn, and the two-byte counts stand on the control's zero.

> **Correction, 2026-09-23 (`sdm-banking-2026-09-23.md`):** the SDM is now banked (325462-092). This family was not drawn from the system-instruction chapter alone: its VMX, SYSCALL/SYSENTER, MSR, CPUID, MONITOR/MWAIT, CLAC/STAC, GETSEC and RDRAND/RDSEED entries come from other chapters. Checked against Table 2-3 (Vol. 3A §2.8), three encodings the family names are **misnamed** (`F3 0F 09` WBNOINVD prints `wbinvd`; `F2`/`F3 0F 01 CA` ERETS/ERETU print `clac`), which is red `(bd)`, and four Table 2-3 instructions are unnamed, which is `(be)`.
