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

**Inputs hashed:** `bin/translator` `9a46c0e921bc5b8b`, `semantic.c`
`dc0093d94a023c52`, `uir.c` `e9eea32293c74944`, `uir.h` `4a1f720ece8cec84`,
`semantic.h` `bda7327582c0e915`. Pre-fix binary `5628af0744ae4087`.

| # | predicted | observed |
|---|---|---|
| P1 | four XPASS, guard PASS | **exactly four**, the four names, guard PASS (`fix-ak-an-xpass-gate-2026-09-22.log`) |
| P2 | ten sites unchanged, serial's two undetermined at `0x1C000C710` / `0x1C000C7F6` | **exactly that.** 10 of 12 byte-identical report lines; serial's two read `"park_undetermined_at": "0x1C000C710"` and `"0x1C000C7F6"` |
| P3 | `-t uir`: line counts identical, only `nop`→`unknown` and `mov`→`xchg` change | **line counts identical on all 12 inputs; 0 lines changed any other way** (whitespace-normalised; the printer pads the mnemonic, which my first diff did not allow for and reported as 75,912 "other" lines, a checker error, not a product one) |
| P4 | census unchanged, register 18 → 14 | 386 → **387** (one test added below), register **14**, union matches |
| P5 | stage 1 and port attestation unchanged | both PASS; port attestation 8 drivers analysed |
| P6 | an undecided opcode fails the build naming `uir_writes` | `error: enumeration value 'UIR_GUARD_PROBE' not handled in switch [-Werror=switch]` in `uir_writes` |

**`-t uir` movement, per input** (`nop`→`unknown` / `mov`→`xchg`): ACPI
22,435 / 34, disk 1,812 / 1, HDAudBus 3,494 / 9, i8042prt 2,338 / 10, pci
14,947 / 12, serial 2,521 / 10, storport 14,820 / 48, usbxhci 13,023 / 29;
controls: nmap_service 336 / 4, beep 4 / 2, ReactOS serial 6 / 0; fixture
17 / 0. **On the eight HP drivers, 75,390 instructions the decoder cannot
name had been printing as `nop`.**

**One change not pre-registered, found during P3 and given its own red.**
The beep control's dump shows `xchg [r3+56], r0`. An exchange with memory
*stores* the register, so if that register holds the base the exchange
is the park, and the walk as first written would have cleared it and
printed "none" for a park that exists. The walk now stops there as
undetermined. `pw_xchg_with_memory_is_not_a_silent_none` failed with the stop
removed and passes with it; P2 is byte-identical either way.

**P2's cost, now paid:** serial.sys reports **0 parks and 2 undetermined**,
where it reported two real parks. The repair that recovers them, which is
the lifter carrying the decoder's operand for the unmodelled identities,
is named and not taken.
