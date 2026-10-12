# TASK UEFI-3/4 — multiboot2 entry, then a framebuffer console (2026-10-12)

Owner, 2026-10-12: UEFI-3/4 next, no separate plan: design note, red,
code, gates, one report; stop before anything runs on a real machine.
Arc and earlier stages: docs/evidence/uefi-1-prereg-2026-09-28.md,
uefi-2-prereg-2026-09-28.md, uefi-mmap-0-2026-09-28.md.

## Design note: UEFI-3 (multiboot2 entry, serial only)

- **One file, loaded twice.** The UEFI branch of the stick's grub.cfg
  (tools/make-uefi-usb.sh) becomes `multiboot2 /forth.img` +
  `module2 /forth.img`. forth.img is combined.img: GRUB loads only the
  kernel part of it (the address tag), and the module is the whole image,
  which BLK_IMAGE_BASE (0x28098) points at exactly as a memdisk boot does
  (boot sector at +0, kernel at +512, block 0 at COMBINED_HEADER_SIZE). So
  BLOCK, LOAD-VOCAB and the installer's pristine-kernel read work unchanged.
- **Header** (multiboot2 spec §3.1): in the kernel, 8-aligned, inside the
  first 32 KiB of the file, after kernel_start's last instruction. Tags:
  address (header_addr; load_addr = KERNEL_ORG 0x7E00; load_end_addr =
  bss_end_addr = KERNEL_ORG + KERNEL_PADDED_SIZE, so GRUB copies the kernel
  only, not the blocks behind it), entry (mb2_entry), information request
  (memory map, type 6), end. The BIOS path is unchanged: the boot sector
  still jumps to 0x7E00 = kernel_start.
- **Entry** (spec §3.3: EAX = 0x36D76289, EBX = MBI, flat 32-bit, paging
  off, interrupts off). mb2_entry runs on a small stack inside the kernel
  image, the only memory GRUB cannot have put the MBI or the module in.
  It checks the magic, walks the tags and copies what it needs (the first
  module's start and end; the memory map, up to a fixed number of entries)
  into the kernel image, sets a flag, and jumps to kernel_start. Nothing
  in a window is written before that copy.
- **Windows** the kernel owns (docs/ARCHITECTURE.md memory map):
  0x500-0x80000 (data stack, kernel, return stack, variables, buffers,
  IDT, dictionary) and 0x100000-0x400000 (the physical allocation pool).
- **Report, serial only** (in mb2_entry, before anything reads
  BLK_IMAGE_BASE): the module's range, then for each window
  how much of it the memory map gives as available (type 1), and every
  non-available entry inside it, as `COLLISION`. A collision is reported,
  not acted on: QEMU's map is not the iron's (UEFI-MMAP-0's caveat).
- **The module must not sit in a window.** Measured: GRUB 2.12 puts it at
  0x100000, inside the pool (first run: the kernel refused, as the
  refusal path should). So the kernel moves it to 0x400000, the end of the
  highest window, after checking the map gives that whole range as
  available; otherwise it refuses. No module, or a bad magic: refuse.
- **As built,** the whole step runs in mb2_entry before kernel_start writes
  any memory (the map is read in place, not copied: 1,200 B of kernel
  instead of 2,224 B), and kernel_start is unchanged.
- **Not in UEFI-3:** VGA text writes stay (harmless on QEMU; UEFI-4 replaces
  them where there is no text mode); keyboard, PIC and IDT unchanged.

## Secure Boot (owner, 2026-10-12): off for the first real-machine runs

The first UEFI runs on the ASUS laptops are planned with Secure Boot off,
the owner's firmware decision when they come. A signed path is noted
here, not built:

- **The chain.** Firmware trusts Microsoft's UEFI CA, so a signed boot
  starts with shim (signed by that CA), which trusts keys enrolled as MOKs
  (Machine Owner Keys, enrolled once per machine at the console). shim
  then loads a second stage signed with our MOK.
- **What we would sign.** Either GRUB (grubx64.efi, built by us, signed with
  our key), or our own BOOTX64.EFI stub (UEFI-5's plan to replace GRUB).
- **Open questions, to check before building:**
  - whether GRUB under Secure Boot (its lockdown and shim_lock verifier)
    allows `multiboot2` at all: forth.img is not a PE image and can't carry
    an Authenticode signature;
  - if not, GRUB's detached-signature check (`check_signatures` with an
    embedded public key) for forth.img, or loading the kernel from our own
    signed stub;
  - key custody: where the private signing key lives and who signs a
    release.
- **Test bed when it's time:** QEMU with OVMF_CODE_4M.secboot.fd and
  OVMF_VARS_4M.ms.fd (Secure Boot on, Microsoft keys enrolled; both are
  installed on the dev machine).

## Owner direction (2026-10-12): boot whichever way the machine offers

Legacy where the machine has it, UEFI otherwise, from the same stick or
over the network.

- **One stick image, both paths gated.** test-uefi-boot boots the stick
  replica under OVMF (UEFI) and, the same image, under SeaBIOS (legacy):
  `ok` and a vocabulary loaded from blocks on both. The replica's BIOS
  half can't be made by `grub-install` without root (and grub-bios-setup
  needs a root device it can open), so it is laid out by hand the way
  grub-bios-setup embeds GRUB on a GPT disk: boot.img's code in the MBR,
  core.img in the BIOS-boot partition, core's blocklist patched. Its bytes
  differ from grub-install's; its path is the stick's (BIOS -> GRUB ->
  grub.cfg `pc` branch -> memdisk -> forth.img).
- **ForthOS reports how it booted.** `BOOT-MODE ( -- n )`: 0 BIOS from a
  disk (installed: VBR or chainload, no memdisk), 1 BIOS through memdisk,
  2 multiboot2 under BIOS, 3 multiboot2 under UEFI (mb2_entry records
  whether GRUB passed an EFI system-table tag, 11 or 12). AUTO-DETECT
  prints it. UEFI-4 uses it to choose VGA text or the framebuffer.
- **Network boot.** Checked: the PXE server does NOT branch on DHCP
  option 93 (tools/pxe/setup-dnsmasq.sh:78, one `dhcp-boot=pxelinux.0`),
  and the GRUB netboot tree is i386-pc only (build-grub-net.sh). The UEFI
  branch (dnsmasq tag on client-arch 7/9 -> a GRUB x86_64-efi netboot
  image with the same multiboot2 + module entry) is written in the repo
  scripts and gated by an OVMF network boot in QEMU (QEMU's own DHCP/TFTP
  serves the tree). **Applying it to the live server reaches real
  machines (the HP boots from it): that waits for the owner.**

## Design note: UEFI-4 (framebuffer console)

Owner rulings 2026-10-12: Terminus 8x16 (OFL), generated at build time
from the installed package and never committed, its license on the stick;
the font in a reserved block range read from the module.

- **Font:** tools/make_font_blocks.py picks printable ASCII (0x20-0x7E)
  by the font's Unicode table: 1,536 B, a 16-byte header (`FNT1`, first,
  count, height, width). write-catalog.py writes it into FONT_RESERVED,
  blocks 536-537 (after MIRROR's range). Package absent: a warning, zeroed
  blocks, and the UEFI console has no font (its gate fails, loudly). Under
  the OFL the subset is a Modified Version: never called "Terminus Font".
- **Framebuffer:** the header asks for one (tag 5, no size preference);
  mb2_entry keeps GRUB's framebuffer tag (8) if it is direct RGB at 32 bpp.
- **Console:** on a UEFI boot with a framebuffer and a font, the kernel's
  text buffer moves from 0xB8000 (no text mode there) to a RAM shadow, and
  every cell print_char, the scroll, PAGE and the screen clear write is
  drawn to the framebuffer as an 8x16 glyph. BIOS boots are unchanged.
- **Not covered:** the form engine and the editors write 0xB8000 directly
  from Forth (UI-CORE's VGA-BASE, FE-VGA); on UEFI they draw nothing yet.

## Results: UEFI-3

Evidence: ~/forthos-evidence/2026-10-12-uefi3/ (predictions-*.md written
before each run, logs, serial captures).

**Red** (kernel without a header, new gate, new grub.cfg branch): three
runs, two of them config faults the gate found before the kernel mattered.
1. `error: file '/forth.img' not found`: the standalone GRUB's root is its
   built-in memdisk (I predicted a header error; wrong). Fix: `search`.
2. `error: no such device: /forth.img`: GRUB sees the stick's partitions
   only after `insmod part_gpt` (debug boot: `(hd0)` before, `(hd0,gpt2)`
   after). Fix: `insmod part_gpt` + `insmod fat`.
3. `error: no multiboot header found`, H1 and H2 FAIL: the red as
   predicted.

**Green**, the gate (tests/test_uefi_boot.py, make test-uefi-boot, +74):

| check | result |
|---|---|
| H1 grub-file --is-x86-multiboot2 | PASS |
| H2 header at file offset 1040 (0x8010), tags consistent | PASS |
| B2 `MB2: module 00100000-0039C200`, both windows fully available, no COLLISION, `moved to 00400000-0069C200`, no REFUSED | PASS |
| B3 banner + ok under OVMF, no CSM | PASS |
| I1 BLK_IMAGE_BASE = 0x400000 | PASS |
| I2 HELLO-APP loads from the module (no IDE disk in this machine) | PASS |
| I3 DEPTH 0 | PASS |

Five runs, 10.5 s each; T_UEFI_BOOT 25. One check of mine was wrong in run
2 (I2 rejected the dependencies' "present, skipped" lines, not only
HELLO-APP's) and was corrected to test_pad_move's K2 form. The UEFI-1 red
is retired in the register (x64-open-register, Python reds 1 -> 0).

**Kernel pad:** 13,684 B left (was 14,884; UEFI-3 costs 1,200 B). The old
K4 (">= 14,800 B left", the pad move's acceptance number) failed; the only
red in the make -k run on this tree. Owner rulings 2026-10-12, applied:
- **K4 now measures the move itself:** the boot stream from the pre-move
  list (3f58be6^) against today's EMBED_VOCABS: 94,640 -> 80,268 B, shrank
  14,372 B (>= 14,000). PASS.
- **Free pad reported on every kernel build** (tools/pad_report.py, in the
  kernel rule): `kernel pad: 13684 B free of 114688 (content 101004; floor
  2048)`.
- **Hard floor 2 KB** (KERNEL_PAD_FLOOR in forth.asm, a TIMES count of 0 or
  -1, so it emits nothing when it holds). Checked both ways on scratch
  copies: floor 20,000 fails the build (`TIMES value -1 is negative`);
  floor 13,684 (= the free pad) builds, kernel still 114,688 B.

**Port inventory** (owner queue item): tools/port_inventory.py now sees
`python3 -u tests/X.py`. Red first: with test-uefi-boot's recipe on
`python3 -u`, the generator found no listens for it (drift against the
committed entry; a new recipe would have passed unchecked). After: 38
recipes, 78 entries, 0 problems.

## Results: UEFI-4, the boot mode, both paths, network boot

Evidence: ~/forthos-evidence/2026-10-12-uefi4/ (predictions written before
each run, logs, serial captures).

**Red** (UEFI-3 kernel, the extended gate): H3, B2 (three windows wanted),
B4, U1, U3, F1, L1, L3 FAIL; H1, H2, B3, I1, U2, U4, L0, L2, L4 PASS, every
one as predicted. L0 shows the dual path already worked: the hand-laid BIOS
half boots the same image through SeaBIOS, GRUB and memdisk to `ok`.

**Green, three things found on the way:**
1. The window report called mb2_window twice by hand, so the third window
   (the text shadow) went unreported: now a loop over MB2_NWINDOWS.
2. GRUB passed **no** framebuffer tag: the standalone GRUB had no video
   driver loaded. The kernel now says what GRUB passed (`GRUB passed none`,
   or the type and bpp it got), which is what the iron will need too.
3. With `insmod all_video`, GRUB passed type 1 at 24 bpp, 800x600: its bochs
   driver setting QEMU's VGA directly. With `insmod efi_gop` only (what a
   real machine offers): 1280x800, 32 bpp, at 0x80000000. The stick's UEFI
   entry loads efi_gop.

| check | OVMF | SeaBIOS |
|---|---|---|
| banner + ok | B3 PASS | L0 PASS |
| BOOT-MODE | U1 = 3 PASS | L1 = 1 PASS |
| HELLO-APP from blocks | U2 PASS (module) | L2 PASS (memdisk) |
| AUTO-DETECT-REPORT | U3 `Boot: UEFI (multiboot2)` | L3 `Boot: BIOS (memdisk)` |
| DEPTH 0 | U4 PASS | L4 PASS |

Plus H1-H4, B2 (three windows, all available), B4 (`framebuffer console
on`), I1, and **F1: after PAGE and `.( UEF) .( I4)`, the screen dump shows
UEFI4 in the image's font, pixel for pixel, at cell 0,1** (split so only
the output, not the echoed command, spells it). Seven runs green, 17.7 s
each; T_UEFI_BOOT 40.

One run (5) crashed in the SeaBIOS leg on a reset serial socket. Not
reproduced in five runs after the change; the cause was not observed. The
test now waits for its own QEMU to own both ports (qemu_pid.wait_started,
which names a QEMU that exits) and reaps the first QEMU before the second
starts, so a repeat names its cause instead of crashing.

**Kernel pad:** 12,576 B free (UEFI-4 and BOOT-MODE: 1,108 B). The font
costs none: blocks 536-537 of the image.

**Network boot.** Red: N1, N2 (no option-93 branch, no EFI boot file
named), N3 (no banner) FAIL as predicted; my predicted detail (an error
naming linux16 on serial) was wrong: nothing followed GRUB's countdown on
serial. Green: tools/pxe/gen-grub-cfg.py gives the netboot grub.cfg a
`grub_platform` branch: the BIOS entries unchanged and in their frozen
order inside the `pc` branch, one UEFI entry (efi_gop, multiboot2 + module2
/forth.img) in the other. test_grub_cfg.py's frozen-shape pins now read the
branches (owner direction 2026-10-12; 31/31). setup-dnsmasq.sh tags
client-arch 7 and 9 and answers them with grub/x86_64-efi/core.efi, every
other client pxelinux.0. test-uefi-netboot (new, +71): N1-N6 PASS, 12 s,
three runs; T_UEFI_NETBOOT 30. test-g6 (the BIOS network chain) 77/77 after
the change. **Neither the dnsmasq config nor the tree is applied to the
live server** (make pxe-setup, make pxe-push-grub): the owner's step.

**The font's license:** tools/make_font_blocks.py --license writes the
notice and the OFL text (from console-setup's copyright file) as
FONT-LICENSE.txt next to forth.img: make-uefi-usb.sh, make-usb-image.sh and
the netboot tree (build-grub-net.sh), and the HP stick builder
(forthos-vocabularies tools/make_hp_stick.py) at its next rebuild.

**Still not covered on UEFI:** the form engine and the editors write
0xB8000 from Forth, so they draw nothing on the framebuffer yet.
