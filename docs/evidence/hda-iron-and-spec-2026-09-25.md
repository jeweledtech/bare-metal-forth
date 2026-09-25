# HDA on the HP: iron reading, spec check, and two reads (2026-09-25)

## 1. Iron reading (the owner at the bench, typed by hand)

**Source: the owner, 2026-09-25.** This session did not observe it; it
is recorded as given.

- HDA controller at **00:1F.3**, `8086:9D71`, class **04/03**. **`HDA-FIND`
  scans function 0 only, so it cannot find this device.**
- Config space: `00=9D718086 04=00100006 08=04030021 10=B1228004 14=00000000`
  → base **`B1228000`**. The BAR is 64-bit (type bits `10`b) with the high
  dword 0, so it sits **below 4 GB**.
- `+02 C@ = 00` (VMIN) and `+03 C@ = 01` (VMAJ). **Both values were
  predicted from the spec before the read.**
- `+00 W@ = 9701` (GCAP) and `+08 @ = 00000001` (GCTL, CRST = 1).

## 2. Spec check: Intel HDA Rev 1.0a, read from the PDF on disk

The owner supplied the file at `refs/high-definition-audio-specification.pdf`
(sha256 `5974a446d914273a…`, 225 pages, "Revision 1.0a"). **The PDF is
not committed**, because `refs/` is untracked. Read with `pdftotext -layout`.

| offset | spec (Table 2, p. 25; §3.3.2–3.3.9, pp. 28–32) | length | the driver's access (stage 2) | match |
|---|---|---|---|---|
| 0x00 | GCAP, Global Capabilities | 2 B | 2 B read ×8 | yes |
| 0x02 | VMIN, Minor Version, reset `00h` | 1 B | 1 B read | yes |
| 0x03 | VMAJ, Major Version, reset `01h` | 1 B | 1 B read | yes |
| 0x04 | OUTPAY, "16-bit Word quantities per 48-kHz frame" | 2 B | 2 B read, ×`0x17700` | yes |
| 0x06 | INPAY, same unit | 2 B | 2 B read, ×`0x17700` | yes |
| 0x08 | GCTL; CRST = bit 0, `RWS` (§3.3.7) | 4 B | 4 B read, bit 0 tested | yes |
| 0x0C | WAKEEN, Wake Enable | 2 B | — | — |
| 0x0E | WAKESTS in Table 2, STATESTS in §3.3.9 | 2 B | — | — |
| 0x12–0x17 | **Reserved** | — | 2 B read at **0x14** | **open** |

- **The spec closes the check for 0x00–0x08.** Each access has the offset
  and the length that the spec gives the register.
- **The ×`0x17700` is explained by the unit:** 96,000 = 2 bytes per word ×
  48,000 frames per second.
- **The driver joins the two version bytes as `(VMAJ<<8)|VMIN`**
  (`1c0022871`), and the iron reading gave `01`/`00`.
- §3.3.7 also says: *"Software must read a 1 from this bit before accessing
  any controller registers."*

**0x14 stays open.** The spec says Reserved. Linux
`include/sound/hda_register.h` (commit `52345d35`) names it `AZX_REG_LLCH`.
The driver reads it only on the branch where its stored ID `>>24` equals
`0x8086`, and tests it for nonzero. **That gives it a name, not a meaning,
and Linux is a second implementation, not the spec.**

## 3. Two reads, no change made

**What `HDA-RESET` (private `audio.fth`) writes at 0x0C, and why.**
- It stores `0` and then `1` with `HDA!`, which is a 32-bit `!`, at
  BAR+0x0C, with a 100 ms delay after each store. It then polls BAR+0x08
  with a 32-bit `@` for nonzero, up to 16 times at 10 ms.
- By Table 2, a 4-byte store at 0x0C covers **WAKEEN (0C–0D) and WAKESTS
  (0E–0F)**, not GCTL. So the "reset" leaves CRST alone and writes the
  SDIN wake-enable flags.
- **Why:** nothing on record says. The word has no comment. It is identical
  in the first commit (public `75e8739`, 2026-04-12) and was carried
  through the split. The only later change was `4b1e5ee`, the HEX/DECIMAL
  literals.
- *Reasoned, not observed:* the poll of 0x08 suggests GCTL was intended.
- On the HP, where CRST already reads 1, the poll would exit on its first
  read, so the word would report success without ever resetting.

**Whether the kernel `W@` is one 16-bit load or two byte loads.** It is
**one**:
- The source (`src/kernel/forth.asm:1047`) is `pop eax; movzx eax, word
  [eax]; push eax`.
- The built kernels agree: the sequence `58 0F B7 00 50` occurs exactly
  once in `build/kernel.bin`, at 0x790.
- `hardware.fth`'s `W@-MMIO` is the one that splits a 16-bit read into
  two `C@`s.

## Named, not taken

- `mmio_desc` is never set in `translator.c`, so every emitted vocabulary
  prints `MMIO: none`.
- (Correction to the earlier report today:) the translator build used for
  every result is `adcbf3c1a22f1233`. A forced rebuild reproduces it. The
  private repo's `bin/translator` (`16dd1f16…`, built 09-20) is a stale
  file that nothing runs.
