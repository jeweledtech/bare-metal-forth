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
