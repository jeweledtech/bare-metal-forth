# Pre-registration: fix (af), the lifter drops seventeen identities (2026-09-21)

**(af) is PROMOTED from parked to prerequisite, and this document is
the record of the promotion.** It was parked on 2026-09-20 with a
minting condition — "(ad) lands first and establishes the shape of a
non-`NOP` default; (af)'s red is written against that shape". (ad) has
landed, and (af) is now a **dependency of the identity consumer**: a
consumer that reads instruction identity must not read a no-op where an
`SBB` was.

**It is larger than (ad) was, which is why it gets its own
pre-registration rather than riding along.** (ad) was one identity and
one corpus row. (af) is **seventeen identities and 1,089 corpus rows**.

## 1. The seventeen, with their corpus counts

Read from the 16 banked decoder dumps, mnemonic by mnemonic, `SETcc`
matched across all sixteen spellings and `.LOCK` suffixes stripped:

| identity | rows | identity | rows |
|---|---|---|---|
| `SBB` | **481** | `ADC` | 9 |
| `SETcc` | **469** | `ROL` | 9 |
| `CBW` | 52 | `CLD` | 0 |
| `CDQ` | 32 | `LOOP` | 0 |
| `LEAVE` | 23 | `POPAD` | 0 |
| `ROR` | 14 | `PUSHAD` | 0 |
| | | `STD` | 0 |
| | | `REP_MOVSB/MOVSD/STOSB/STOSD` | 0 each |
| **total** | | | **1,089** |

**Five of the seventeen have a corpus count of zero, and that is
printed rather than omitted** — zero-measured is not zero-found.

**The two that matter are ordinary integer code**: subtract-with-borrow
and condition-flag stores, 950 of the 1,089 between them. That is
precisely what a reader assumes was covered.

## 2. The fix: a third state, not seventeen guesses

`UIR_UNSET = 0` means nobody assigned. `UIR_INVALID` means the decoder
refused. **Neither covers "the decoder named it and the lifter does not
model it"**, which is what all seventeen are.

**So (af) adds `UIR_UNMODELLED` and maps all seventeen to it.**

**It deliberately does NOT invent semantics.** The 41 existing UIR
opcodes have no honest target for these:

- `ADC`/`SBB` → `ADD`/`SUB` would **drop the carry**, which is the same
  class of lie the whole arc has been removing.
- `ROL`/`ROR` → `SHL`/`SHR` would **drop the wrap**; a rotate is not a
  shift.
- `SETcc`, `CBW`/`CDQ`, `LEAVE`, the `REP_` string forms → no
  equivalent exists at all.

Modelling any of them properly is **a separate piece of work with its
own evidence**, and this fix does not pretend to it. What it buys is
that a consumer of identity can tell *"not modelled"* from *"does
nothing"*, which is the whole reason (af) blocks the consumer.

## 3. Readers, enumerated from source

`grep -rn "\.opcode\|->opcode" src/ --include=*.c`, whole tree —
unchanged since (ad) and re-run for this document:

- `src/ir/uir.c` name table and lifter.
- `src/ir/semantic.c:357` (`UIR_CALL`) and `:478` (`UIR_INT`) — the
  **only** two opcodes any analysis tests.
- `src/codegen/` and `src/optimize/` — **no opcode dispatch at all**.

**The `UIR_UNMODELLED` enumerator must not take value 0**, and the
totality guard `uir_opcode_name_is_total_over_the_enum` must be
extended to cover it — it passed at 40 opcodes before (ad) and 42
after, and must pass at 43.

## 4. Predictions, both halves

**Half one — no corpus figure and no product figure moves.**

- The operand differential is **untouched in every column on all 16
  inputs**: it compares **decoder** output and never lifts.
- `summary.call_graph` and the port attestation are **identical**: they
  test `UIR_CALL` and `UIR_INT`, and neither is produced here.
- **`hardware_functions` stays at 320 and instruction-derived stays at
  0** — (af) changes what the IR *carries*, and nothing reads it yet.
  That is (ag), and it is why this fix is a prerequisite rather than an
  improvement.
- The **`-t uir` text** changes for **1,089 instructions across 10
  inputs**, from `nop` to `unmodelled`. That is the entire observable
  movement.

**Half two — exactly one expected failure flips.** `(af)`'s own red,
written before the fix, which decodes an `SBB` and asserts the lifted
opcode is not `UIR_NOP`. Every other name in every suite stays as it
is; `test_uir` currently carries **0** registered expected failures, so
it goes 0 → 1 → 0 across red, gate and close.

## 5. Denominators

Population **16 of 16**, asserted before summing. The per-identity
counts above are printed with their zeros. The `-t uir` movement is
predicted **per input** and checked per input, not as a total.

## 6. Rule 28: the shipped-binary assertion

**The fixture contains no `SBB`, `SETcc` or any of the seventeen**, so
the fixture cannot assert this fix — measured, not assumed. **The
assertion is therefore owed and blocked, exactly as (ad)'s was**, and
the remedy is the same one already queued: when the fixture next opens,
append an `SBB` after the trailing `RSM`, where it shifts nothing.

*(ad)'s identical debt is still open; the two should be discharged in
one fixture edit, which is why neither has been discharged alone.*

## 7. Boundaries

> **(af) owns the seventeen identities the lifter drops.** One new
> enumerator, one `switch` arm per identity, no semantics invented.
>
> **(ad) is closed and (af) must not move it.** `X86_INS_INVALID`
> already lifts to `UIR_INVALID`.
>
> **(ag) is untouched.** Nothing reads the field; this fix makes the
> field honest, not read.
>
> **Modelling any of the seventeen properly is out of scope**, and each
> would need its own evidence.

---

**State before the fix:** `pass=102 xfail=14 fail=0 xpass=0
(tests=116)`, `test_uir` 24/24 with an empty expected-failure list, 26
suites, 0 warnings under `-Werror`. No line of (af) is written.
