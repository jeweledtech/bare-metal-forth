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
