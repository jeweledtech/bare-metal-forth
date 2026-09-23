# Stage 2's bound, re-derived from the bytes before any code (2026-09-23)

**Input:** `HDAudBus.sys` (sha256 `9966d998035daae0…`, the HP set, unchanged).
**Function:** `1c0022510`–`1c0022daf`, from the PE exception directory
(`.pdata`), a single entry that contains the park. **Park:** `1c002267d`
`mov %rax,0x58(%rdi)` (stage 1's report: `park_offset 0x58`, route `path`).

**Rules, fixed before the run:** a *reload* is a later
`mov 0x58(%rdi),%REG`. It counts only if the `rdi` family has no bare write
between the park and the reload, with operands split outside parentheses
(the spec records the text-match version of that check being wrong twice).
Its *access* is the first use of `%REG` as a memory base while `%REG` is
live, meaning before it is overwritten, or a call, `jmp` or `ret` intervenes.
Size comes from the instruction; offset is the displacement.

**Writes to the `rdi` family after the park:** one, `1c0022dac`, in the
epilogue after the last reload. None falls between the park and any reload.

| # | reload | into | access | reads |
|---|---|---|---|---|
| 1 | `1c00226a3` | RCX | `1c00226d2` `mov 0x8(%rcx),%eax` | **4 bytes at 0x8** |
| 2 | `1c00226de` | RAX | `1c00226e2` `movzwl (%rax),%r8d` | 2 bytes at 0x0 |
| 3 | `1c00226e6` | RAX | `1c00226ea` `movzwl (%rax),%ebx` | 2 at 0x0 |
| 4 | `1c00226ed` | RAX | `1c00226f1` `movzwl (%rax),%edx` | 2 at 0x0 |
| 5 | `1c00227cc` | RAX | `1c00227d0` `movzwl (%rax),%ecx` | 2 at 0x0 |
| 6 | `1c002284a` | RAX | `1c0022865` `movzbl 0x3(%rax),%edx` | 1 at 0x3 |
| 7 | `1c0022869` | RAX | `1c002286d` `movzbl 0x2(%rax),%eax` | 1 at 0x2 |
| 8 | `1c002297d` | RAX | `1c0022981` `movzwl (%rax),%ecx` | 2 at 0x0 |
| 9 | `1c0022984` | RAX | `1c0022994` `movzwl (%rax),%ecx` | 2 at 0x0 |
| 10 | `1c0022997` | RAX | `1c00229a4` `movzwl (%rax),%ecx` | 2 at 0x0 |
| 11 | `1c0022bfe` | RAX | `1c0022c02` `movzwl 0x14(%rax),%eax` | 2 at 0x14 |
| 12 | `1c0022c79` | RAX | `1c0022c7d` `movzwl (%rax),%ecx` | 2 at 0x0 |
| 13 | `1c0022cb9` | RCX | `1c0022cbd` `movzwl 0x4(%rcx),%ecx` | 2 at 0x4 |
| 14 | `1c0022d0b` | RCX | `1c0022d0f` `movzwl 0x6(%rcx),%ecx` | 2 at 0x6 |

## The count is 14, not the 13 the stage-2 exit names

**Row 1 was read from the bytes by hand:** `1c00226a3 mov 0x58(%rdi),%rcx`
comes straight after the second mapping call (`1c0022697`). The only
instructions before `1c00226d2 mov 0x8(%rcx),%eax` are tests, `je` and
stores through `%rdi`/`%rbx`; none writes RCX or RDI, and no call
intervenes. **It is a genuine 4-byte read at offset 0x8 of the region parked
at 0x58, in the same function through the same park.**

**Why the 13 missed it cannot be established:** the ad-hoc tracer that
produced it is not banked. Row 1 is also the only reload taken at the
second mapping site rather than further down; that is noted and not
offered as the cause.

**The exit as written says "13 accesses through 1 park".** The bytes say
14. **Changing an exit's number is the owner's ruling**, so no stage-2
code is written until it is made. The independent-sample count is
unchanged: **one pointer, one park, one function, one driver.**

## Ruling (owner, 2026-09-23), and what the product can reach of it

**The exit now reads 14 accesses through 1 park, stated as an exact set,
and never without "independent sample count 1".** This is a correction,
not a rebaseline, **because it raises what the work commits to** (13 → 14).
Rule 33 refused loosening a threshold so a check would pass; this goes the
other way, and the direction is the test.

**Checked before any code: can the product reach all 14 under its own
discipline?** The product's function `func_1C0022510` matches `.pdata`,
contains every reload and access, and a lifted memory operand carries the
access size (`movzwl` 2, `movzbl` 1, `mov` 4). **But between row 1's reload
(`1c00226a3`) and its access (`1c00226d2`) are two instructions the decoder
cannot name**: `1c00226bd movups (%rbx),%xmm0` and `1c00226c0 movups
%xmm0,0x28(%rdi)`, both lifted `unknown`. The other 13 rows have nothing
unseen between reload and access. **Under the walk's rule (where an
instruction's writes cannot be seen, stop and say so), the product would
state 13 accesses and report row 1's access as undetermined.** It is
correct by the hand read: `movups` writes XMM0 and memory, not RCX. But the
product cannot see that without naming the SSE moves. Treating an unknown
instruction as writing nothing, so that row 1 comes through, is the
loosening rule 33 forbids, and is **not** an option.
