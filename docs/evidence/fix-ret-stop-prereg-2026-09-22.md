# The walk stops at RET: pre-registration (2026-09-22)

**Written before the stop exists.** Owner's order: RET stop first, then the
lifter carrying the flag-set's operand; branch-following not now. Outcomes
go BELOW the line, from the artefact only.

## What the source says the stop can and cannot do (rule 31)

The walk (`semantic.c`, stage 1) runs forward in address order over the
function's blocks, and ends in exactly one of four ways:

| end | outcome |
|---|---|
| a STORE of a register holding the base | park |
| an instruction whose writes the UIR does not show | couldn't tell |
| a CALL | none |
| the function's blocks run out | none |

A RET is currently *not* an end: `uir_writes()` answers "writes RSP", and
the walk carries on into whatever follows in address order.

**A RET stop ends a walk earlier, and the outcome there is `none`.** So:

- a site that is `none` today stays `none`. The stop cannot turn a `none` into
  anything, because a walk that found nothing before the RET finds nothing
  once it stops there;
- a park or a stop that the walk reaches **after** a RET becomes `none`;
- nothing else moves.

**So `none` can only rise, and the owner's proposed mechanism for the `none`
gap is reversed by the source.** A walk that runs past a RET can wrongly
*produce* a park or a stop, attributing a later block's store to this call.
It cannot wrongly produce a `none` that the stop would then remove. The
stop is still the right repair, because it removes false attribution, the
stronger claim. It cannot test the overfitting reading.

## Predictions

| # | machine | prediction | why |
|---|---|---|---|
| R1 | HP | **no change at all**: 6/2/1/2/1 | none of the twelve windows (objdump, `session_2026_09_22_flag_only_review`) has a RET before its outcome |
| R2 | Dell, ASUS ×2 | `none` **rises**; parks and couldn't-tell **fall by the same total**; sites unchanged | the monotonicity above |
| R3 | Dell, ASUS ×2 | the rise per machine is **small, a guess of 3–10**, taken mostly from the 15 `int3` stops | `int3` is padding, reached only past a RET or a JMP; the stop catches the RET cases and not the JMP ones (tail calls), so fewer than 15 move in total, and the park share of the rise is **not known** |
| R4 | all | the `none` gap (8% against 24–30%) **survives** the stop | from R2: it can only widen |

**The experiment that does discriminate, pre-registered with it.** It asks
what *ends* the `none` walks, per machine, read from the product's own walk
through a diagnostic build that is kept out of the tree:

| # | prediction |
|---|---|
| D1 | on every machine, **most `none` walks end at a CALL** before any store, not at the end of the function |
| D2 | the named suspect is that the base goes into a call as an argument (`mov %rax,%rcx` / `%rdx` / `%r8` / `%r9`, then `call`), which is a helper that parks it. That is **interprocedural**, outside the walk's scope, and **not** the walk failing on unfamiliar code |

**If D1/D2 hold**, the `none` gap is a difference in how drivers are written,
since more of them hand the mapped base to a helper, and the overfitting
reading is not supported. **If `none` walks mostly end at the function's end,
or at a CALL with no register copy of the base as an argument**, the walk is
losing chains, and the overfitting reading stands.

---

## Outcome

*(below this line, from the artefact only)*

**Inputs hashed:** `bin/translator` `9dcde79bec4b3f75` (the pre-stop run was
`9a46c0e921bc5b8b`). The census scripts were unchanged, checked against
`~/corpus/tools-2026-09-22/SHA256SUMS` before the run. The diagnostic build
lives in scratch, outside every tree, and was never committed. It is held to
a control: its count of `none` walks equals the census's on all four
machines (1 / 48 / 54 / 56).

**(ao):** exactly one XPASS, `sem_RED_ao_ret_ends_the_walk`. 388 tests across
27 suites, 14 reds, the union matching.

| # | predicted | observed |
|---|---|---|
| R1 | HP unchanged | **unchanged**, 0 of 12 sites moved |
| R2 | `none` rises; parks and couldn't-tell fall by the same total; site sets unchanged | **held, and narrower than predicted.** Site sets identical. **Every** move was couldn't-tell → none: Dell 6, ASUS older 3, ASUS newer 5. **No park moved** |
| R3 | a rise of 3–10 per machine, taken mostly from the 15 `int3` stops | 6 / 3 / 5. **14 of the 15 `int3` stops moved**; the one left (`dxgmms2.sys` `0x1c007234a`) is reached by `jmp` after the call, the case the stop was predicted not to catch |
| R4 | the `none` gap survives | **widened**: 8% on HP against 28 / 32 / 30% |

**The census, both ways, after the stop:**

| machine | structure / all sites | structure / resolved | none | couldn't tell |
|---|---|---|---|---|
| HP | 6/12 = 50% | 6/9 = 67% | 1 (8%) | 2 |
| Dell | 88/172 = 51% | 88/113 = 78% | 48 (28%) | 11 |
| ASUS (older) | 78/171 = 46% | 78/106 = 74% | 54 (32%) | 11 |
| ASUS (newer) | 93/184 = 51% | 93/119 = 78% | 56 (30%) | 9 |

Both share rows are identical to the run before the stop, because every
site that moved was unresolved on both runs.

**The discriminating experiment: what ends the `none` walks** (exclusive
classes; a walk with the base in an argument register is counted as A even
if a copy is also held elsewhere):

| machine | none | **A** handed to callee | **B** live in a nonvolatile reg at the CALL | C dies at the CALL | D not held | E RET | F end |
|---|---|---|---|---|---|---|---|
| HP | 1 | 1 | **0** | 0 | 0 | 0 | 0 |
| Dell | 48 | 14 | **16** | 4 | 7 | 6 | 1 |
| ASUS (older) | 54 | 21 | **18** | 4 | 7 | 3 | 1 |
| ASUS (newer) | 56 | 23 | **15** | 4 | 8 | 5 | 1 |

- **D1 held:** most `none` walks end at a CALL (41 / 50 / 50).
- **D2 held only for a plurality.** The named suspect, the base handed to
  the callee, is the largest class on both ASUS machines and the second
  largest on Dell. It is 29–41% of `none`, not most.
- **A second class, B, supports the overfitting reading, and it is 0 on
  HP.** In 27–33% of `none` walks off HP, the base sits in a **nonvolatile
  register at the CALL where the walk quit**. The Windows x64 ABI preserves
  RBX/RBP/RDI/RSI/R12–R15 across calls, so the walk gave up on a live chain.
  Two examples were read against the bytes, and they show two mechanisms:
  - `IPMIDrv.sys` `0x14000c0b5`: base → RBX, then `test; jne` away. The
    linear walk follows the *failure* fallthrough and quits at the error
    path's call. **Branch-following** would fix it.
  - `IntelPMT.sys` `0x14000c53a`: base → RSI; the call is an allocation on
    the success path, after which `lea 0xc(%rsi),%r9` uses the base. **An
    ABI-aware CALL stop** (clear the volatile registers, carry on) would
    see it.

  How B splits between those two mechanisms is **not measured**; two
  examples show that both occur.
- **Correction of record, found while classifying:** my first pass labelled
  a class "CALL, base only in RAX", but it tested RAX before the other
  registers. Walks with the base in RAX *and* a nonvolatile register were
  filed there. The table above is exclusive and was recomputed from the
  register masks.

**So the reading is mixed, and the parts are named:** a third or more of
`none` off HP is the base handed to a helper (a real scope limit), and a
third is the walk quitting on a chain that is still live. That part is
exercised nowhere on HP.
