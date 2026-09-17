# Pre-registration: IAT accidental-match check on one HP driver (2026-09-17)

Written BEFORE the probe was run. Outcome below the line.

## The claim under test

The 2026-09-14/15 register entries say "no import is ever
cross-referenced on x64" and "the import comparison can never match".
Owner (2026-09-15): if `semantic.c:356`'s branch is ENTERED with a
wrong address rather than skipped, it may occasionally match by
accident and attribute a real HAL name to the WRONG call site, which is
worse than an empty result. Until measured, "can never match" is an
inference.

## Mechanism (read from code, 2026-09-17)

`src/ir/semantic.c` 355-373: a UIR CALL whose operand is memory with
`reg < 0 && index < 0` is taken as `call [absolute]`; `call_target =
(uint64_t)(uint32_t)dest.disp`; it is compared for EQUALITY against
`image_base + imports[k].iat_rva` for every import. On the HP PE32+
drivers `image_base` = 0x1C0000000, so every `iat_abs` ≥ 0x1C0000000
while `call_target` ≤ 0xFFFFFFFF. **By arithmetic no match is
possible** on these inputs; a match is possible only when image_base
< 4 GiB (PE32, where the path was designed and works).

## What the probe measures (one HP driver, i8042prt.sys, plus a PE32 control)

For every function: count call edges of kind IAT (the branch was
entered), the maximum `target_addr` among them, the minimum `iat_abs`
among the driver's imports, and how many edges matched an import
(hardware `hal_calls` + scaffolding `scaf_call_count`). The same probe
on ReactOS `tests/data/serial.sys` (PE32, image_base 0x10000) is the
control: the 32-bit mechanism must show matches there.

## Predictions

1. i8042prt.sys: IAT-kind edges recorded > 0 (the branch IS entered;
   Ghidra finds 509 `CALL qword ptr [abs]` sites, ours will be near that
   minus desync losses); matched = 0; names attributed = 0;
   max(target_addr) < 0x100000000 ≤ min(iat_abs). The owner's "worse
   case" (a confident wrong name) does NOT occur on this input.
2. ReactOS serial.sys control: matched > 0 (the mechanism works on PE32).
3. Named alternative: any matched edge on i8042prt.sys means the
   arithmetic above is wrong somewhere (e.g. imports stored with a
   32-bit base) and the register's "never" must become "sometimes,
   wrongly", which is the worse finding.

## What this decides for the (a) fix

If prediction 1 holds, the semantic.c change for (a) is a REPAIR: the
branch already exists and already computes a target; it needs the RIP
marker accepted and the target resolved as instruction address +
length + disp instead of the raw disp. No rewrite.

---

## Outcome (appended after the run; log `iat-xref-2026-09-17.log`)

Instrument: `translator -t report` gained a `summary.call_graph` block
(private commit after 6041c5f; semantic.c). First revision counted only
CLASSIFIED matches and read 0 on the nmap control although its targets
lay inside its IAT range; corrected to count slot EQUALITY separately
from classification before any number was quoted.

| binary | iat_edges (entered) | iat_slot_hits (== any slot) | classified matches | max target | min slot |
|---|---:|---:|---:|---|---|
| i8042prt.sys (HP PE32+) | 523 | **0** | 0 | 0xFFFFF2A5 | 0x1C0011000 |
| serial.sys (ReactOS PE32 control) | 275 | 275 | 245 | 0x191B4 | 0x19100 |
| nmap_service.exe (PE32 control) | 45 | 44 | 0 | 0x40E254 | 0x40E18C |

Prediction 1 holds: the branch IS entered on the HP driver (523 times;
Ghidra counts 509 `CALL qword ptr [abs]` sites, the excess being
desync-born decodes), and it can never hit a slot there: every target
is a 32-bit value and every slot is above 4 GiB. Zero names are
attributed, right or wrong. Prediction 2 holds (275/275 on PE32). The
nmap control's 0 classified with 44 hits is the classifier's vocabulary
(CRT/kernel32 imports it does not know), not the cross-reference.

**Register correction:** "can never match on x64" is now MEASURED on
one HP driver and DERIVED from the arithmetic for all eight (same
image base 0x1C0000000). The owner's worse case (a confident wrong
name) does not occur on these inputs.

**For the (a) fix:** REPAIR, not rewrite. The branch exists, is
entered, and computes a target; it needs to accept the RIP marker
(base 32) and resolve the target as instruction address + length +
disp instead of the raw disp. Nothing else in semantic.c depends on
the base sign (grep 2026-09-15).
