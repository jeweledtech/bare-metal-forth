# TASK — forms and editors on the UEFI screen (2026-10-12)

Owner, 2026-10-12: make the screen target one cell, 0xB8000 on BIOS and the
text shadow at 0x80000 on UEFI, plus a flush to the framebuffer, so
FILE-BROWSER, notepad and the forms draw on both. Gate it with the same
screenshot method under OVMF; keep the BIOS screens unchanged. Follows
UEFI-4 (docs/TASK_UEFI_3_4.md), where only print_char reached the
framebuffer.

**Superseded in part, 2026-10-12, by HAL slice 1 (docs/TASK_HAL_DISPLAY.md),
before this task was committed:** the consumers no longer take `SCREEN` as a
constant; they call the display contract (FB-BASE, FB-FLUSH), bound from
BOOT-MODE. The kernel half below (the shadow, FB_DRAWN, the flush, the
palette, SCREEN and SCREEN-FLUSH) stands as the contract's UEFI binding, and
the gate below stands with U5/L5 reading FB-BASE.

## Design note

- **Who writes the screen directly** (grep of forth/dict, 2026-10-12):
  three constants, all `B8000`: UI-CORE's VGA-BASE (the forms, notepad,
  FILE-BROWSER's tree), the block editor's VGA-BASE, and FILE-EDITOR-CORE's
  FE-VGA (notepad's and FILE-BROWSER's editor). Every app draws through one
  of them.
- **One cell.** The kernel's `vga_base` (UEFI-4) is that cell: 0xB8000 on a
  BIOS boot, FB_SHADOW (0x80000) on a UEFI boot with a framebuffer. A new
  word `SCREEN ( -- addr )` returns it, and the three constants become
  `SCREEN CONSTANT ...`. They are evaluated when the vocabulary loads,
  after mb2_entry has set the cell, so the draw paths pay nothing extra.
- **The flush.** `SCREEN-FLUSH` draws every cell that differs from what the
  framebuffer last showed (a second 4,000-byte copy, FB_DRAWN = 0x81000;
  the text-shadow window grows to 0x80000-0x82000). It runs:
  - in the kernel's key wait (read_key's idle branch, before `hlt`):
    FORM-RUN and every KEY loop;
  - in FILE-EDITOR-CORE's RAW-SCAN wait, which spins on the keyboard ring
    and never reaches read_key (notepad's and FILE-BROWSER's editors).
  On a BIOS boot it returns at once.
- **Colours.** fb_cell draws the attribute byte through the 16-colour VGA
  palette (bit 7 ignored: no blink), so the forms' inverse video (focus,
  buttons) shows on UEFI as it does on BIOS. The default 0x07 stays light
  grey on black.
- **Gate** (test-uefi-boot, both legs): `SCREEN` = 0x80000 (OVMF) /
  0xB8000 (SeaBIOS); HELLO-RUN's form and notepad's editor (entered with
  the New button, so the RAW-SCAN path runs) each leave their text in the
  screen memory (QEMU monitor pmemsave); on OVMF, every one of the 2,000
  cells on the screen dump equals that memory drawn in the image's font and
  palette. BIOS screens: the same text at 0xB8000; nothing else about the
  BIOS path changes.
- **Not in this task:** FILE-BROWSER's tree needs an NTFS volume to draw
  anything; it draws through the same UI-CORE and FILE-EDITOR-CORE words,
  which the gate covers.

## Results

Evidence: ~/forthos-evidence/2026-10-12-uefi-screen/ (predictions written
before each run, logs).

**Red** (UEFI-4 kernel, the extended gate), every result as predicted: U5
and L5 FAIL (`SCREEN ?`), U6 and U7 FAIL (the form and the editor drew at
0xB8000; the shadow held only print_char's lines), S1 and S2 PASS but
vacuously (the framebuffer matched a shadow without the form, which is why
U6/U7 sit beside them), U8 and L6-L8 PASS (BIOS already drew at 0xB8000).
Two instrument faults on the way: HMP read `pmemsave ... 4000 /tmp/...` as
a division (the path is quoted now), and a missing dump stops the run as
INSTRUMENT FAIL instead of a traceback. The gate outgrew its 40 s limit
(50.5 s); the red ran at T_UEFI_BOOT=200, a measurement run.

**Green:**

| check | OVMF (UEFI) | SeaBIOS (legacy) |
|---|---|---|
| SCREEN | U5 = 80000 | L5 = B8000 |
| HELLO-RUN's form in the screen memory | U6 PASS | L6 PASS |
| ... with inverse-video cells | U6b 30 cells | L6b PASS |
| the form on the framebuffer, all 2,000 cells, font + palette | S1: 0 differ | (VGA) |
| notepad's editor (New button, RAW-SCAN wait): title + `Ln1 Col1` | U7 PASS | L7 PASS |
| the editor on the framebuffer, all 2,000 cells | S2: 0 differ | (VGA) |
| back at the prompt, DEPTH 0 | U8 PASS | L8 PASS |

Every earlier check of the gate still passes (F1 included). Four runs,
50.5 s each; T_UEFI_BOOT 40 -> 100 (the gate now runs two apps per leg:
a re-measure of a changed test, not a slowdown). Kernel pad 12,309 B free
(this task: 267 B).
