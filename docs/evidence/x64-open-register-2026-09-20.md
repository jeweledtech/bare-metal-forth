# x86 front end: the open register, 2026-09-20

**What this file is.** One place where every open finding in the x86
arc is read, replacing the `Open after (n)` / `Open after (a)` /
`Open after (o)` lines scattered through three closing sections. Those
lines are historical records of what was open at a moment and must not
be edited to stay current; this file is current and carries no history.

**Order of work (owner ruling, 2026-09-20): (aa) lands before (s).**
(s) repairs six forms sitting on an arm that mis-renders 219 opcodes.
Landing (s) first turns six reds green over a floor still wrong beneath
them and patches the two-byte map twice instead of building it once.
(s)'s pre-registration survives — the census, the address sequence, the
boundary sentence — but its differential figures are taken again after
(aa).

**Authority.** For anything with a red, `xfail_names[]` in
`tools/translator/tests/test_x86_decoder.c` is the list and this file
is a reading of it. `open_register_is_exactly_the_xfail_list` in that suite parses the
table below and fails the build if the two disagree, so this file
cannot drift (owner item 7). For a finding
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
| (ab) | `x64_RED_ab_two_byte_arm_ignores_mandatory_prefix` | the arm never reads `66`/`F2`/`F3` |

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

*(ab) was deferred here and is now minted; see the table above. The
deferral said its only measurable instance was `0F 78`, which was true
of the **length** half only. The identity half is 1,091 exposures, and
the red is an inequality between `0F AE C0` (invalid in both
instruments) and `F3 0F AE C0` (RDFSBASE, 4 bytes in both), so it needs
no instruction modelled and (aa) cannot close it.*

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
