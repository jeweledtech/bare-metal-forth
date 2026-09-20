# x86 front end: the open register, 2026-09-20

**What this file is.** One place where every open finding in the x86
arc is read, replacing the `Open after (n)` / `Open after (a)` /
`Open after (o)` lines scattered through three closing sections. Those
lines are historical records of what was open at a moment and must not
be edited to stay current; this file is current and carries no history.

**Authority.** For anything with a red, `xfail_names[]` in
`tools/translator/tests/test_x86_decoder.c` is the list and this file
is a reading of it. The suite prints `pass=93 xfail=20 fail=0 xpass=0
(tests=113)` today, and the 20 below are those 20 names. For a finding
with no red, this file is the only record, which is why each one
carries the **condition that mints it** rather than an intention.

## Open, with a red (20)

| letter | red | what is wrong |
|---|---|---|
| (d') | `x64_RED_rex_b_push_r12` | REX.B not applied to an opcode-embedded register |
| (f) | `x64_RED_byte_reg_sil_under_rex` | reg 4-7 at size 1 under REX is SPL/BPL/SIL/DIL |
| (g) | `x64_RED_truncated_imm32_refused` | immediate read past the code buffer |
| (g) | `x64_RED_truncated_disp32_refused` | displacement read past the code buffer |
| (p) | `x64_RED_p_movsxd_decoded` | `63` recognised, not just length-consumed |
| (p) | `x64_RED_p_imul_imm_decoded` | `69`/`6B` recognised |
| (r1) | `x64_RED_r1_push_iz_opsize16` | `66 68` Iz read at a fixed 4 bytes |
| (r2) | `x64_RED_r2_test_eax_iz_opsize16` | `66 A9` likewise |
| (r3) | `x64_RED_r3_test_ev_iz_opsize16` | `66 F7 /0` likewise |
| (s) | `x64_RED_s_pshufw_imm8_length` | two-byte arm loses a trailing imm8 |
| (s) | `x64_RED_s_cmpps_imm8_length` | same |
| (s) | `x64_RED_s_pinsrw_imm8_length` | same |
| (s) | `x64_RED_s_pextrw_imm8_length` | same |
| (s) | `x64_RED_s_pextrw_xmm_imm8_length` | the corpus encoding `66 0F C5` |
| (s) | `x64_RED_s_mov_cr_mod_ignored` | honours a mod field hardware ignores |
| (s) | `x64_RED_s_rsm_no_modrm_length` | consumes a ModRM that does not exist |
| (u) | `x64_RED_u_0f_map_matches_oracle` | the hand-typed no-ModRM list vs the oracle |
| (v) | `x86_RED_v_addr_size_prefix_disp16` | legacy `67` makes mod=10 a disp16 |
| (y) | `x64_RED_y_lea_register_form_invalid` | `8D C0` LEA register form is #UD |
| (aa) | `x64_RED_aa_unhandled_two_byte_is_not_nop` | unhandled two-byte opcodes render as NOP |

## Open, deferred, each with the condition that mints it

**(q) VEX / EVEX / REX2 unmodelled.** Measured zero on two
instruments: 0 occurrences by bytes over 576,115 objdump instructions
and 512,000 Ghidra starts, 16 of 16 inputs.
**Minting condition:** the first corpus input containing a VEX, EVEX or
REX2 encoding. Until then a red would have no number to move
(twenty-second rule), and the zero is recorded rather than the finding
closed, because the gap is real and the corpus is what is narrow.

**(t) the two-byte map has no INVALID.** Both instruments give the same
22 two-byte opcodes as invalid; the arm has no way to say so.
**Minting condition:** the generator run that produces the two-byte
table's refusal list. Banked separately from (s) so it does not leave
with it.

**(ab) the two-byte arm is blind to mandatory prefixes.** 1,091 of
48,241 two-byte instructions carry `66`, `F2` or `F3`; the arm consults
none of them. That is an upper bound on the affected class, not a
defect count.
**Minting condition:** the two-byte map becomes table-driven *and* an
instrument can separate "the arm ignored the prefix" from "this
opcode's length is wrong". Today (ab)'s only measurable instance is
`0F 78`, which is already inside (s)'s scope, so a red would duplicate
an (s) red rather than distinguish the class — the mask the alias table
taught us to avoid. Same treatment as (q).

## Not a defect letter, but owed and easy to lose

- **`cmovcc_0F44` asserts `X86_INS_NOP`.** A green test defends the
  behaviour (aa) says is wrong. It must be inverted in the act that
  fixes the default arm, or that fix will be reported as a regression.
- **512,213 is withdrawn.** It was summed from Ghidra per-instruction
  files that lived in `$(BUILDDIR)` and a clean destroyed. No
  difference may be taken against it. The reproducible pair is
  576,115 and 512,000, printed together by
  `tools/translator/scripts/denominators.py`.
- **`0F 21`, `0F 22`, `0F 23` have zero corpus witnesses** (`0F 20` has
  218). That one arm covers all four is read from source only.

## Closed, for the boundary

(b), (c), (d), (d-k), (e), (h), (i), (k), (m), (n), (o), (w), (x), (z),
(a). Each closed through an XPASS gate whose log names the exact set of
names that moved.
