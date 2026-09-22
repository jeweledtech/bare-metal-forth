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

**Inputs hashed:** `bin/translator` `4852c9c516ec295c` (the pre-stop run was
`9dcde79bec4b3f75`). The census scripts were unchanged against
`SHA256SUMS`. The diagnostic build is in scratch only; its outcomes match
the census site for site on all four machines (0 mismatches).

**(ap):** exactly one XPASS; `pw_GUARD_volatile_register_dies_at_call` stayed
PASS. 390 tests across 27 suites, 14 reds, the union matching.

| # | predicted | observed |
|---|---|---|
| C1 | HP byte-identical; one walk freed and ending `none` | **byte-identical, 12 of 12 lines.** The freed storport walk ended at `ret`, as read from the bytes |
| C2 | `none` falls by at most 28 / 30 / 28 | fell by **15 / 17 / 15**. The walks freed were **exactly 28 / 30 / 28** |
| C3 | only `none` sites move; site sets unchanged | **held.** Site sets identical; every move started from `none` |
| C4 | couldn't-tell can rise | **rose 13 / 14 / 13** |
| C5 | *guess:* 10–30 parks, a third or more `none` again | parks **7** (2 / 3 / 2), **below the guessed range**; `none` again 13 / 13 / 13 (46%, 43%, 46%), inside |
| C6 | every new park checked against the bytes | **all 7 read, all 7 real.** See below |

**The seven parks this repair created, each read against the bytes:**

- `fvevol.sys`, one per machine (`0x280` / `0x270` / `0x278`): the base
  goes to RSI, a helper is called, `js` jumps to the error path, and the
  fallthrough stores RSI at `0x2xx(%rdi)`. **Straight-line, and real**: RSI
  is callee-saved.
- `scsiport.sys`, one per machine (`0x8`): the base goes to RDI, an
  allocation is called, then `jne` goes to `mov %rdi,0x8(%rax)`, which files
  the base into the new object. **Real, but reached by the wrong route.** The
  walk fell through the failure block and its `jmp`, and agrees only
  because nothing on that stretch touches RDI.
- `Netwtw08.sys` (older ASUS, frame `0x70`): a join block reached by eleven
  `je`/`jb` from the success-side body. R12 is written once, by the mapping
  call's `mov %rax,%r12`, so every path holds the base. **Real frame
  spill**, again reached in address order and not by path.

**None is false. Four of the seven are right by address order and not
verified by path**, which is the branch-following limit, and it is now
producing correct answers it cannot vouch for.

**The ABI limit, measured where it could be:** the walks crossed 96 / 121 /
96 calls with the base live. Of those, 34 / 36 / 38 were imports, all kernel
APIs, **none of them noreturn**; the rest are calls internal to the driver.
Hand-written callees remain unmeasured. **A hazard found:** 66 of the
crossings are `MmUnmapIoSpace`. The walk carries the base past the call that
releases it. None of the seven parks is a store after an unmap *on its real
path*, but the three `scsiport` parks cross one on their address-order
route.

**What stopped the new couldn't-tell (40):** `mov %cr8,%rbx` 12 (all in
`mlx4_bus.sys`, an inlined IRQL read the decoder does not name, writing
RBX), `lfence` 8, `cmovcc` 9, `sete` 3, `movsd` 2, `bt`-family 4, `int3` 2,
`rep` and `cqto` 1 each.

**The byproduct: the residual.** 13 freed walks per machine still end as
`none`:

| machine | ended at RET, base kept, nothing stored | ended at a later CALL with the base only in argument registers |
|---|---|---|
| Dell | **8** | 5 |
| ASUS (older) | **7** | 6 |
| ASUS (newer) | **8** | 5 |

The right column is class A met again at a later call, so it is
interprocedural and not a branch problem. **The left column, 8 / 7 / 8, is
the upper bound on the branch-following share** of what class B held. Those
walks kept the base across every call and reached a return without storing
it, which is what a linear walk down the wrong side of a branch looks like.
It is also what a function that returns the base looks like, so it is an
upper bound and not a measurement. **That is the size of the deferred job,
as far as this census can see it.**

**The census, both ways, after the stop:**

| machine | structure / all sites | structure / resolved | none | couldn't tell |
|---|---|---|---|---|
| HP | 6/12 = 50% | 6/9 = 67% | 1 (8%) | 2 |
| Dell | 90/172 = 52% | 90/115 = 78% | 33 (19%) | 24 |
| ASUS (older) | 80/171 = 47% | 80/109 = 73% | 37 (22%) | 25 |
| ASUS (newer) | 95/184 = 52% | 95/121 = 79% | 41 (22%) | 22 |

The `none` gap narrows from 28–32% to 19–22% against HP's 8%, and most of
what left `none` went to couldn't-tell, not to parks.
