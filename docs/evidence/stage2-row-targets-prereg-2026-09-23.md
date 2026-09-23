# Stage 2's 14 rows as pre-registered targets for the items that unblock them (2026-09-23)

**Written before any SSE or IMUL work exists**, so it cannot be shaped to
their outcome (owner ruling). Every row below is a hand-verified access
(`stage2-bound-2026-09-23.md`) that the product, held to its own rule
(*where an instruction's writes cannot be seen, stop and say so*), cannot yet
vouch for. When an item lands, the rows it unblocks must flip from
undetermined to **exactly** the row given, **and nothing else may move**.

## A correction of my own, first

I told the owner the product could reach **13** of the 14, having checked
only each reload→access span. **A reload is vouched only if the park's base
register (RDI) is provably unwritten from the park to the reload**, and that
span contains three instructions the decoder cannot name:

| address | instruction | open item |
|---|---|---|
| `1c00226bd` | `movups (%rbx),%xmm0` | SSE moves (not yet opened) |
| `1c00226c0` | `movups %xmm0,0x28(%rdi)` | SSE moves |
| `1c0022cc1` | `imul $0x17700,%ecx,%ecx` (`69 /r`) | **(p)**, `x64_RED_p_imul_imm_decoded`, already registered |

**Only row 1's reload comes before the first of them, and row 1's access
lies beyond the two `movups`. Held to its rule, the product vouches for 0 of
the 14, not 13.** None of the three writes RDI or the reloaded register
(the hand read), but the product cannot see that, and treating an unknown as
writing nothing is the loosening rule 33 forbids.

## The targets

Independent sample count throughout: **1**: one pointer, one park, one
function, one driver.

| # | reload | into | access | reads | blocked by | unblocked by |
|---|---|---|---|---|---|---|
| 1 | `1c00226a3` | RCX | `1c00226d2` `mov 0x8(%rcx),%eax` | 4 bytes at 0x8 | `movups` ×2 inside reload→access | SSE |
| 2 | `1c00226de` | RAX | `1c00226e2` `movzwl (%rax),%r8d` | 2 at 0x0 | `movups` ×2 inside park→reload | SSE |
| 3 | `1c00226e6` | RAX | `1c00226ea` `movzwl (%rax),%ebx` | 2 at 0x0 | same | SSE |
| 4 | `1c00226ed` | RAX | `1c00226f1` `movzwl (%rax),%edx` | 2 at 0x0 | same | SSE |
| 5 | `1c00227cc` | RAX | `1c00227d0` `movzwl (%rax),%ecx` | 2 at 0x0 | same | SSE |
| 6 | `1c002284a` | RAX | `1c0022865` `movzbl 0x3(%rax),%edx` | 1 at 0x3 | same | SSE |
| 7 | `1c0022869` | RAX | `1c002286d` `movzbl 0x2(%rax),%eax` | 1 at 0x2 | same | SSE |
| 8 | `1c002297d` | RAX | `1c0022981` `movzwl (%rax),%ecx` | 2 at 0x0 | same | SSE |
| 9 | `1c0022984` | RAX | `1c0022994` `movzwl (%rax),%ecx` | 2 at 0x0 | same | SSE |
| 10 | `1c0022997` | RAX | `1c00229a4` `movzwl (%rax),%ecx` | 2 at 0x0 | same | SSE |
| 11 | `1c0022bfe` | RAX | `1c0022c02` `movzwl 0x14(%rax),%eax` | 2 at 0x14 | same | SSE |
| 12 | `1c0022c79` | RAX | `1c0022c7d` `movzwl (%rax),%ecx` | 2 at 0x0 | same | SSE |
| 13 | `1c0022cb9` | RCX | `1c0022cbd` `movzwl 0x4(%rcx),%ecx` | 2 at 0x4 | same | SSE |
| 14 | `1c0022d0b` | RCX | `1c0022d0f` `movzwl 0x6(%rcx),%ecx` | 2 at 0x6 | `movups` ×2, and `imul` at `1c0022cc1` | SSE **and (p)** |

**So the SSE item alone flips rows 1–13, and row 14 needs (p) as well.**
Those are the pre-registered outcomes of those items, written before either
exists. (p) is the smaller of the two and is already an open red.
