# (bk) is blocked by (bm): import thunks, and a discovery defect underneath them (2026-09-24)

**Status: measured, reds registered, nothing fixed.** Owner ruling,
2026-09-24: (bk) first, because it changes what the analysis *sees*. Reading
(bk)'s fix site before pre-registering it found that for most thunks the
fix would attribute the import to the **wrong function**. The reason is a
second defect, lettered `(bm)`, in function discovery. The build order is
brought back to the owner.

## What reading the fix site found

(bk)'s fix is small on its face. `semantic.c` resolves an IAT edge only on
`UIR_CALL` (`if (ins->opcode != UIR_CALL) continue;`). Admitting a `UIR_JMP`
whose memory target is an import slot would make an import thunk a tail
call. The lifter resolves RIP-relative targets for **any** operand
(`uir.c`, fix (a)), so a real `jmp [rip+x]` carries its absolute target.

**But the thunk must be its own function for that to help.** The 664-0
result records, for each thunk, the lifted function that holds it.

| class-library thunks (`jmp [slot]`), 392 importers | count |
|---|---|
| the thunk **is** a function of its own | **52** (12 drivers) |
| the thunk is **absorbed** into a neighbouring function | **239** (63 drivers) |

An absorbed thunk sits after the neighbour's `ret` and padding. For it,
(bk)'s simple fix would give the import's category to **the neighbour**, a
function that does not call the import. The thunk's real callers call its
address directly, and that address is not a function entry, so they would
still get nothing.

**The absorption is real, not an artefact of the ownership map.** 152 of 152
absorbed thunks checked on 40 drivers have **no** `function @` header of
their own and are listed in **exactly one** function.

**Their callers exist.** `thunk_refs.py` (one objdump pass per driver) finds
**199 of the 239** absorbed thunks with at least one **direct `call`** to
their address. 198 of those calls are from `.text` to `.text`. So discovery
*should* have made them entries: step 2 of `sem_discover_functions()` adds
every direct-call target inside `.text`.

## (bm): why it did not

- The decoder stores a REL operand's `imm` as the **absolute** target:
  `x86_decoder.c`, `E8`/`E9`/`EB`,
  `imm = base_address + offset + rel`.
- Discovery step 2 then computes `target = address + length + imm`,
  **adding the displacement a second time**. The target lands far outside
  `.text` and is dropped.
- So step 2 contributes nothing. Entries come from exports, `.pdata`
  function boundaries (passed in as unnamed exports), the prologue pattern and
  the text base.

**The claim was narrowed by measurement before it was written.** My first
statement was "step 2 never contributes on any input". **On the HP eight, 0
direct-call targets are missing as entries**, because `.pdata` lists every
function there. The defect is **masked** wherever `.pdata` is complete, and
exposed where it is not: leaf thunks, which have no unwind data, are the
clearest case.

**The red:** `sem_RED_bm_call_target_is_entry`. It decodes `call +6; ret;
int3 ×5; jmp [rip+0]` at `0x140001000` and asserts an entry at the thunk
(`0x14000100B`). **Mechanism control**
(`fix-bm-mechanism-control-2026-09-24.log`): in a throwaway, step 2 taking
`imm` as the target, and nothing else changed, turns the red green. Restored
identical, binary hash `343e89fa…` again.

**Reach, measured over the 1,322** (`bm_extent.py`: objdump direct-call
targets inside `.text` against the shipped translator's function entries):

| | |
|---|---|
| drivers measured | 1,321 (1 has no `.text`) |
| drivers with ≥ 1 direct-call target that is not an entry | **199** (15%) |
| direct-call targets | 347,707 |
| not an entry | **17,820** (5.1%) |
| per-driver fraction missing | median 0; 90th percentile 11.8%; max 57.9% |

## Why this goes back to the owner rather than being built

**Fixing (bm) moves function boundaries on 199 drivers.** Every figure that
depends on boundaries could then move: buckets, the park census, stage 2, and
X2's report bytes (though not its families). That is much larger than (bk),
and it has to be pre-registered on its own, with its own must-not-move set.
The 1,122 measured drivers with no missing entry should not move at all.

**Two orders, stated, not chosen:**
1. **(bm) then (bk).** Thunks become their own functions first, then (bk)
   resolves `jmp [slot]` inside a thunk's own function. This is the order
   the defect structure implies.
2. **(bk) restricted to thunks that are their own function** (52 sites, 12
   drivers) now, with the absorbed 239 waiting for (bm). This is smaller, but
   it lands a fix whose main population is blocked.

## Reds now

14 across 27 suites (418 tests): the 12 decoder reds, `(bk)`, `(bm)`.
