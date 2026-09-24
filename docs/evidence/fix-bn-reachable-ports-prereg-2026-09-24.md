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
