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
> **`UIR_NOP = 0` rides WITH (ad)** — see the amendment below. It is
> (ad)'s own sentence at the type level.

---

**State before the fix:** `test_x86_decoder` `pass=85 xfail=30 fail=0
xpass=0 (tests=115)`; `test_uir` `22/23 passed (xfail=1 of 1
registered, xpass=0)`; 25 suites; `SMOKE PASS`. No line of (ad) is
written.


---

# Amendment: the zero value rides with (ad), and the reader enumeration gets its own letter (2026-09-20)

## 1. `UIR_NOP = 0` is (ad)'s own sentence at the type level, so it is in scope

`include/uir.h:27` makes the no-op the **zero value** of the opcode
enum. Any zero-initialised or partly-populated `uir_instruction_t`
therefore reads as *"does nothing"* — the same claim (ad) exists to
stop a refusal making. Recording it and fixing it elsewhere would have
split one sentence across two letters.

**In scope for (ad): a sentinel at 0.** `UIR_UNSET = 0`, with `UIR_NOP`
moved to a real value of its own.

**Blast radius, enumerated from source before the line is written:**

- **`src/ir/uir.c:688` `opcode_names[]`** uses **designated
  initialisers** (`[UIR_NOP] = "nop"`), so every existing name follows
  its enumerator automatically and no entry shifts. **The sentinel
  needs its own entry**, or the array is one shorter than
  `UIR_OPCODE_COUNT`.
- **`src/ir/uir.c:710-711`** bounds the lookup with
  `op >= 0 && op < UIR_OPCODE_COUNT` and then indexes the array. That
  bound is **against the enum, not the array**, so an enumerator with
  no name entry is an out-of-bounds read of an uninitialised pointer.
  **Measured today: 40 of 40 enumerators have an entry**, so there is
  no hole now — but the invariant is **unasserted**, and adding a
  sentinel is exactly the change that could open it.
- **`src/ir/semantic.c:357, 478`** compare against `UIR_CALL` and
  `UIR_INT` by name. Renumbering is invisible to them.
- **No serialised form, no table indexed by a literal opcode number,
  no persisted artefact** carries these values — `grep` for
  `UIR_OPCODE_COUNT` and for the name table returns only the two sites
  above.

**A guard rides with it:** `uir_opcode_name()` returns non-NULL for
every value in `[0, UIR_OPCODE_COUNT)`. It passes today, which is the
point — it is written **before** the enum changes so that it is the
thing that catches a missing entry rather than a later crash.

## 2. Say "no product figure moves", not "nothing moves"

**Correction to §4 above, which invited a wrong inference.** "Zero
corpus figures move" is true and is not the same as "the analyzer is
unimproved". **(ad) improves no product figure, and neither will
(aa), (ac) or (s).** The reason is (ag) below, and every
pre-registration in this arc from here states it in those words rather
than letting a reader infer analyzer improvement from a decoder repair.

## 3. When a corpus witness is itself a symptom, say so — as a standing note

(ad)'s single corpus `INVALID` sits inside (r2)'s desync run and is
predicted to reach **0** when (r2) lands, which is why the red is its
only durable instrument. **The same note is owed by any future fix
whose corpus witness is a symptom of another open defect**, because
without it a vanished count reads as proof the fix worked. Recorded on
the open register, not only here.

## 4. (ag) minted: the IR is write-only with respect to instruction identity

**The largest finding of the round, and it is not a decoder defect.**

`grep -rn "\.opcode\|->opcode" src/ --include=*.c`, whole tree. The
lifter produces **40** distinct opcodes. **Two are ever tested by any
analysis**: `UIR_CALL` (`semantic.c:357`) and `UIR_INT`
(`semantic.c:478`). `src/codegen/` and `src/optimize/` dispatch on the
opcode **nowhere at all**.

**The rationale for landing (ad) first was partly wrong and is
corrected here.** The honesty (aa) and (ac) introduce is **not
destroyed** one layer up — **it is never read**. (ad) still lands
first, because it is cheap, correct, and its prediction is now proved
from source rather than hoped. **That reason is its own, and it does
not unblock the other two.**

**(aa), (ac), (ad) and (s) together make the IR _true_. Not one of them
makes it _used_.** That is the missing middle of the product, it is
what actually bounds tier 2, and it is worth knowing before three more
decoder fixes are spent against a tier-2 claim.


---

# Closing: (ad) built and green (2026-09-20)

**The third reader class, enumerated before the line was written.**

- **Zero-init-and-use** — a `uir_instruction_t` zeroed and used without
  assigning `opcode`: **none.** Every constructor assigns on every
  path, including both lifters' `default:` arms and the ARM64 one at
  `uir.c:1100`. Checked over every site in `src/` and `tests/` that
  holds instruction storage.
- **Persisted or numeric opcode** — a golden file, a serialised IR, a
  fixture holding a literal: **none.** No test compares `-t uir`
  output, no file under `tests/data/` carries UIR text, and no
  assignment of a literal number to `opcode` exists.

**So nothing could fire where it never did, and the artefact confirms
it: `unset` appears 0 times in all 16 inputs.** The enumeration was
from source; the zero is from the binary.

**Built:** `UIR_UNSET = 0` and `UIR_INVALID` added to the opcode enum,
both given name-table entries, and
`case X86_INS_INVALID: uir->opcode = UIR_INVALID;` placed **before**
the `default:` arm so the other seventeen identities are untouched.

**Gate:** XPASS fired on **exactly one name**,
`ad_invalid_does_not_lift_to_nop`, across all 25 suites
(`fix-ad-xpass-gate-2026-09-20.log`). Name removed by hand afterwards;
`test_uir` is now `24/24 passed (xfail=0 of 0 registered, xpass=0)` and
the whole suite is green (`fix-ad-green-2026-09-20.log`, 25 suites).

**Every prediction checked against the artefact:**

| predicted | observed |
|---|---|
| no corpus figure moves | the 16 decoder dumps are **byte-identical** to the pre-fix baseline — every differential column unchanged by construction, without needing the oracle re-run |
| exactly one XPASS | exactly one; the decoder suite held at `pass=85 xfail=30 fail=0 xpass=0` |
| one instruction in one input changes in `-t uir` | 8139too prints **1** `invalid`, at `.text+2721` — the address predicted from (r2)'s overshoot — and the other 15 print **0** |
| the sentinel is never produced | **0** `unset` lines across all 16 |
| letter (af) does not move | 8139too still prints **845** `nop` lines |
| no product figure moves | unchanged and **stated, not inferred**: nothing reads the field |

**The totality guard passed before the enum changed (40 opcodes) and
passes after (42).** It was written first for exactly that reason.

**One instrument defect found while closing.** The open register's
executable check matched any table row whose first cell merely
*contained* a parenthesis, so the closing table's prose rows made it
report `nop` and a module basename as missing reds. Tightened: the
first cell must be a defect letter **and nothing else**. The guard
caught its own looseness the first time a closing table was written
under it, which is the cheapest place for that to happen.
