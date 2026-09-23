# The lifter carries MOV_CR / MOV_DR's operand: pre-registration (2026-09-22)

**Written before the change.** Scope, owner ruling: the lifter carrying the
operand of an unmodelled `MOV_CR`/`MOV_DR` under the existing contract (an
unmodelled instruction's `dest` is set only where the decoder's operand is
its **complete register write set**). Outcomes go BELOW the line.

## The write set per direction, read from the SDM and the decoder after `(av)`

| encoding | operand 0 (after `(av)`) | registers written | general registers written |
|---|---|---|---|
| `0F 20` / `0F 21` (read: MOV r, CRn/DRn) | the GPR | the GPR | **the GPR** |
| `0F 22` / `0F 23` (write: MOV CRn/DRn, r) | the CR/DR (40–71) | the CR/DR | **none** |

So operand 0 **is** the complete write set in **both** directions, and the
contract applies to both unchanged: carry operand 0 as `dest`.

## The owner's case: a CR/DR index where the walk reads a GPR number

It is settled by a type argument from source, not by a count:

- `uir_writes()` sends a register `dest` through **`reg_bits()`**, which
  bounds-checks before setting a bit: `16–19` → the alias bits;
  **`r < 0 || r > 15` → 0**. A CR/DR `dest` (40–71) therefore yields
  **"seen, writes no general register"**. For a CR/DR *write* that is the
  truth.
- The park walk's `holds[64]` is indexed directly **only** at a STORE's
  source, a MOV's operands, an XCHG's operands and the release check's
  RCX (`semantic.c:468, 579–580, 593–595, 528`). Each is guarded `< 64`,
  and `MOV_CR`/`MOV_DR` lift as none of them. Every other write goes
  through `reg_bits()` (`semantic.c:642`, `g < 16`). **So a CR/DR index can
  neither alias a tracked register nor index past `holds` at 64–71.**
- This gets a red either way (owner): the write direction must be *seen*
  and must leave a base in RAX tracked.

## Bound, measured on the current binary

The walks that stop today at a CR/DR move number **0 / 4 / 4 / 4** (HP /
Dell / ASUS older / ASUS newer), **12**. All are **`mov %cr8,%rbx`**, a read,
at the same four sites (`mlx4_bus.sys` `140013F29`, `140014046`,
`14001442B`, `140014548`) on each machine. **The three `mlx4_bus.sys` are
byte-different** (`211bdc6b`, `2c6b2684`, `ac8b0424`: three builds of one
driver), so the 12 are one driver's four sites on three builds, not twelve
independent sites. No stop in the corpus is at a CR/DR write.

## Predictions

| # | prediction |
|---|---|
| M1 | the reds pass together: a CR read writes only its GPR; a CR write and a DR write write no GPR, and a base in RAX survives them; the guard (a CR read *into* RAX kills the base) stays green |
| M2 | park census: **only the 12 sites can change**. Each moves off couldn't-tell, to park / couldn't-tell (a later stop) / `none` / after-release. **No prediction of which**; reported as observed, per machine |
| M3 | HP: byte-identical (0 sites) |
| M4 | `-t uir`: line counts identical; the only changed lines are `unmodelled` lines at MOV_CR/MOV_DR rows gaining an operand |
| M5 | differential byte-identical (the decoder is unchanged) |
| M6 | suites green; tests +1; 14 reds |

---

## Outcome

*(below this line, from the artefact only)*

**Inputs hashed:** `uir.c` `fa6f2d16204a7b9b`, `bin/translator` `7fcb5a58bdfc4dab`.
The census scripts are v2, unchanged against `SHA256SUMS`.

| # | predicted | observed |
|---|---|---|
| M1 | the reds pass together; the guard stays green | **held**: one XPASS, `sem_RED_aw_movcr_write_set` (CR read into RBX, CR write, DR write); `pw_GUARD_cr_read_into_base_kills_it` PASS |
| M2 | only the 12 sites change; outcomes as observed | **only the 12**, 0 outside them; **all 12 → `none`** (4 per machine) |
| M3 | HP byte-identical | **held** |
| M4 | `-t uir`: only unmodelled lines gain an operand | **held**: line counts identical; 221 changed lines, 0 any other way |
| M5 | differential unchanged | the decoder is unchanged (the `x86_decoder.c` hash equals `(av)`'s) |
| M6 | suites green; tests +1; 14 reds | suites green, 14 reds, **but tests rose by 2, not 1** (397 → 399): the red came with a guard, and the prediction counted only the red |

**Why the 12 become `none`, read from the bytes** at `mlx4_bus`
`140013F29` (Dell): the base goes to R15, then `test %rax,%rax` /
`jne 0x140013f7e`. The linear walk falls through the **failure** path (base
NULL), and the `mov %cr8,%rbx` it used to stop at is an IRQL read for a log
message about `0x270` bytes down that path. On the **success** path the base
is used at once as an address (`lea 0xc(%r15),%rbx`), with no store of R15
seen in the span read. **So `none` is plausibly the right answer for this
site, but it was reached by the wrong route**, through the branch-following
limit. It is not a missing park.

**The owner's aliasing case, now tested as well as argued:** a CR write
(`mov %rax,%cr8`) and a DR write (`mov %rax,%dr7`) leave a base in RAX
tracked, and a CR read into RAX kills it. The type argument (`reg_bits()`
maps 40–71 to no bits; `holds[]` is indexed only through operands
`MOV_CR` does not produce) predicted exactly that.
