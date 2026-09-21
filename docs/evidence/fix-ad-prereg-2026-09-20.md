# Pre-registration: fix (ad), the lifter turns a refusal into a no-op (2026-09-20)

**Order.** (ad) lands **first and alone**, ahead of (aa)+(ac) and (s).
Its prediction is *nothing moves*, which makes it a live test of the
claim that this decoder almost never emits `INVALID` today — far better
found before two larger fixes than inside their movement.

Everything below is recomputed against the **post-split differential**,
`docs/evidence/operand-diff-decided-split-2026-09-20.log`, by name, and
against fixture **v13** (`b19fcb69…`). All decoder-side counts are read
from the 16 `*.ours.txt` dumps that run produced, row count asserted at
16 before summing.

## 1. Scope, settled: (ad) is the `INVALID` row. The other seventeen get a letter

The red asserts only that `X86_INS_INVALID` does not lift to
`UIR_NOP`. Seventeen other identities fall through the same
`default:` arm at `src/ir/uir.c:442`. **Measured, so the choice is not
a guess:**

| identity | corpus rows | identity | corpus rows |
|---|---|---|---|
| SBB | **481** | ADC | 9 |
| SETcc | **469** | ROL | 9 |
| CBW | 52 | CLD, LOOP, POPAD, PUSHAD | 0 |
| CDQ | 32 | REP_MOVSB/MOVSD/STOSB/STOSD | 0 |
| LEAVE | 23 | STD | 0 |
| ROR | 14 | **INVALID** | **1** |

**All eighteen: 1,090 rows. `INVALID` alone: 1.**

**So (ad) repairs one row and says so.** Repairing all eighteen would
be a 1,090-row change whose "nothing moves" is not predictable without
measuring each identity's downstream effect, and it mixes two different
defects: *a refusal becoming a claim* (`INVALID` → "does nothing") and
*a known instruction being dropped* (`SBB` → "does nothing"). The first
is a lie about knowledge; the second is a gap in coverage.

### (af) minted: the lifter drops seventeen modelled identities

**1,089 corpus rows**, the table above minus `INVALID`. On the open
register with its count. Not in (ad)'s scope, and (ad)'s fix must not
move it — which is assertable, because (af)'s rows are counted here.

## 2. The one corpus `INVALID` is a symptom of an open defect, not a stable count

It is at **`8139too.ko` `.text+2721`**, and the row before it is
`.text+271b TEST AX, 0xc07f` at length **6**. That is (r2): `66 A9`
whose `Iz` must be 2 bytes under `0x66`, read as 4. The walk overshoots
to `2721`, lands mid-instruction, and refuses.

**So (ad)'s corpus exposure is 1 today and predicted 0 after (r2)
lands.** The count is a consequence of another open defect and is not
durable. **The red is (ad)'s only durable instrument**, which is stated
now rather than discovered when the number goes to zero and someone
reads that as the defect being gone.

## 3. Readers, enumerated from source — and the reason "nothing moves" is predictable

`grep -rn "\.opcode\|->opcode" src/ --include=*.c`, whole tree:

- **`include/uir.h:27` — `UIR_NOP = 0`.** The no-op is the **zero
  value** of the enum, so any zero-initialised `uir_instruction_t`
  already reads as a no-op. **The fix must not give its new value 0**,
  and this is the latent form of the same defect, recorded here.
- **`src/ir/uir.c:689`** — the name table used by `-t uir`. The only
  place the opcode is *rendered*.
- **`src/ir/semantic.c:357`** — `if (ins->opcode != UIR_CALL) continue;`
  (call-graph edges).
- **`src/ir/semantic.c:478`** — `ins->opcode == UIR_INT` (interrupt
  handling).
- **`src/codegen/` and `src/optimize/` dispatch on the UIR opcode
  nowhere at all** — `grep` returns nothing in either directory.

**"Nothing moves" is predictable not because the change is small but
because no pass reads the field except for two values.** `UIR_CALL` and
`UIR_INT` are the only opcodes any analysis tests for, and the
`default:` arm produces neither, so no path from this change reaches
`summary.call_graph`, the port attestation, or the code generators.

**That is itself a finding about the product**, and it belongs beside
the tier-ladder addendum: the intermediate representation is, with
respect to opcode, very nearly write-only.

## 4. The prediction, both halves, because they differ

**Half one — zero corpus figures move.** Named baseline:
`operand-diff-decided-split-2026-09-20.log`.

- **The operand differential is untouched in every column on all 16
  inputs** — `ghidra=512,000`, `operand_ok=464,911`, `ok_defaulted=0`,
  `score=90.8%`, `decided=90.8%`, and every per-class count. It
  compares **decoder** output and never lifts.
- **`summary.call_graph` is identical on every input**, by the reader
  enumeration above: the only opcode it tests is `UIR_CALL`.
- **Port attestation is identical**: it tests `UIR_INT` and pre-extracted
  port lists.
- **The `-t uir` text changes for exactly one instruction in one
  input**, `8139too.ko .text+2721`, from `nop` to whatever the fix
  names it. That is the *entire* observable movement.

**Half two — exactly one expected failure flips.**

- **XPASS (1):** `ad_invalid_does_not_lift_to_nop`, in `test_uir.c`.
  (ad) closes its own red, so "nothing moves" does **not** mean "no
  test changes".
- **Stay red (30):** every name in `test_x86_decoder.c`'s
  `xfail_names[]`. (ad) touches no decoder line.
- `test-semantic` and `test-port-attestation` carry 0 registered
  expected failures and must stay at 0.

## 5. Denominators

- Population: **16 of 16** inputs, asserted before summing.
- Identity counts: read from the 16 `*.ours.txt` dumps, mnemonic by
  mnemonic, with `SETcc` matched across all sixteen spellings and
  `.LOCK` suffixes stripped, so a spelling gap cannot silently print 0.
- Five of the eighteen identities have corpus count **0**, and that is
  printed rather than omitted — zero-measured, not zero-found.

## 6. Proportionality

**Fifteen of sixteen inputs contain no `INVALID` at all** and must show
no change of any kind, in any output. Only `8139too.ko` may move, and
only in `-t uir` text, and only at one address.

## 7. Rule 28: the shipped-binary assertion is OWED and BLOCKED, with its remedy

**No committed artefact contains an encoding this decoder refuses.**
Measured: `INVALID` count is 0 in the fixture, in both ReactOS
controls, and in `nmap_service.exe`; the only one is in a **fetched**
kernel module, which is not a committed input.

So (ad) cannot gain a shipped-artefact assertion today, and that is
stated rather than papered over with a skip that reads like a pass.
**The remedy is exact and costs no offsets:** when the fixture next
opens for (s), append a single `0x06` byte **after** the trailing
`RSM`. It is past every existing row, so it shifts nothing, and it
gives the shipped binary a refusal to render. The 35-line assertion
becomes 36 at the same moment and is restated in the same act.

## 8. The boundaries

> **(ad) owns `X86_INS_INVALID` → not `UIR_NOP`. One row.**
>
> **(af) owns the other seventeen identities**, 1,089 corpus rows, and
> (ad) must not move it.
>
> **(aa)/(ac) own the decoder's answer.** (ad) is downstream of them and
> orthogonal: (ad) lands first precisely so that when (aa)+(ac) land,
> the identities they newly produce meet a lifter that no longer
> flattens a refusal.
>
> **The `UIR_NOP = 0` latency is named, not fixed here.** Changing the
> enum's zero value is a separate, wider change.

---

**State before the fix:** `test_x86_decoder` `pass=85 xfail=30 fail=0
xpass=0 (tests=115)`; `test_uir` `22/23 passed (xfail=1 of 1
registered, xpass=0)`; 25 suites; `SMOKE PASS`. No line of (ad) is
written.
