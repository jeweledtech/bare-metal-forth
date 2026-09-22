# An ABI-aware CALL stop: pre-registration (2026-09-22)

**Written before the stop exists.** The owner's order moves this ahead of
the lifter repair. Outcomes go BELOW the line, from the artefact only.

## The change, and why it is a correctness fix, not a loosened threshold

Today a CALL ends the walk, on the assumption that a call destroys every
register. The Windows x64 calling convention says otherwise: **RBX, RBP,
RDI, RSI and R12–R15 are callee-saved**, so a callee that uses one restores
it before it returns. A base held in one of them at a call is still held
after it. The walk has been discarding a fact the ABI guarantees.

**New rule at a CALL:** clear what the ABI lets a call destroy (RAX, RCX,
RDX, R8–R11), keep the nonvolatile registers, and continue. **If no register
still holds the base, the walk ends there as `none`**, which gives the same
outcome as today for every walk that had no nonvolatile copy.

**The guarantee's limit, stated:** it holds only for code that conforms to
the ABI. Three ways a call in this corpus might not conform:

1. **hand-written assembly in the callee.** Not detectable from the caller;
2. **a thunk or dispatch stub** (`__guard_dispatch_icall`, import thunks).
   These jump to the real target and pass the nonvolatile registers
   through;
3. **a call that does not return** (`KeBugCheckEx`). The walk would continue
   in address order into code that is not this call's continuation. That is
   the same address-order hazard the RET stop addressed, now reachable past
   a CALL.

The freed walks' call targets are recorded below the line, so (2) and (3)
are measured rather than assumed. (1) stays an unmeasured limit.

## Which walks can change, read from the walk and the pre-fix classification

Only a walk that today ends **at a CALL with the base in a nonvolatile
register** can change. Every park and couldn't-tell today ends before any
CALL, because a CALL ended the walk, so none of them can move.

**The owner's upper bound (at most class B: 16 / 18 / 15) is too tight, per
the source.** B was exclusive: a walk holding the base in an argument
register was filed under A even when a nonvolatile copy was also held. Such
a walk is freed too. Counted from the pre-fix masks:

| machine | B | A with a nonvolatile copy | **freeable** |
|---|---|---|---|
| HP | 0 | **1** (storport `1c0038269`: RDI and R8) | **1** |
| Dell | 16 | 12 | **28** |
| ASUS (older) | 18 | 12 | **30** |
| ASUS (newer) | 15 | 13 | **28** |

## Predictions

| # | prediction | why |
|---|---|---|
| C1 | **HP's twelve report lines are byte-identical.** One HP walk is freed and ends as `none` again. If any HP report line changes, that is **stop-and-report**. | storport's freed walk: in address order after the call, `mov 0x60(%rsp),%rdi` clears the last copy, and the walk reaches `ret` (read from the bytes) |
| C2 | per machine, `none` falls by **at most 28 / 30 / 28**. Any larger drop means the stop is keeping a register the ABI doesn't preserve, and is **stop-and-report** | the freeable counts above |
| C3 | site sets unchanged; only sites that are `none` today move; **no park or couldn't-tell moves** | monotonicity above |
| C4 | freed walks become park, couldn't-tell, or `none` again. **Couldn't-tell can rise**: freed walks run into more code, and more code means more unseen writes (`setne`, `rep`, `bt` …) | — |
| C5 | a guess, marked as a guess: of the ~86 freed walks off HP, **a minority become parks** (10–30 in total), **a third or more end as `none` again**, and the rest as couldn't-tell | the two examples read earlier: IntelPMT should become a park; IPMIDrv's walk is on the failure fallthrough and should not |
| C6 | **every park this creates is new.** No instrument has seen it, and it is the first number in the arc that a repair creates rather than uncovers. **Sampled against the bytes, not trusted**: at least one per machine, and all of them if there are ten or fewer | — |

**The byproduct measurement.** After the stop, a freed walk that still ends
as `none` has kept the base across every call and still found no park. By
construction it has lost the chain another way: the linear walk took a
branch the base did not, it reached the function's end, or the base went
into a later call's arguments. That residual, per machine, is reported as
the **upper bound on the branch-following share**, split by how it ended.
It is not exactly the branch-following share, because the A-at-a-later-call
case sits inside it too, and that case is separated out.

---

## Outcome

*(below this line, from the artefact only)*
