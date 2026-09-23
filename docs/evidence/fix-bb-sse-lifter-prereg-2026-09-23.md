# (bb) The lifter carries SSE operand 0: pre-registration (2026-09-23)

**Written before the change.** Scope, owner ruling: SSE operand 0 under the
existing contract, with its bound stated per machine and its distinct count.
The named target is the two `movups` at `1c00226bd` / `1c00226c0` in
HDAudBus. **Stage 2's rows are a consequence of this item, not a reason for
it.** Outcomes go BELOW the line.

## The contract, and which rows it gives a `dest`

The (as) contract: an unmodelled instruction's `dest` is set only where
the decoder's operand 0 is its **complete register write set**. Read per
instruction from the SDM:

- **Operand 0 is the whole write set** for every family row except the
  ten below. That covers moves, arithmetic, shuffles and conversions (an
  XMM, a general register for `G`/`E` forms such as MOVMSKPS, PEXTRW,
  CVTTSS2SI or `movq %xmm0,%rax`, or memory for the stores). These carry
  operand 0.
- **No `dest`, by the contract:**
  - COMISS, UCOMISS, COMISD, UCOMISD and PTEST write flags only; operand 0
    is a source.
  - PCMPESTRI and PCMPISTRI write ECX.
  - PCMPESTRM and PCMPISTRM write an implicit XMM0.
  - MASKMOVDQU writes memory at an implicit [RDI].
  - The MMX-operand rows carry no decoded operands.

  These stay unseen: the walk still stops at them. That is the
  conservative reading, not a new one.

**Readers of an unmodelled `dest`, enumerated from source (rule 24):**
`uir_writes()` (`uir.c:894`), and the `-t uir` printer. `semantic.c`
reaches it only through `uir_writes()`. An XMM `dest` (72–87) gives
**seen, no general register** via `reg_bits()`. A memory `dest` gives
**seen, no register**. A general-register `dest` gives that register,
which kills a base held there.

## Bound, per machine, with the distinct count

- **Park census:** a walk can change only if it stops at a family
  instruction today, since making an instruction seen can only extend a
  walk. There are **0 / 0 / 1 / 1** such walks (HP / Dell / ASUS older /
  ASUS newer), **2 in all**, and both are **`IPMIDrv.sys`**. **Distinct
  binaries: 2 builds of one driver** (`3b542bdf`, `6b20f83b`). Dell's build
  of the same driver has no such stop.
  - Both stop at the same instruction, **`movsd 0x10(%rdi),%xmm1`**
    (`F2 0F 10 4F 10`), a load whose whole register write set is XMM1.
  - Read at ASUS older `0x1C0009651` (call site `0x1C0009560`) and ASUS
    newer `0x1C000AEA1` (call site `0x1C000AE36`).
- **Contract exceptions in the corpus**, which are rows that keep no
  `dest`:
  - HP 0; Dell 218; ASUS older 2,316; ASUS newer 309;
  - Mac userland 3,349; dexts 7; KC 2,858;
  - all of them (U)COMIS* or PTEST, plus PCMPISTRI 12 and 7 on the two
    ASUS sets.
- **The UIR inputs** (the 8 HP drivers, the fixture and the 3 controls)
  carry **7,315** SSE lines and **0** exceptions.
- **The named target:** HDAudBus `1c00226bd` `0F 10 03` (`movups
  (%rbx),%xmm0`) and `1c00226c0` `0F 11 47 28` (`movups %xmm0,0x28(%rdi)`),
  read from the bytes. Today both lift as a bare `unmodelled`.

**Small in the park census, and stated as small.** The item's reason is
that every SSE row is seen by the IR once it lands. The park census is one
consumer of that, and stage 2 (not yet built) is the next.

## Predictions

| # | prediction |
|---|---|
| L1 | the red `sem_RED_bb_sse_dest_seen` XPASSes: the target's own bytes (`0F 10 03`, `0F 11 47 28`) between the map and a store of RAX leave the base tracked, and the store parks at `PW_BODY + 7`. The guard `pw_GUARD_bb_sse_contract` stays green both before and after: `movq %xmm0,%rax` (`66 48 0F 7E C0`) into the base's register leaves no park at the later store, and `ucomiss %xmm1,%xmm0` (`0F 2E C1`) still stops the walk. Nothing else moves |
| L2 | `-t uir`: line counts identical; **exactly the 7,315 SSE lines change, each gaining an operand**, and 0 others. The target lines read `unmodelled r72` (`1c00226bd`) and `unmodelled` with the memory operand `[rdi+0x28]` in the printer's format (`1c00226c0`) |
| L3 | park census: **only the 2 `IPMIDrv` sites can change**; their outcome is not predicted, and is reported as observed and read from the bytes. HP and Dell identical |
| L4 | differential unchanged (the decoder is untouched, and `dump_starts` does not lift) |
| L5 | suites green; **tests +2** (the red and the guard); 13 reds while the red is open, then 12 |

---

## Outcome

*(below this line, from the artefact only)*
