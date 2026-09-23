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

**Inputs hashed:** `uir.c` `65fdaaa8dae2759c`, `bin/translator`
`629096321b3d3a53`. The UIR baseline is the post-(ba) binary's dump, and the
census is v3, unchanged against `SHA256SUMS`.

| # | predicted | observed |
|---|---|---|
| L1 | the red XPASSes on the target's bytes; the guard green before and after; nothing else moves | **held**: exactly one XPASS, `sem_RED_bb_sse_dest_seen`, and `pw_GUARD_bb_sse_contract` PASS before the fix and after it (`movq %xmm0,%rax` kills the base; `ucomiss` still stops the walk) |
| L2 | 7,315 SSE lines gain an operand; 0 other changes; the target lines as named | **held**: line counts identical on all 12 inputs, **7,315** lines gain an operand, 0 others. `1c00226bd: unmodelled r72` and `1c00226c0: unmodelled [r7+40]` (the printer's form of `[rdi+0x28]`, displacement in decimal) |
| L3 | only the 2 `IPMIDrv` sites can change; HP and Dell identical | **held**: exactly those 2 changed, **both couldn't-tell → `none`, address order**; 0 changes elsewhere, and the site sets 12 / 172 / 171 / 184 are unchanged |
| L4 | differential unchanged | by construction: the decoder is untouched, and `dump_starts` does not link the lifter |
| L5 | suites green; tests +2; 13 reds then 12 | **held**: 405 tests across 27 suites (403 + the red + the guard), 12 reds once the red closed |

**Why the two `IPMIDrv` sites are `none`, read from the bytes** at ASUS
older `0x1C0009560`, with IAT slots resolved by name (`0x15250`
`MmMapIoSpaceEx`, `0x15248` `MmUnmapIoSpace`):

1. The mapped base goes to RSI, and RDI scans it for the `_SM_` signature
   (`cmpl $0x5f4d535f,(%rdi)`, stepping 0x10): an SMBIOS entry-point search.
2. At the hit, `movsd 0x10(%rdi),%xmm1` reads 8 bytes of the entry point
   (the walk's old stop), `movsd %xmm1,0x70(%rsp)` spills them, and a
   second `MmMapIoSpaceEx` maps the table they describe.
3. `mov %rsi,%rcx` / `MmUnmapIoSpace` then releases the first mapping.

The first base is used only as a scan address and released in the same
function; it is **never stored**. So `none` is the right answer. The route
is address order because the walk reaches the `movsd` past the loop's
back-edge `jmp` at `1c000964c`. The real path (the `je 0x1c0009651` hit)
reaches it too. The newer build's stop (`0x1C000AEA1`) sits in the same
`_SM_` loop and the same `movsd`. These are one driver on two builds.

**For stage 2 (a consequence, not a reason):** the named target now lifts
as seen. `movups (%rbx),%xmm0` writes XMM0 only, and `movups
%xmm0,0x28(%rdi)` writes memory only. So the product's walk passes the pair
that blocked all 14 banked rows. The `imul` at `1c0022cc1` was cleared by
(p). **Stage 2's blockers are all now named and seen.** Whether its 14 rows
come out exactly as banked is stage 2's own measurement, when it is built.
