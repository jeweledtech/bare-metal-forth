# SBB, ADC, ROL, ROR carry their operand: pre-registration (2026-09-22)

**Written before the change.** Owner's order: extend the SETcc contract
(`fix-setcc-operand-prereg-2026-09-22.md`) to SBB, and take ADC, ROL and
ROR with it. Outcomes go BELOW the line, from the artefact only.

**One rule, not four cases.** The contract is: an unmodelled instruction's
`dest` is set only where the decoder's operand is its complete register
write set. A probe at `d6df4535` read the decoder's operand 0 for
register, memory and immediate forms of all four: `19 c0`, `48 19 c8`,
`1b 03`, `83 d8`, `19 03`, `1d`, `11 c8`, `83 d0`, `14`, `d1 c0`, `d3 c8`,
`48 c1 c0`, `d1 0b`. Operand 0 is the destination in every one: a register
where the destination is a register (including `sbb (%rbx),%eax` → EAX),
and memory where it is memory. So the four join SETcc's lifter case
unchanged, and `uir_writes()` needs no edit.

**Bound, measured on the current binary** with an exact mnemonic matcher
(the first attempt's suffix stripper turned `sbb` into `s` and read zero):
walks stopping at one of the four today are **0 / 1 / 1 / 1**, the three
`pmem` sites: Dell `140019997`, ASUS (older) `1C001604E`, ASUS (newer)
`1C001827F`. At the walk this is a three-site repair, however large SBB is
by corpus occurrence.

| # | prediction |
|---|---|
| T1 | HP: byte-identical |
| T2 | only the three `pmem` sites can change; every other outcome is byte-identical |
| T3 | the three `pmem` sites: no prediction of what they become; reported as observed |
| T4 | `-t uir`: line counts identical; every changed line is an `unmodelled` line that gains an operand |
| T5 | one XPASS; the `(al)` red's `sbb %rax,%rax` and `rol $1,%rax` cases stay green (the guard that these still overwrite the base); tests +1; 14 reds |

---

## Outcome

*(below this line, from the artefact only)*
