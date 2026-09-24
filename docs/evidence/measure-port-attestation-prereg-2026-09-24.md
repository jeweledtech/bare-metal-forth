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
