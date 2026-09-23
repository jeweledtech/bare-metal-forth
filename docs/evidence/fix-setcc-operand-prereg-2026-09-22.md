# The lifter carries SETcc's operand: pre-registration (2026-09-22)

**Written before the change.** Owner's order: this is next, scoped to the
flag-set; the CR moves are a decoder gap and a separate item. Outcomes go
BELOW the line, from the artefact only.

## The change

`X86_INS_SETCC` still lifts to `UIR_UNMODELLED`, and no semantics are
invented, but its `dest` now carries the decoder's operand 0. The contract,
written into `uir.h`: **an unmodelled instruction's `dest` is set only
where the decoder's operand is its complete register write set.** Today
that is SETcc alone. The other sixteen unmodelled identities keep `dest`
NONE and stay unseen. `uir_writes()` answers accordingly: an unmodelled
instruction with a register `dest` writes exactly that register, one with a
memory `dest` writes no register, and one with none stays unseen.

**Readers of the changed field, enumerated from source (rule 24):**
`uir_writes()` and the UIR printer. No test asserts on SETcc's `dest`. The
existing red `(al)` (`setne %al`, then a store of RAX, must not park) is the
guard that a SETcc overwriting the base still kills it.

## The bound, measured on the current binary

Only walks that stop today at a SETcc can move: **2 / 4 / 3 / 3** (HP /
Dell / ASUS older / ASUS newer), 12 in all: 9 `setne` and 3 `sete`. The
owner's figure of 11 predates the ABI stop, which added the three `sete`
sites.

| machine | sites |
|---|---|
| HP | serial `1C000C701`, `1C000C7E7` |
| Dell | fdc `1C0004E2F`; pmem `140019997` (sete); serial `1C000E4CB`, `1C000E5B1` |
| ASUS (older) | pmem `1C001604E` (sete); serial `1C000C701`, `1C000C7E7` |
| ASUS (newer) | pmem `1C001827F` (sete); serial `1C000D4CB`, `1C000D5BC` |

## Predictions

| # | prediction |
|---|---|
| S1 | HP's two serial sites become parks at `0xE8` and `0xF0`, **route `address_order`**: the walk crosses `jmp 0x1c000c71a` at `1c000c713` before the park at `1c000c720` (read from the bytes); nothing else on HP moves |
| S2 | on every machine, **only the 12 listed sites can change**; every other outcome is byte-identical once the route key is set aside |
| S3 | *reasoned, not read:* serial's two sites become `address_order` parks at `0xE8` / `0xF0` on all three other machines, because ASUS (older) is HP's build and the two Windows 11 builds are the same driver |
| S4 | `fdc` and `pmem`: no prediction; they are reported as observed |
| S5 | `-t uir`: line counts identical per input; every changed line is an `unmodelled` line that gains an operand, and no other line changes |
| S6 | one XPASS; tests rise by one; 14 reds |

---

## Outcome

*(below this line, from the artefact only)*

**Inputs hashed:** `bin/translator` `d6df45353907fda4` (the pre-change run was
`baad7b886c867d3a`). The census scripts are v2, unchanged against
`SHA256SUMS`.

| # | predicted | observed |
|---|---|---|
| S1 | HP serial's two sites become `address_order` parks at `0xE8` / `0xF0`; nothing else on HP moves | **exactly that** |
| S2 | only the 12 listed sites change | **held**: 0 changes outside them; 9 of the 12 moved |
| S3 | *reasoned:* serial's two sites become `address_order` parks at `0xE8` / `0xF0` on all three other machines | **five of six.** ASUS (newer) `1C000D5BC` parks at **`0x0`**: that build stores the base through a pointer, `mov %rax,(%r15)`, where the others store `0xf0(%rdi)` (read from the bytes). "The same driver" was wrong for that build |
| S4 | `fdc`, `pmem`: reported as observed | `fdc` (Dell) → `none`. The three `pmem` walks get past their `sete` and **now stop at `sbb %eax,%eax`**: another unmodelled identity whose single operand is its whole write set, so the same contract would cover it. **Named, not taken**, because this repair is scoped to the flag-set |
| S5 | `-t uir`: only `unmodelled` lines gain an operand | **held**: line counts identical on all 12 inputs; 460 changed lines, 0 any other way |
| S6 | one XPASS, tests +1, 14 reds | **held**: 394 tests, 14 reds |

**The census, both ways** (Wilson intervals as before, recomputable from
the counts):

| machine | structure / resolved | path-verified structure / resolved | none | couldn't tell | after release |
|---|---|---|---|---|---|
| HP | 8/11 = 73% | 6/11 = 55% | 1 | 0 | 0 |
| Dell | 91/116 = 78% | 85/116 = 73% | 34 | 21 | 1 |
| ASUS (older) | 81/110 = 74% | 76/110 = 69% | 37 | 23 | 1 |
| ASUS (newer) | 96/122 = 79% | 89/122 = 73% | 41 | 20 | 1 |

**HP now has no couldn't-tell at all.** Its path-verified share *fell*
(6/9 to 6/11), because both serial parks came back as address order. The
repair recovered two real parks, and the walk cannot vouch for the route
to either.
