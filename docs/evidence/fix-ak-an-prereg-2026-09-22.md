# (ak)–(an) pre-registration: what the park walk can see a register do

**Written before any fix code, 2026-09-22.** The reds are registered and red
(private `c568cd6`, register `82d801f`). Outcomes go BELOW the line, and only
from the artefact.

## The design, in three parts, owner's order

1. **The totality switch.** `uir_writes()` in `src/ir/uir.c`: a `switch` over
   every `uir_opcode_t` with **no `default:`**, answering for one instruction
   *which registers does it write, or can that not be seen?* It answers
   more than "does it write `dest`", because (ak)'s pass state needs it to:
   MUL/DIV/IDIV and one-operand IMUL leave `dest` alone **and** write
   RAX:RDX. If they answered only "dest not written", the walk would
   have to stop at them (their RAX:RDX writes unseen), and (ak) would stay
   red. `-Wall -Werror` makes a missing case a build failure, the same guard
   shape as `uir_opcode_name()`'s table.
2. **Two lifter states, both needed by the switch.**
   - `UIR_UNKNOWN`: `X86_INS_UNKNOWN` stops lifting to `UIR_NOP`. At present a byte
     sequence the decoder cannot name and a real `nopl` are the same UIR,
     and **every one of the twelve HP windows has a real `nopl` straight
     after the call**. A guard that stops on "cannot see" cannot work
     until the two are different.
   - `UIR_XCHG`: the ModRM exchange stops lifting to `UIR_MOV`. A MOV
     records one write; (am) asserts both.
3. **The walk guard.** At each instruction, the walk asks `uir_writes()`. If
   the answer is that the writes cannot be seen, it stops, and the region
   records `park_undetermined_at` with that instruction's address. The
   census counts that as its own category. The CMP/TEST special case is
   deleted: the switch subsumes it.

**Readers enumerated from source (rule 24):** `UIR_MOV` is read by exactly
one product site, the walk at `semantic.c:486`, and `UIR_NOP` by none
outside the lifters and the name table. Nothing else in `src/` switches on
a UIR opcode. So the only product figures that can move are the park walk's
output and the `-t uir` text dump.

## Predictions

| # | prediction | suspect named |
|---|---|---|
| P1 | exactly **four** XPASS, the four names; `pw_GUARD_plain_park_is_found` stays PASS | — |
| P2 | of the twelve HP sites, **ten unchanged** and **serial's two change**: park `0x1C000C720` becomes `park_undetermined_at 0x1C000C710`, and park `0x1C000C806` becomes `park_undetermined_at 0x1C000C7F6` | `setne %cl` lifts to `UIR_UNMODELLED` with no dest, so its write cannot be seen, although it writes CL and the base is in RAX |
| P3 | `-t uir` over the 12 captured inputs: **line count identical per input**, and every changed line is `nop`→`unknown` or `mov`→`xchg`; no other line changes | — |
| P4 | census 386 tests / 27 suites unchanged; register union **18 → 14** once the four names are removed | — |
| P5 | stage 1 (`test-mmio-consumer`) and port attestation unchanged | — |
| P6 | adding one unhandled opcode to the enum fails the build, naming `uir_writes` | — |

**P2 is a cost, stated before it is paid.** Serial's two parks are real (the
bytes show `mov %rax,0xe8(%rdi)` after `setne %cl`), and the guard as specified
will report them as "couldn't tell". The UIR drops SETcc's operand, so the
honest answer at the UIR level *is* "cannot see". The repair is to have the
lifter carry the decoder's operand for the unmodelled identities, which
would recover them. That is **not** in this fix; it changes UIR output for
1,089 corpus rows and needs its own count.

**Alternative named and not taken:** stop only when the invisible
instruction's *operand* names a holding register. The UIR doesn't carry
that operand for UNKNOWN or UNMODELLED, so this can't be done without the
lifter repair above.

---

## Outcome

*(below this line, from the artefact only)*
