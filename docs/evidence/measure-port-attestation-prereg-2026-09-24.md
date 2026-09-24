# Port facts attested by reachability (Ghidra): pre-registration (2026-09-24)

**Written before any Ghidra run.** Owner ruling, 2026-09-24. This goes
ahead of (bi)'s 15. It settles the corpus zero-fact rate (**unmeasured,
bounded 91.2–99.9%**) and HP's representativeness with one measurement.
Outcomes go BELOW the line.

## Instrument

- **Oracle:** Ghidra, pinned (snap revision 47, `/snap/ghidra/47/ghidra`),
  headless auto-analysis, followed by the harness's `InstrStarts.java`. That
  lists every instruction Ghidra's **flow-following** analysis produced, by
  section and offset, with its mnemonic. **Every dump is regenerated fresh**
  from the corpus file, and its input sha256 is logged. No old dump is reused.
- **Our side:** the translator's own port sites, `port_in`/`port_out` lines
  in `-t uir` (address and function), for every function the report lists
  with `ports_accessed`. Not objdump: objdump shares the linear sweep's
  failure mode.
- **A port site is attested** if Ghidra lists an `IN` or `OUT` instruction
  starting at the same address. **A port-fact function is attested** if at
  least one of its immediate-port sites is attested.

## Controls, run first (positives before zeros)

- **Positive:** HP `serial.sys` and `i8042prt.sys`. Their in/out are real
  code; serial's are the 135 DX-form port accesses of its register routines.
  **Void unless ≥ 95%** of each driver's UIR port sites are attested.
  *The known risk the owner named:* on a protected driver, Ghidra failing to
  reach real code is as available an explanation as the code not being real.
  The positives only show that the oracle reaches ordinary code.
- **Negative, known from bytes:** `f3ahvoas.dll`'s `out %al,$0xfa` at
  `0x180002261`, inside a keyboard-layout table. **Predicted not attested.**
  If Ghidra lists it, Ghidra is decoding the table too, and a Ghidra "yes"
  cannot count as attestation for images like it.

## Population

The **136** drivers whose reports carry port facts (`zero-fact-port-attest.json`),
**932** port-fact functions. Drivers are processed by distinct sha256.

## Predictions

| # | prediction |
|---|---|
| A1 | serial.sys and i8042prt.sys: **≥ 95%** of UIR port sites attested (the control) |
| A2 | f3ahvoas's 0xFA site: **not attested** |
| A3 | ClipSp.sys (3 copies, 520 port-fact functions): **< 10%** of its port-fact functions attested |
| A4 | the drivers using ≤ 4 distinct ports (the post hoc cut, now **tested** rather than assumed): **≥ 80%** of their 143 port-fact functions attested |
| A5 | corpus-wide attested port-fact functions: **150** (range 80–300) of 932. Zero-fact = (10,751 − attested − 11) / 10,751, **≈ 98.5%** (range 97.1–99.2%) |
| A6 | HP's 99.62% is then **within 2 points** of the corpus rate, so HP is representative on this measure once the fabrication is removed |

**Independent checks: the oracle, with its two controls.**

---

## Outcome

*(below this line, from the artefact only)*

**Inputs:** Ghidra snap 47; `bin/translator` `1560da9a91319b0d`;
`port_attest_ghidra.py`. Results `port-attest-ghidra-{controls,result}.json`
in `~/corpus/tools-2026-09-24/SHA256SUMS`. **136 of 136** fresh dumps were
produced (0 oracle missing). Each dump is keyed by its input's sha256.

| # | predicted | observed |
|---|---|---|
| A1 | positives ≥ 95% attested | **held**: serial.sys **135 of 137** UIR port sites (98.5%), i8042prt.sys **2 of 2** |
| A2 | f3ahvoas's 0xFA site not attested | **held**: Ghidra lists only **5** instructions in the whole image, and **0 of 48** of its port sites. It does not decode the keyboard table |
| A3 | ClipSp < 10% attested | **missed: 127 of 520 (24%)** |
| A4 | ≤ 4-port drivers ≥ 80% attested | **missed badly: 27 of 143 (19%)**. The ≥ 20-port drivers came out **192 of 702** (27%) |
| A5 | attested ~150 (80–300); zero-fact ≈ 98.5% (97.1–99.2%) | **220** attested (inside the range, not the point); zero-fact **97.85%** (inside the range) |
| A6 | HP within 2 points of the corpus | **held**: HP 99.62% against the corpus's 97.85%, **1.77 points** |

### The value-spread hint was wrong, and reachability says why

- **Real, attested in full:** `DellInstrumentation.sys`, **7 of 7**
  port-fact functions and **21 of 21** sites. Ghidra lists `IN AL,0x81` /
  `OUT 0x81,AL` and `OUT DX,AL` exactly where our UIR has them.
- **Few distinct ports, attested zero:** `iaStorVD.sys` (**5,526** UIR port
  sites, **0** in Ghidra's listing), `WdDevFlt.sys` (545–569, 0) and
  `Netwtw10.sys` (364, 0). **Fabrications can concentrate on a few values.**
  The ≤ 4-port cut in the zero-fact outcome was post hoc **and wrong**, and
  it stays unscored.

### The rate, per set, with attested port facts

| set | hardware | attested port-fact fns | stage-2 | zero-fact |
|---|---|---|---|---|
| hp_i3 | 266 | 0 | 1 | **99.62%** |
| Dell | 3,398 | 47 | 2 | 98.56% |
| Older ASUS | 3,368 | 87 | 5 | 97.27% |
| Newer ASUS | 3,945 | 64 | 3 | 98.30% |
| Dell 26100 System32 | 192 | 24 | 0 | 87.50% |
| **corpus, distinct** | **10,751** | **220** | **11** | **97.85%** |

**One caveat that bounds it, stated.** On protected code the oracle's risk
runs in the direction opposite to the one the controls tested. Ghidra
following control flow *into* obfuscation junk is as available as Ghidra
missing real code. The controls show that Ghidra reaches ordinary code (A1)
and does not decode a data table (A2). They do not show that a Ghidra "yes"
inside ClipSp is code. Counted with and without ClipSp's 127:

| ClipSp's 127 attested sites | corpus zero-fact |
|---|---|
| counted as real | **97.85%** |
| not counted | **99.03%** |

**The corpus zero-fact rate is 97.85%–99.03%**, narrowed from 91.2–99.9%.
**HP is representative on this measure:** it is 1.77 points from the
pessimistic end and 0.6 from the other. The three machine sets sit at
97.3–98.6%. The one outlier is the System32 kernel images (87.5%, including
ntoskrnl), which may well be genuine port I/O. That is not established here.

### What this prices

- **(bn):** **712 of the 932** port-fact functions (76%) carry port facts that
  Ghidra's flow does not reach. That is the upper bound on what a
  reachability guard could remove. How many (bn)'s pass state, reachability
  inside the function, would actually remove is **not measured**: some of
  the 712 are reached by linear fall-through, the residual (bn) already
  names.
- **The product statement.** Across 10,751 hardware functions on the 1,322
  kernel drivers, **231–242 carry an instruction-derived fact the oracle
  confirms** (11 stage-2, plus 220 attested ports, or 93 without ClipSp).
  **Everything else the product calls hardware rests on which DLL a driver
  imports.**

**The model that missed**, once more recorded as one: I trusted the value
spread twice, first as a fabrication signal and then as a reality signal,
and both times reachability overruled it. Distribution found the problem.
Only reachability can measure it.
