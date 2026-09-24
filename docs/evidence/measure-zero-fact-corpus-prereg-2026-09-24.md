# The zero-fact rate across the corpus: pre-registration (2026-09-24)

**Written before the run.** Owner ruling, 2026-09-24. This goes ahead of
(bi)'s 15.

The product's named weakness is **hardware functions classified on import
evidence alone, with no instruction-derived fact**. It has been measured only
on the HP eight: 0 of 320 on 2026-09-21, 319 of 320 zero-fact since stage 2,
and **265 of 266** after (bl). This run measures it across every kernel
driver, reports the HP eight separately, and so answers whether the machine
everything was calibrated on is representative.

## Definition (the spec's, `consumer-spec-2026-09-21.md` §1, unchanged)

A hardware function carries an **instruction-derived fact** if its
`ports_accessed` is non-empty, or any of its `mapped_regions` has stage-2
`accesses`. Otherwise it is **zero-fact**: hardware on import evidence alone.

## Instrument and population

- The shipped report (`bin/translator` `1560da9a91319b0d`) over the
  **1,322** distinct kernel drivers, parsed per function.
- Rows: each machine set (**Dell, Older ASUS, Newer ASUS, hp_i3**, and the
  **Dell 26100 System32**), counted within the set, plus the corpus total by
  distinct sha256. A driver present on several machines is counted once in
  the total and once per set, so the set rows **do not sum to the total**.
- **The Mac set is out of scope**: it is Mach-O userland, and has no
  kernel-driver report.
- **Control:** the hp_i3 row must reproduce **266 hardware, 1 with a fact,
  265 zero-fact**. If it does not, the run is void.

## Predictions

| # | prediction |
|---|---|
| Z1 | hp_i3 reproduces 266 / 1 / 265 (the control) |
| Z2 | corpus-wide, the zero-fact share of hardware functions is **≥ 97%** (range 95–99.9%) |
| Z3 | hardware functions **with** an instruction-derived fact, corpus-wide: **150** (range 50–400). Nearly all are expected to come from stage-2 accesses; `ports_accessed` needs an immediate port, which the modern drivers do not use (finding (z)) |
| Z4 | **every** machine set's zero-fact share is within **2 points** of the corpus-wide share, so HP is representative on this measure |

**Independent checks: one instrument, plus a control** (Z1). The per-set rows
come from the same run.

---

## Outcome

*(below this line, from the artefact only)*

**Inputs:** `bin/translator` `1560da9a91319b0d`; `zero_fact.py` and
`zf_port_attest.py`; results `zero-fact-result.tsv` and
`zero-fact-port-attest.json` in `~/corpus/tools-2026-09-24/SHA256SUMS`.
0 empty outputs.

### The raw reading (not a rate: see below. **Do not quote 91.23%**; the corpus zero-fact rate is *unmeasured, bounded 91.2–99.9%*)

| set | drivers (with any hw) | hardware functions | with a fact (ports / stage-2) | zero-fact |
|---|---|---|---|---|
| **hp_i3** (control) | 8 (7) | **266** | **1** (0 / 1) | **265 = 99.62%** |
| Dell | 428 (261) | 3,398 | 243 (241 / 2) | 3,155 = 92.85% |
| Older ASUS | 433 (259) | 3,368 | 324 (319 / 5) | 3,044 = 90.38% |
| Newer ASUS | 485 (294) | 3,945 | 353 (350 / 3) | 3,592 = 91.05% |
| Dell 26100 System32 | 14 (13) | 192 | 46 (46 / 0) | 146 = 76.04% |
| **corpus, distinct** | **1,322 (788)** | **10,751** | **943 (932 / 11)** | **9,808 = 91.23%** |

| # | predicted | observed |
|---|---|---|
| Z1 | HP reproduces 266 / 1 / 265 | **held**: the run is valid |
| Z2 | corpus zero-fact ≥ 97% (95–99.9%) | **missed on the raw reading: 91.23%.** But see below: the raw numerator is not trustworthy |
| Z3 | ~150 functions with a fact, mostly stage-2 | **missed twice**: 943, and **932 from ports, 11 from stage 2**. The composition is the reverse of the prediction |
| Z4 | every set within 2 points of the corpus | **missed on the raw reading**: HP is 8.4 points off |

### The port facts are contaminated: this is (z) at corpus scale

`ports_accessed` comes from immediate-port `in`/`out` instructions in the
linear decode. Finding (z) showed one of those fabricated inside a desync run
(storport's `0xFC`). Here it is at scale:

- **`ClipSp.sys` alone (three copies) holds 520 of the 932 port-fact
  functions**, with **218–236 distinct "ports"** per copy across the whole
  byte range. ClipSp is the licensing driver, which ships protected, so its
  bytes need not decode as instructions.
- `ntoskrnl.exe` shows 98 distinct ports. `RTKVHD64`, `PEAuth` and `drmk`
  show 20–60. `cng.sys` has 25 (function, port) pairs, and **0** of them match
  an objdump `in`/`out` in the same function.
- **"Attested by objdump" is not independent here.** objdump also sweeps
  linearly, so it reads the same non-code bytes as the same `in`/`out`. That
  is two instruments sharing one failure mode. 548 of the 932 port-fact
  functions are "fully attested", and that proves agreement, not code.
- **The plausible ones look like real hardware code.** **102 of the 136**
  drivers with port facts use **≤ 4 distinct ports**, covering **143**
  port-fact functions. `DellInstrumentation.sys` uses exactly
  {0x81, 0xB0, 0xB2, 0xB4} (0xB2 is the SMI command port). `VBoxSup.sys`
  uses {0x3F8, 0x3FD}, which is COM1.

**Value spread is a reasoned test, not a per-instruction proof.** The
discriminating experiment is a flow-following disassembler (the Ghidra
oracle): are ClipSp's `in`/`out` addresses instructions reached by control
flow? It is not run here.

### What can be stated: bounds, not a rate

| reading | with a fact | zero-fact share |
|---|---|---|
| every port fact real (the raw reading) | 943 | **91.23%** (lower bound) |
| only stage-2 facts real | 11 | **99.90%** (upper bound) |
| *post hoc*: port facts real only in drivers using ≤ 4 distinct ports | 143 + 11 = 154 | 98.57% |

The third row's cut was chosen **after** seeing the data. It is labelled post
hoc and is not scored.

**HP's representativeness is therefore undetermined.** It is 8.4 points off
on the raw reading and about 1 point off on the plausible one. It cannot be
settled until the port facts are attested by an instrument that does not
share the linear sweep's failure.

**The product finding, which does not depend on which bound holds:**
`ports_accessed` is printed as an instruction-derived fact **with no check
that the bytes it came from are code**. On today's corpus, **56% of the
port-fact functions (520 of 932) sit in one licensing driver**, whose value
spread (218–236 distinct ports per copy) makes fabrication the likely reading.
"Likely" is reasoned from the spread; it is not established per instruction.
**The instruction-derived count that rests on a walk rather than a sweep is
11** (stage 2), against 10,751 hardware functions.

**The model that missed**, recorded as one: the four predictions assumed
the corpus looks like the HP eight (clean Microsoft inbox drivers). It
contains protected third-party and licensing binaries, where the linear
sweep manufactures facts.

### Owner ruling, 2026-09-24, and the free control

**The corpus zero-fact rate is unmeasured, with bounds 91.2%–99.9%.** It is
not a rate, and 91.23% is not quoted as one in any store. The commit message
of `412f5da` quotes it and cannot be amended; this line supersedes it. HP's
representativeness is **undetermined**.

**The System32 control, checked before reasoning from its label.** The owner
suggested those 46 port facts might sit in user-mode images, where `in`/`out`
would fault at ring 3. **They do not.** All 14 System32 images are **kernel
mode** (Subsystem NATIVE), so the ring-3 argument does not apply. The 46 sit
in `ntoskrnl.exe` (38), `ci.dll` (3), `skci.dll` (3), `kdnet.dll` (1) and
`f3ahvoas.dll` (1).

**`f3ahvoas.dll` is the positive control anyway, with no oracle.** It is a
keyboard-layout DLL. It has **no `.text`**; its only executable section is
`.data` (0x1000, 0x1400 bytes), which holds **49 UTF-16 key names**
("Down", "Left", "Home", "Ctrl", "Num /", …). The product reports a hardware
function `func_180001000` with **port 0xFA**, from `e6 fa` (`out %al,$0xfa`)
at `0x180002261`, between `pop %rsp` / `sbb $0x67,%al` and
`rolb $1,0x46(%rdx)` inside that table. The section is also full of
`insl`/`outsb`: the letters `l`, `m` and `n` (0x6C–0x6E) decoded as string
I/O. **The product prints a port access fabricated from a keyboard table.**
That proves the failure exists. It does not give its rate, which still needs
the attestation.

**The defect, minted as `(bn)` before any Ghidra run** (owner ruling 2). The
design question is answerable today. The lifter records a port for **every**
`in`/`out` in the function's linear range (`uir.c`, `add_port` on each
`UIR_PORT_IN`/`OUT`), with no check that the bytes are code. So it prints a
sweep-derived value as instruction-derived evidence.
- Red: `uir_RED_bn_unreachable_port_not_recorded`. `ret; out $0x60,%al; ret`
  records 0x60 today.
- Guard, green: a reachable `out` is still recorded.
- **The pass state is necessary, not sufficient**: reachability from the
  entry would not reject garbage reached by linear fall-through, which is how
  `f3ahvoas`'s table is reached from `func_180001000`. That residual is stated
  now, not discovered later.

**Next, per ruling 4:** the Ghidra attestation of reachability, with
positives first (serial.sys, i8042prt.sys: their known `in`/`out` must be
reached) before any zero is read.
