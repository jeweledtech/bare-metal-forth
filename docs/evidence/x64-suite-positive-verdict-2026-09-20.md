# Result: what the x86 decoder suite does see (2026-09-20)

Three weeks of this arc have measured what the suite **cannot** see —
vacuous reds, a green test defending a defect, expectations read off
the product, an apparatus structurally incapable of seeing a corrupt
link. This is the first measurement of what it **does** see, and it is
recorded as a result rather than as a step in something else.

## The measurement

`tools/translator/scripts/rule30_sweep.py`, banked at
`docs/evidence/x64-rule30-sweep-2026-09-20.log`. For every **passing**
test that decodes a literal byte array, the test's own bytes are
disassembled in the test's own mode by a second instrument and the
assertion is compared. Reds are excluded: their expectation is the
oracle and they are meant to fail.

| predicate | swept | confirmed | disagrees |
|---|---|---|---|
| asserted **length** vs objdump | 65 of 85 | **65** | **0** |
| asserted **identity** vs objdump | 62 of 85 | **62** | **0** |

**127 expectations independently confirmed against a second
instrument.** Denominator printed, remainder named, alias table and
parsing contract both hashed into the log.

## What the sweeps found while confirming the rest

- **One real defect.** `0F 0D C0` is the register form of `PREFETCH`
  and is `#UD` — oracle NONE, screen `(bad)` — while its memory forms
  are 3 and 7 in both. A test asserted length 3 for an encoding that
  has no length. It is now a red under (t).
- **Nine identity expectations**, found earlier by symptom rather than
  by predicate, each naming a real instruction in its comment and then
  asserting it was a no-op. All nine converted.
- **Four rows that are neither.** `06`, `82`, `60`/`61` and `8F /1` are
  refused by *both* instruments, which therefore attest no length at
  all. The suite's "length stays 1" on those is this decoder's
  **refusal policy** — registered by
  `x64_RED_n_invalid_walk_continues` — and objdump's competing 1 or 4
  is objdump's own. A refusal is not a disagreement and the sweep
  scores it in its own bucket.

## The remainder, named rather than claimed

These predicates check the **length** and the **mnemonic**. An operand
count, a register number or an immediate copied from the decoder is the
same defect and neither predicate would see it. **No instrument covers
that today.** Sixteen tests are unswept on length and 23 on identity,
each listed with its reason in the log; six of them probe
redundant-prefix behaviour, which objdump cannot adjudicate because it
prints the prefix as its own pseudo-instruction, and those need the
pinned oracle instead.

## Why it counts as a result

An expectation that agrees with a second instrument is not proof the
decoder is right — it is proof the *test* is not merely a snapshot of
the decoder. That is the property the thirtieth rule exists to protect,
and 127 of them now have it on the record with the exact predicate that
established it, so the number can be re-taken rather than re-asserted.
