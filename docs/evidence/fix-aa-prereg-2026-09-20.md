# Pre-registration: fix (aa), the two-byte default arm's silent NOP (2026-09-20)

**Order.** The owner ruled (aa) ahead of (s) on 2026-09-20: (s) repairs
six forms sitting on an arm that mis-renders 219 opcodes, and landing
it first would patch the two-byte map twice instead of building it
once. (s)'s pre-registration survives entire and its differential
figures are re-taken after this fix.

Everything below is recomputed against
**`operand-diff-fix-o-2026-09-20.log`** by name, and against fixture
**v13** (`b19fcb6911e66fa66bdda105ee5e047f93fe4cafae85fbddb3fe7480dbaee9b4`).

## 0. What (aa) is, after two corrections to my own numbers

`x86_decoder.c:1316` ends the two-byte `default:` arm with
`out->instruction = X86_INS_NOP;`. An opcode the decoder does not model
is reported as an instruction that **does nothing** — a confident wrong
answer where `UNKNOWN` would be an honest one.

**Correction 1, already banked:** "30 of 256 reach the arm" was wrong;
**59** do. The 29 missed are the arm's own `no_modrm` list, which skips
the ModRM fetch and then assigns NOP like every other row.

**Correction 2, from this pre-registration:** "5 corpus instructions
reach the default arm" was counted over that wrong 30-set. Over the
correct 59-set the figure is **22**.

## 1. Population, pinned before any table

16 of 16 inputs, the list the post-(o) differential ran. Census by
bytes, `scripts/denominators.py`:

| | count |
|---|---|
| instructions examined | **576,115** |
| two-byte (`0F xx`) instructions | **48,244** |
| inputs | 16 of 16, none missing |

**The two-byte population moved from 48,241 to 48,244 and the reason is
named:** fixture v13 added three `0F 2x` rows. Three, exactly, and no
other input changed.

## 2. Rule 29: the prediction over the corpus AND over the opcode space

**(aa) moves 22 of 48,244 two-byte occurrences, and 59 of the 219
NOP-rendering opcodes leave the class.**

Both numbers, because they answer different questions. Twenty-two says
how often this bit these sixteen binaries. Fifty-nine of 219 says how
wide the hole is for the seventeenth, and 219 of 256 is the shape of
the map a translator is pointed at arbitrary code with.

Per input, by bytes:

| input | (aa) occurrences |
|---|---|
| storport.sys | 13 |
| fixture (v13) | 3 |
| ACPI.sys | 2 |
| pci.sys | 2 |
| ne2k-pci.ko | 1 |
| via-rng.ko | 1 |
| **the other ten inputs** | **0** |

## 3. Proportionality, with the asymmetry predicted in advance

**Ten of the sixteen inputs contain zero (aa)-touched encodings and
must not move at all**: disk, HDAudBus, i8042prt, HP serial, usbxhci,
8139too, iTCO_wdt, both ReactOS controls and nmap. An input that moves
while containing none of the thing being fixed is doing something else.

The six that may move are capped at their byte counts above, and
storport carries more than half of the corpus total on its own.

## 4. The predicted differential movement is exact, not a bound

A NOP-rendered instruction prints `nop` and the comparer classifies it
`mnemonic` (`nop vs <real>`). After the fix it prints `???` and is
classified `undecoded` — `compare_operands.py:208,211`. Both are
non-`ok` classes.

**So: `operand_ok` and the score are UNCHANGED on every input.
`mnemonic` falls by at most 22 and `undecoded` rises by the same
number, input for input.** Any other class moving is a finding.

**Lengths do not change.** The arm's ModRM consumption is untouched;
only the identity assignment changes. So `nostart`, `beyond_extent` and
`invalid_at_start` are unchanged on all 16 inputs. If a start moves,
the fix did something it was not asked to.

## 5. Readers, enumerated from source before a line changes — and one
of them is a new defect

`grep -rn "X86_INS_NOP" src/` over the whole tree, minus the two-byte
arm itself:

- **`x86_decoder.c:319, 1026, 1030–1038`** — one-byte NOP sites and the
  string-op arms. Untouched by (aa); named so they are checked.
- **`x86_decoder.c:1421`** — the printer's name table, `[X86_INS_NOP] =
  "nop"` and `[X86_INS_UNKNOWN] = "???"`. This is what makes the
  movement in §4 visible at all.
- **`src/ir/uir.c:437`** — `case X86_INS_NOP: uir->opcode = UIR_NOP;`

**And `src/ir/uir.c:442`, which is the finding: `default: uir->opcode =
UIR_NOP;`.** Everything the lifter does not model becomes a no-op in
the IR, so `UNKNOWN` and `NOP` are **already indistinguishable one
layer down**. **18 of the 56 x86 identities fall through it, and
`X86_INS_INVALID` is one of them** — an explicit refusal lifts to a
no-op.

### (ad) minted: the lifter collapses refusal into no-op

Minted now, with its count, **because (aa) alone does not reach the
analyzer**. The decoder will stop lying; the IR will carry the same
`UIR_NOP` it carries today. Any claim that (aa) improves downstream
analysis is false until (ad) lands, and this document makes no such
claim. Pass state: an unmodelled or invalid instruction is not a
`UIR_NOP`. **(ad) is not in (aa)'s scope** — (aa) is the decoder's
answer — and its red exists now: `ad_invalid_does_not_lift_to_nop` in
`test_uir.c`, which had no expected-failure plumbing until this red
needed it. It decodes `06` PUSH ES, asserts as *setup* that the decoder
says `INVALID`, and fails on the lifted opcode being `UIR_NOP`.

## 6. Denominators

Every figure above prints one. The corpus counts come from
`scripts/denominators.py` and the opcode-space counts from a probe that
sweeps **all 66 ModRM forms** — 64 register cells plus `mod=00` and
`mod=10` — because for `0F 00/01/18/AE` the digit is opcode and for
`0F 20`–`23` the mod bits are ignored. Result: 0 opcodes render NOP for
some forms and not others, so 219 is ModRM-independent.

## 7. Expected XPASS, red by red, over all 30

**Flip (1), and only one:** `x64_RED_aa_unhandled_two_byte_is_not_nop`.
`0F A7` is in the 59.

**Stay red (29).** The nine converted tests are named individually, as
required:

| red | why it must NOT move |
|---|---|
| `cmovcc_0F44` | `0F 44` is explicitly cased — (ac), not (aa) |
| `bt_rm_r_0FA3` | `0F A3` explicitly cased — (ac) |
| `bt_rm_imm8_0FBA` | `0F BA` explicitly cased — (ac) |
| `cmpxchg_0FB1` | `0F B1` explicitly cased — (ac) |
| `xadd_0FC1` | `0F C1` explicitly cased — (ac) |
| `desync_recovery_BT_then_IN` | `0F A3` explicitly cased — (ac) |
| `three_byte_0F38` | `0F 38` explicitly cased — (ac) |
| `three_byte_0F3A` | `0F 3A` explicitly cased — (ac) |
| `unknown_0f_modrm_recovery` | `0F 0D` explicitly cased — (t) |

**Any of those nine flipping means the fix widened past the default arm
without saying so.** That is the sharpest assertion in this document,
because the eight are 160 opcodes and 22,012 corpus occurrences of a
class (aa) is not allowed to touch.

The remaining 20 stay red for the ordinary reason: (d'), (f), (g)×2,
(p)×2, (r1)–(r3), (s)×7, (u), (v), (y), (ab). **(ab) in particular
cannot move**: `0F AE` is explicitly cased, and its red is an
*inequality* that `UNKNOWN == UNKNOWN` does not satisfy.

**Other suites:** `test-semantic` and `test-port-attestation` carry 0
registered expected failures and must stay at 0. **`test-uir` now
carries 1** — (ad), minted with this document — and it must stay red
through (aa), because (aa) never reaches the lifter.

## 8. Rule 28: the shipped-binary assertion (aa) can fail

**The fixture contains no NOP byte at all** — `grep -c 0x90` over
`x64_reds.s` returns 0 — so a correct decoder prints **zero** `nop`
lines for it. The shipped binary prints **three** today:

```
0040104d:  nop        0F 70 PSHUFW   -- (ac), stays
00401055:  nop        0F C4 PINSRW   -- (aa), must go
00401074:  nop        0F AA RSM      -- (aa), must go
```

**Assertion: after (aa), `bin/translator -t disasm` on the fixture
prints no `nop` at `00401055` or `00401074`, and still prints one at
`0040104d`.** It fails now, passes when (aa) lands, is derived from the
fixture's own bytes plus the pinned oracle rather than from a run, and
**the surviving row is the assertion's control** — a fix that silenced
all three went further than it was authorised to.

## 9. The boundaries, stated before a line is written

> **(aa) owns the two-byte `default:` arm and nothing else: 59 opcodes,
> the identity only, never the length.**
>
> **(ac) owns the 160 opcodes assigned NOP at the 17 explicit `case`
> sites.** 219 = 59 + 160, computed as a set difference, not by eye.
>
> **(ab) owns the arm's blindness to `66`/`F2`/`F3`.** Orthogonal to
> both: a prefix-aware arm is needed whichever half is fixed.
>
> **(s) owns two-byte lengths**, and (aa) changes none.
>
> **(t) owns the map's inability to refuse**, and (aa) produces
> `UNKNOWN`, not `INVALID`. If (aa)'s fix emits `INVALID` anywhere it
> has taken (t)'s work without (t)'s oracle list.
>
> **(ad) owns the lifter's `default: UIR_NOP`.** (aa) stops at the
> decoder boundary.

## 10. (q), unchanged and still blocking nothing here

Measured zero across the whole pinned population, three ways, 0 of
576,115. (aa) touches no VEX, EVEX or REX2 path, so (q)'s status is
unchanged by it and no figure in this document rests on it.

---

**State before the fix:** `pass=85 xfail=30 fail=0 xpass=0 (tests=115)`,
25 suites, `SMOKE PASS`. No line of (aa) is written.
