# (bn) a port fact needs a reachable instruction: pre-registration (2026-09-24)

**Written before the fix.** Owner ruling, 2026-09-24: (bn)'s fix next. The
Ghidra attestation (`measure-port-attestation-prereg-2026-09-24.md`) has
already labelled every port site independently, so the gate is an **exact
set**. Outcomes go BELOW the line.

## The rule, as it will be implemented

A port, whether immediate (`in`/`out imm8`) or DX-resolved (pass 4's
`mov dx, imm16`), is recorded for a function **only if its instruction's
block is reachable from the entry block** over the lifter's own edges: the
fall-through and branch targets of pass 3. The UIR itself is unchanged
(`port_in`/`port_out` still lift). Only the port facts are filtered.

**Named before the run:**
- **Jump tables.** `jmp [base+idx*8]` has no edge the lifter follows, so
  ports inside `switch` case bodies become unreachable. Ghidra resolves
  tables, so these can be attested sites the guard drops, which are false
  negatives against the oracle.
- **A C quirk the rule inherits.** Pass 3 sets non-`jcc` fall-through only
  if the function's **first** instruction is not a `jmp` or `ret`
  (`!is_terminator(insts[0])`). In a thunk-headed function, that disables
  fall-through everywhere. It is mirrored in the model and not fixed here.
- **Residual.** Garbage reached by linear fall-through from real code
  (f3ahvoas) stays reachable. This fix is necessary, not sufficient.

## Prediction 1: my estimate, before any model runs

Over the 136 drivers' **port-fact sites** (UIR port sites inside functions
the report lists with `ports_accessed`), and against the attestation's
labels:

| # | estimate |
|---|---|
| E1 | **~30%** of the *unattested* port-fact sites are removed (range 10–60%) |
| E2 | **≤ 2%** of the *attested* sites are removed (jump tables) |
| E3 | port-fact functions left after the fix: **~600** of 932 (range 400–850) |

## Prediction 2: the rule's outcome, from a second implementation, before the C change

`bn_model.py` (Python, over `-t uir`; sha in `~/corpus/tools-2026-09-24/SHA256SUMS`)
implements the rule over the UIR text: block reachability from the entry,
and pass 4's DX back-scan. The function-level count uses the lifter's own
printed edges (`-> fall_through` / `-> branch`). It is scored against the
Ghidra labels.

| | before | kept after the rule |
|---|---|---|
| port-fact sites, unattested | 34,724 | 11,133 (**23,591 removed, 67.9%**) |
| port-fact sites, attested | 573 | 544 (**29 removed**) |
| port-fact functions, **attested** | 220 | **191** |
| … of which ClipSp (non-code, per the owner's point 3) | 127 | 100 |
| … **outside ClipSp** | **93** | **91** |
| port-fact functions, **unattested** | 712 | **363** (349 removed, 49%) |
| … outside ClipSp | 319 | 120 |

**Scored against my estimate (part 1):**
- E1 predicted 30% of unattested sites removed, range 10–60%: **missed,
  67.9%**.
- E2 predicted ≤ 2% of attested sites removed: **missed, 5.1%**.
- E3 predicted ~600 port-fact functions left, range 400–850: **held, 554**.

**The owner's gate, predicted to fail in two named places:**
- **2 attested functions outside ClipSp lose their port facts**, in
  `RTKVHD64.sys` (fn `0x160260`). The chain to the attested sites breaks at
  a block ending in an `unknown` instruction our decoder cannot identify,
  where Ghidra decodes on. The lifter's own printed edges agree. This is **a
  decoder-coverage gap feeding the CFG**, not the rule.
- **27 ClipSp attested functions lose theirs.** Under point 3 (no device, no
  hardware resources, every port site in 7.1–7.9 bits/byte sections) these
  are not port access, so this is correct.

**The residual, as the owner asked:** the rule removes **349 of the 712**
unattested functions, not 712. The other 363 stay, reached by linear
fall-through (f3ahvoas's kind) or through code Ghidra itself does not
reach. **So the guard needs a second condition.** That is not a failure of
this fix, and it is named here before the fix lands.

## The gate for the C change

1. The (bn) red XPASSes on exactly its name, the guard stays green, and
   the suites are otherwise unchanged. The domain guard stays at 14.
2. **The C change reproduces the model exactly:** per driver, the set of
   functions keeping port facts equals the model's, with **554** in total
   (191 attested + 363 unattested).
3. **Nothing but port facts moves:** UIR text unchanged on all 12 snapshot
   inputs (ports are facts about the UIR, not UIR lines), dumps 0 of 16, X1–X3
   unchanged, census 0 of 539.
4. Buckets may move: a function that is hardware only through its port fact
   and loses it leaves the hardware block. That count is **not predicted**,
   because a port-fact function can also be hardware through its imports.
   It is counted after.

---

## Outcome

*(below this line, from the artefact only)*

**Inputs hashed:** `bin/translator` before `1560da9a91319b0d`, after
`016001f9c343189b`, built from private `b8a1484` (red `67aa689`), mirror
identical. Readings are `bn-reports-post.tsv`, `bn-zero-fact.tsv` and
`bn-model-sites.json` in `~/corpus/tools-2026-09-24/SHA256SUMS`. 0 empty
outputs.

| gate | predicted | observed |
|---|---|---|
| 1 | the (bn) red XPASSes alone; its guard stays green; the domain guard stays 14 | **held** (`fix-bn-xpass-gate-2026-09-24.log`): 421 tests, 12 reds |
| 2 | per driver, the C's kept port-fact functions equal the model's; 554 in total | **135 of 136 drivers exact; 553 against 554.** The one miss, `PEAuth.sys` (older ASUS) `0x1c00b4008`, is **the model's error**. The model credited a DX port from `mov r2, 0x3a1160e0a9c0602d` (a 64-bit move into RDX), a form the C's pass 4 has never counted: the pre-fix port list for that function is {0xAC, 0x1D, 0xB1, 0x6F, 0x81, 0x30, 0xD6}, with no 0x602d. The function itself is protected-code garbage (`invalid`, `sti`, `hlt`, operandless `port_in`) |
| 3 | only port facts move: UIR 0 of 12, dumps 0 of 16, X1–X3, census 0 of 539 | **held**: UIR 0; dumps 0; snapshot reports 0; X1 0 hex, X2 and X3 1,322 of 1,322; `iat_edges` unchanged on 1,322; census 0 of 539. Report bytes changed on **98** drivers, all among the 136 port-fact drivers |
| 4 | buckets may move; counted after | **0 moved.** See the residual below |

**The owner's exact-set gate, scored as predicted.** The attested functions
kept are **191 of 220**. The 27 ClipSp functions dropped are correct (non-code,
point 3). The **2 RTKVHD64** functions are false negatives against the oracle,
from our CFG breaking at an undecodable instruction. That is decoder coverage,
not the rule. **Unattested functions removed: 349 of 712**, with 363 left.

### What (bn) did not reach, now measured

- **The convergence check (owner point 5) does not converge.** The product's
  own zero-fact number after the fix is **94.75%** (10,751 hardware, 553
  port-fact, 11 stage-2), up from 91.23%. The oracle says 97.85–99.03%.
  **The gap is the 363 unattested functions kept**, reached by linear
  fall-through, so the second condition the pre-registration named is
  needed. An internal check and an external oracle do **not** yet agree, and
  that is the result.
- **The hardware label is untouched: 0 buckets moved.** The fix filters port
  *values*. The lifter's `has_port_io` is still set by **any** `in`/`out`,
  reachable or not, and it still makes a function hardware. So the functions
  that lost every port fact are still printed as hardware. **That is the same
  defect one level up**, and it is not pre-registered. It needs its own letter
  and red before any fix. How many hardware functions it holds up is **not
  measured**.

**Independent checks:** the suites, the model (a second implementation), the
population run, the census and the snapshot. **Five.**
