# The SDM, banked and pinned, and its four dependents checked against it (2026-09-23)

**Owed since the system family** (register, *Not a defect letter, but
owed*). Four things rested on the manual's structure, recalled, with no copy
on disk: the system family, the SSE family, the pseudo-op class, and (bb)'s
ten contract exceptions. Every other oracle here is pinned: Ghidra by snap
revision, xnu by tag, the corpus by sha256. This closes the one unpinned
source.

## The pin

| | |
|---|---|
| document | Intel® 64 and IA-32 Architectures Software Developer's Manual, Combined Volumes 1, 2A–2D, 3A–3D, 4 |
| order number / revision | **325462-092** |
| document date | 2026-06-19 (PDF CreationDate) |
| sha256 | **`16a9336104750613ae2f2bab6eb7a1b21a7e1ef60ced35e9ab2e0d8c7efcec68`** |
| size | 26,664,910 bytes |
| fetched | 2026-09-23T16:21:05-07:00, `https://cdrdv2-public.intel.com/922475/325462-092-sdm-vol-1-2abcd-3abcd-4.pdf` (redirected from `https://cdrdv2.intel.com/v1/dl/getContent/671200`) |
| held at | `~/references/intel-sdm/`, **outside every repository**, with `SHA256SUMS` and `FETCHED` beside it. It is Intel's copyrighted document: like the corpus, it never enters a repo, and only this pin, the table numbers and short quotations are published |

Checks were run on a `pdftotext -layout` extraction of that file.

## 1. The pseudo-op class: identical

**Cited:** Vol. 2 Tables **3-9** (CMPPD), **3-11** (CMPPS), **3-13**
(CMPSD) and **3-15** (CMPSS), "Pseudo-Op and … Implementation", and Table
**4-15**, "Pseudo-Op and PCLMULQDQ Implementation".

**36 of 36 (instruction, imm8) pairs are identical** to `compare_operands.py`'s
table (`pseudo_sha256` `6ceb47ffeefb`), compared programmatically in both
directions with 0 differences. The VEX tables (3-10, 3-12, 3-14, 3-16),
which extend the predicates to 31, are outside the family by definition.

## 2. (bb)'s ten contract exceptions: all confirmed

Each was read on its own instruction page (Vol. 2):
- **COMISS, COMISD, UCOMISS, UCOMISD:** "sets the ZF, PF, and CF flags in
  the EFLAGS register … The OF, SF, and AF flags … are set to 0". The
  write set is flags only.
- **PTEST:** "set[s] the ZF flag … sets the CF flag". Flags only.
- **PCMPESTRI, PCMPISTRI:** "generates an index stored to the count
  register (ECX)".
- **PCMPESTRM, PCMPISTRM:** "a mask stored to XMM0".
- **MASKMOVDQU:** "the memory location specified by the effective address
  in the DI/EDI/RDI register".

**10 of 10: in each, operand 0 is not the complete register write set, so
it carries no `dest`**, as (bb) coded it.

## 3. The SSE family: every key attested, and the maps omit seven

**Cited:** Vol. 2 Appendix A, **A.2.1** "Codes for Addressing Method" (V,
U, W), and the opcode maps, Table **A-3** (two-byte), **A-4** (`0F 38`)
and **A-5** (`0F 3A`).

**Method.** The family was re-derived independently of the maps, from the
instruction reference pages: every legacy-encoded opcode row (no `VEX.`/
`EVEX.`) whose instruction form names an `xmm` operand. pdftotext
renders those rows inconsistently (lower-case `66 0f 38 20`, `23/r`
without a space), so two parsers were run and their union taken. Each one
alone misses rows that the other finds, which is why neither is used
alone.

- **All 270 keys are attested by the instruction pages.** 0 are missed by
  both parsers.
- **Seven legacy XMM encodings are on the instruction pages but outside
  the 270:**
  - GFNI: `66 0F 38 CF` GF2P8MULB, `66 0F 3A CE` GF2P8AFFINEQB,
    `66 0F 3A CF` GF2P8AFFINEINVQB;
  - Key Locker: `F3 0F 38 DC` AESENC128KL and LOADIWKEY (register form),
    `DD` AESDEC128KL, `DE` AESENC256KL, `DF` AESDEC256KL.
- **Tables A-4/A-5 in revision 092 do not list them.** The two tables'
  span (278 lines) contains PMOVSXBW, PSHUFB, AESENC, SHA1MSG1,
  SHA256RNDS2, PTEST, ROUNDPS, PCLMULQDQ, MOVBE, CRC32 and INVPCID, and
  **no** GF2P8* or *KL entry. That grep has a control: the names that should
  be there are found.

**So the family matches the maps as printed, and the maps are incomplete
against the manual's own instruction reference.** Stated as a correction of
my definition, not of the SDM's: *"entries of Tables A-3/A-4/A-5 with
V/U/W"* is narrower than *"legacy encodings with an XMM operand"*, by these
seven.

**Reach: 0 corpus rows**, over all seven sets on the post-(ba) sweep. That
is **zero measured, not zero found**: the same scan sees **21,349** other
unnamed `0F 38`/`0F 3A` rows (ADCX/ADOX `F6`, MOVBE/CRC32 `F0`/`F1`, INVPCID
`82`). It is recorded as `(be)`, open without a red, since there is no row
for a red to move.

## 4. The system family: not Table 2-3 alone, and Table 2-3 found a defect

**Cited:** Vol. 3A §2.8, Table **2-3** "Summary of System Instructions".

**The family was never Table 2-3 alone.** Its VMX entries, SYSCALL/SYSRET,
SYSENTER/SYSEXIT, RDMSR/WRMSR, CPUID, MONITOR/MWAIT, CLAC/STAC, GETSEC and
RDRAND/RDSEED come from other chapters. The census doc's *"from the SDM's
system-instruction chapter"* was loose, and is corrected here. The parse of
Table 2-3 has artefacts: footnote digits fused to names (`RDPMC4`), and
rows split across lines.

**Two-byte instructions in Table 2-3 that the family lacks:** LAR (`0F
02`), LSL (`0F 03`), INVPCID (`66 0F 38 82`), LKGS (`F2 0F 00 /6`), ERETS
(`F2 0F 01 CA`), ERETU (`F3 0F 01 CA`) and WBNOINVD (`F3 0F 09`). The rest
of the table's difference is one-byte forms (HLT, INT*, IRET) and ARPL,
already handled elsewhere. Decoded by the shipped decoder, with objdump
beside it:

| encoding | SDM / objdump | ours | length |
|---|---|---|---|
| `F3 0F 09` | WBNOINVD / `wbnoinvd` | **`wbinvd`** | right |
| `F2 0F 01 CA` | ERETS / `erets` | **`clac`** | right |
| `F3 0F 01 CA` | ERETU / `eretu` | **`clac`** | right |
| `F2 0F 00 F0` | LKGS / `lkgs` | `???` | right |
| `0F 02` / `0F 03` | LAR / LSL | `???` | right |
| `66 0F 38 82` | INVPCID | `???` | right |

**Three are wrong answers, not unknowns.** `system_identity()` does not
check the mandatory prefix at `0F 09` or `0F 01 CA`, so these print another
instruction's name. That is a defect in (au), and it is now the red
**`x64_RED_bd_system_prefix_not_misnamed`**. The pass state is *not the
wrong name*; whether to name them or leave them unknown is a ruling.

**Reach, from the bytes on the post-(ba) sweep:**
- **Misnamed: 0 rows.** This zero is measured too: the scan sees 14
  unprefixed WBINVD and 3 CLAC rows.
- **Unnamed:** LAR/LSL 3 rows (ASUS newer 2 in 1 binary, KC 1);
  **INVPCID 14 rows in 1 KC binary**; LKGS 0.

## What banking changed

| dependent | cited | against the text |
|---|---|---|
| pseudo-op class | Tables 3-9/3-11/3-13/3-15, 4-15 | **identical, 36 of 36** |
| (bb) exceptions | the ten instruction pages | **confirmed, 10 of 10** |
| SSE family | A.2.1; Tables A-3/A-4/A-5 | all 270 attested; **7 legacy XMM encodings missing from the maps and the family** (0 corpus rows) → `(be)` |
| system family | Table 2-3 (and other chapters) | **3 misnamed encodings** → red `(bd)`; 4 unnamed (17 corpus rows) → `(be)` |

**The plainest finding is the error class itself.** The system family was
assembled from several chapters (Table 2-3, the VMX instruction reference,
and the pages for SYSCALL, the MSRs, CPUID and MONITOR) and was described in
its own census as drawn from one chapter ("the SDM's system-instruction
chapter"). That is exactly the error that
banking the source was meant to close, and it surfaced on the first
check. It is the strongest argument that pinning the manual was worth
doing.

**Two of the four came back clean. Two came back with findings, and one
of those is a wrong answer the recalled structure had hidden.** That is
the reason to pin a source.
