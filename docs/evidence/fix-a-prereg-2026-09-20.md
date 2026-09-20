# Pre-registration: fix (a), RIP-relative addressing (2026-09-20)

Owner ruling 2026-09-19/20: **(a) before (o)**. Written before any
line of `src/` changes. (o) keeps its enumeration and pre-registration
and goes next, unchanged.

**A decoder-only (a) is a regression by construction.** The decoder
half and the resolver half land in one commit or not at all: marking
RIP makes the resolver's base-less test stop matching, so IAT edges
fall toward zero with slot hits still zero — a worse state than today,
reached by fixing something. The mechanism is under "The interaction"
below; it is stated here because it governs the shape of the work, not
just its detail. Found by enumerating the readers of the operand base
field *before* writing a line (rule 24).

## Why (a) first: three justifications, weakest to strongest

1. **Row count.** `addr` is the differential class (a) moves:
   ≈40,856 rows corpus-wide against (o)'s entire residual of 129.
2. **The product layer.** The resolver records 12,979 IAT edges no
   import backs and matches **0** on every 64-bit driver, while by
   bytes 10,714 of 12,890 memory-indirect calls do target a real
   import thunk slot (measured 2026-09-19, both instruments).
3. **(a) is the only thing between a working emitter and any 64-bit
   output — measured on the emitter's own output.** `STRIP` lines:
   both PE32 controls classify in both directions (ReactOS serial 9
   kept / 25 scaffolding / 2 unclassified; beep 3 / 6 / 0). All eight
   64-bit drivers recognise **zero** scaffolding, and disk, HDAudBus,
   pci and usbxhci keep **zero** functions of 193, 346, 1642 and 1466.
   Classification attributes imports to call sites through the
   cross-reference that matches zero on 64-bit, so a 64-bit driver's
   Forth output today is a catalog header plus a manifest of
   unclassified addresses. This is stronger than the row count because
   it is measured on what the product emits.

## The defect, read from source: two halves that must land together

**Decoder half.** `x86_decoder.c:142` handles ModRM `mod=00, rm=101`
and its own comment (line 143) names it: *"disp32 only, no base
register (RIP-relative in 64-bit mode: defect a)"*. Probed today:
`FF 15 10 00 00 00` at 0x1000 → `type=MEM base=-1 index=-1
disp=0x10`; `48 8D 05 10 00 00 00` → same shape. In 64-bit mode that
encoding is RIP+disp32, so the operand is emitted as an absolute
address that is really an offset.

**Resolver half.** `semantic.c` enters its IAT branch on
`ins->dest.type == UIR_OPERAND_MEM && ins->dest.reg < 0 &&
ins->dest.index < 0` and computes
`call_target = (uint64_t)(uint32_t)ins->dest.disp`. The branch is
entered *because of* the decoder half (base −1 reads as "no base"),
and the raw offset is then compared against slots above 4 GiB, so it
can never hit. That is the measured 12,889 edges / 0 hits.

**The interaction, pre-registered because it would otherwise look like
a regression.** `uir.c:124` copies `op.reg = x86->operands[idx].base`.
The moment the decoder marks RIP (a new base value), `reg < 0` becomes
**false**, the resolver's branch stops being entered at all, and edges
fall from 12,889 toward **0 with hits still 0** — the product would go
from wrong edges to no edges. **The two halves therefore land in one
commit**; a decoder-only (a) is a regression by construction, and this
paragraph is the prediction that says so before the run.

## Rule 24: readers of the operand base field, enumerated from source

A base value that does not exist today (RIP) is introduced, so every
reader of `.base` is named before a line changes:
- **bridge copies**, field-for-field, both `int8_t`, RIP=32 fits:
  `translator.c:147`, `test_pipeline.c:182,280`.
- **`uir.c:124`** → the UIR operand's `reg` (`uir.h:105`, `int8_t`).
  This is the reader the interaction above runs through.
- **`uir.c:633`** `op->base_reg = prev->operands[1].base` (struct
  offset from a previous MOV): must not read RIP as a GPR.
- **`semantic.c`** IAT branch: the site being repaired; its test
  becomes "absolute (`reg < 0`) **or** RIP (`reg == 32`)", with the
  target computed per case.
- **`dump_starts.c:64,68,76`** — **already prepared, and now
  exercised**: it has a `base == 32` arm that prints
  `address + length + disp` and a comment citing the register map
  (`operand-diff-prereg-2026-09-15.md`: 0-15 GPR, 16-19
  SPL/BPL/SIL/DIL, **32 RIP**). The differential harness therefore
  needs no change for (a), and the `addr` rows resolve as soon as the
  decoder emits base 32.
  **That arm had never executed** (no operand carries base 32 today),
  so it was green by vacuity and its first run would have been (a)'s
  own run, while reporting on ≈40,856 rows; an off-by-one-instruction
  error in `address + length + disp` is the classic mistake in exactly
  that computation, and it would have made a correct (a) look broken.
  Owner ruling 2026-09-20: red-test the instrument first.
  `tests/test_dump_starts_arm.c` (private `f42cc25`, wired into
  `test-all`) includes the tool as a translation unit with its `main`
  renamed, so **the arm itself** is exercised rather than a copy of
  its arithmetic. Expected values come from the pinned fixture-v12
  oracle rows: the LEA at `0x401003`, length 7, displacement `0x10`
  must render `0x40101a`. Five assertions — the oracle target, a
  negative displacement keeping its sign, resolution relative to the
  instruction **end** rather than its start, and two controls (the
  absolute arm, a real base register) — **all pass. The instrument is
  sound before (a) leans on it.**
- **test assertions on specific base values**: `test_x86_decoder.c`
  404, 421, 434, 529, 547, 730, 738, 781, 870, 889, 1016, 1692 —
  the (a) red at 730/738 already asserts `base != -1` and a value
  outside 0-15.
- **header**: `X86_REG_RIP` **does not exist** and is added as 32,
  matching the pinned register map and the dump tool's existing arm.

## What (a) must not do

- **Not credit itself with classification-vocabulary gaps.** The
  ReactOS controls' 30 and 15 unclassified matches and nmap's 44 are
  vocabulary, frozen and measured separately
  (`vocab-freeze-tier1-prereg-2026-09-20.md`). (a)'s measure is
  `iat_slot_hits`, never `iat_matched_classified`.
- **Not refuse the Control Flow Guard calls.** 2,176 corpus-wide go
  through each image's load-config `__guard_dispatch_icall_fptr` cell
  (one distinct address per image). They get their own edge kind, not
  a refusal and not an IAT edge. The loader does not expose that cell
  today; its red is minted in this commit with the plumbing.

## Predictions, per class and per input, never a headline

**Report, per 64-bit driver:** `iat_slot_hits` 0 → ACPI 3307,
usbxhci 1294, pci 2423, storport 2031, HP serial 465, i8042prt 457,
disk 346, HDAudBus 391 (the by-bytes exact-slot counts).
`iat_edges` falls by each image's CFG count once CFG is its own kind
(ACPI 3724 → 3307, usbxhci 2199 → 1294, …).
`iat_matched_classified` rises to **at most** the slot hits and is
capped by the frozen vocabulary, so it is predicted **below** the hit
column on every input and is not (a)'s measure.

**32-bit controls: every column identical.** They are the control for
(a) precisely because their slot equality already works.

### Second prediction: the two columns must diverge

An observation found while capturing the widening's before-state, now
converted to a forward prediction (owner, 2026-09-20: a corroboration
you do not convert is evidence you only get to use once).

**Observed before (a):** on **every** 64-bit driver
`hardware_functions` *equals* `port_io_functions` exactly — ACPI 13/13,
i8042prt 2/2, HP serial 31/31, storport 20/20, and disk, HDAudBus, pci,
usbxhci all 0/0. On the ReactOS PE32 control they differ, 9 against 8:
one function is hardware by HAL attribution. The only surviving route
to `is_hardware` on 64-bit is a literal IN/OUT instruction.

**Predicted after (a):** the columns **diverge on all eight**,
`hardware_functions` > `port_io_functions`, because HAL attribution
starts working. Bound, measured by bytes today (call sites targeting a
slot whose import name carries a hardware category in the frozen
146-entry vocabulary; 49 such names):

| input | hw slots | call sites to them | `hw_functions` now | predicted |
|---|---|---|---|---|
| ACPI | 10 | 46 | 13 | > 13, ≤ 13+46 |
| HDAudBus | 8 | 33 | **0** | **> 0**, ≤ 33 |
| disk | 3 | 4 | **0** | **> 0**, ≤ 4 |
| i8042prt | 8 | 61 | 2 | > 2, ≤ 2+61 |
| pci | 10 | 31 | **0** | **> 0**, ≤ 31 |
| HP serial | 8 | 53 | 31 | > 31, ≤ 31+53 |
| storport | 13 | 98 | 20 | > 20, ≤ 20+98 |
| usbxhci | 8 | 82 | **0** | **> 0**, ≤ 82 |

**Sharpened to eight exact numbers (owner, 2026-09-20: a bound is a
prediction that has not finished being made).** The range above was
wrong to call its lower end strict: sites > 0 guarantees attribution
happens, not that a *new* function gets marked — on ACPI, i8042prt, HP
serial and storport every new site could land inside a function already
counted, and a correct (a) would leave the column unmoved. So the
quantity is measured instead of bounded.

Two sets are countable by bytes today: the functions the translator
already marks hardware (its own `hardware_functions` array, addresses),
and the functions containing a call site to a hardware-marked import
slot (`.pdata` extents, objdump's resolved targets). **The predicted
post-(a) value is the size of their union.** It is exact, not a lower
bound, because `sem_propagate_callgraph` propagates **scaffolding
only** — read from source: it sets `has_scaffolding` /
`transitive_scaffolding`, never `is_hardware`, and a hardware callee
*blocks* the propagation. No function can become hardware except by
carrying its own evidence.

| input | hardware now | + functions with a hw-slot call site | **predicted after (a)** |
|---|---|---|---|
| ACPI | 13 | 36 | **47** |
| HDAudBus | 0 | 21 | **21** |
| disk | 0 | 3 | **3** |
| i8042prt | 2 | 29 | **31** |
| pci | 0 | 29 | **29** |
| HP serial | 31 | 23 | **48** |
| storport | 20 | 73 | **93** |
| usbxhci | 0 | 58 | **58** |

`port_io_functions` is predicted **unchanged on all eight** (a RIP
repair adds no IN/OUT instruction), so the two columns diverge on all
eight, which was the point. Assumption stated: function extents come
from `.pdata`, while the translator uses exports **plus** `.pdata`, so
a site inside an export-only function is not counted here; that is the
one way the observed value could exceed the prediction, and it is
checkable by name.

**A control fired while measuring this, and it found phantoms.**
Counting by bytes the functions that contain a port instruction should
reproduce `port_io_functions` exactly. It does on six of eight; on
ACPI it reads 11 against 13 and on storport 12 against 20. Read at
those addresses: every one of the eight unexplained storport functions
contains **exactly one port operation in our decode that objdump does
not see** (seven `INSB`, one `IN`), and the same on ACPI's two. They
are desync-born phantoms — the class that suspended `test-hp-drivers`
and produced the rtl8139 phantom `OUT`s. **They are (o)-owned, not
(a)'s:** storport's 20 is 12 real (6 plain, 6 `REP` Buffer variants)
plus 8 phantom; ACPI's 13 is 11 plus 2. They persist through (a), so
they are inside the predicted union above, and **(o) is predicted to
remove exactly them**, taking storport 93 → 85 and ACPI 47 → 45 when
it lands. That is a forward prediction for (o), banked here.

### The desync exemption, its form decided before the run

The standing rule — every row leaving `operand_ok` is read from bytes
and named, or the fix stops — was written for movements of a few dozen
rows. (a) moves ≈40,856. At that volume the rule collides with
arithmetic and gets quietly relaxed mid-run, which is worse than either
keeping it or replacing it, so it is **replaced deliberately here,
before the run**, on the same principle that parked the INIT rows by a
rule rather than by the number 34:

> **A row leaving `operand_ok` is accounted BY RULE when its
> instruction carries a RIP-relative operand whose printed value
> changed. Every row outside that rule is read from bytes and named,
> and the two counts are reported separately.**

The by-rule class is mechanical and expected: those rows were
`operand_ok` only because both sides printed the same wrong absolute,
and the repair makes ours right where Ghidra was already right (they
move *into* `ok`) or reveals a genuine disagreement (they move out,
by rule). The named class is where a surprise can hide, and it keeps
the expensive reading pointed at rows that could be telling us
something.

**Why the rule is complete — which turns a reading instruction into a
gate.** (a) reinterprets `mod=00 rm=101`; it does not re-size it. A
RIP-relative encoding is the same number of bytes before and after, so
**`nostart` must be identical on every input**, no re-sync point moves,
and therefore no row can leave `operand_ok` except at an instruction
whose own operand value changed — which is exactly the rule's scope.
**A row outside the rule is therefore not merely unexplained: its
existence is evidence that (a) changed a length, which (a) must not
do.** It stops the fix because it falsifies the fix's shape, not
because it is unread. `nostart` identical on all sixteen inputs is
itself a gate condition, checked before the class counts are read.

Both counts, and the by-rule class's per-input totals, are reported in
the closing matrix; a by-rule count that exceeds the input's
RIP-relative operand count is itself a finding (a rule that can
over-fire needs its own ceiling).

**One design consequence to decide with the CFG edge kind, measured
here so it is not met mid-run.** `sem_propagate_callgraph` vetoes any
function carrying an `SEM_EDGE_UNRESOLVABLE` edge: it is permanently
unclassified. **1,339 functions across the eight drivers contain a
Control Flow Guard dispatch call** (usbxhci 485 of 1452, ACPI 322 of
2549, pci 201, storport 121, HDAudBus 117, i8042prt 49, disk 36, HP
serial 8). If the CFG edge kind is made unresolvable, scaffolding
propagation is silently switched off for a third of the corpus's
functions. The CFG kind is therefore **resolved-but-not-IAT**, and the
veto set is predicted **unchanged** by (a).

**Differential:** `addr` is the class that moves, ≈40,856 rows, and
the harness already resolves base 32, so those rows resolve as soon as
the decoder emits it. Per-input `addr → ok` predictions are written
from the reclassification log immediately before the run.

**The exemption, named in advance.** Repairing a RIP-relative target
changes an operand *value*, so a row that is `operand_ok` today only
because both sides printed the same wrong thing can move **out** of
`operand_ok` — the `.text+0x69d4c` lesson at a scale an order of
magnitude past anything the invariant has been exercised on. Any row
leaving `operand_ok` is read from bytes and named, exactly as a
desync-run exemption is named; an unnamed row leaving stops the fix.

## Gate

XPASS on `x64_RED_lea_rip_relative` and on the resolver's refusal red
`sem_RED_a_iat_resolver_refuses_non_iat_target`; the CFG red minted
with the plumbing and green in the same commit; every other XFAIL
holds; both sweeps unchanged (the one-byte table is not consulted by
the ModRM path); full `make test` green; then ONE differential.
