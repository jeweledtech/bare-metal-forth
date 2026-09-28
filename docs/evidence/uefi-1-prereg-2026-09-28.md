# UEFI-1: a registered red for booting the stick under UEFI (pre-registration, 2026-09-28)

Written before the test exists. The outcome goes **below**, and nothing
above the Outcome line is edited after the first run.

**Owner ruling (2026-09-28):** the UEFI path is (a), GRUB EFI +
multiboot2, first. (b), our own BOOTX64.EFI stub, comes later and
replaces GRUB only.

ASUS-OLD-1 is CLOSED: no CSM, even with Secure Boot off (photographed),
and the operator restored the as-found settings.

Stages, each its own commit, red → XPASS:
- **UEFI-1:** this red.
- **UEFI-2:** own GDT and an abstract block base.
- **UEFI-3:** the multiboot2 entry; this red goes to XPASS.
- **UEFI-4:** the framebuffer console.
- **UEFI-5:** iron on the Older ASUS.

The survey this rests on is `UEFI-BOOT-0`, reported 2026-09-28. The
kernel makes no BIOS calls (0 `int` in `forth.asm`). Its BIOS/CSM
dependencies are the boot sector, memdisk, the fixed memory layout, the
inherited GDT, VGA text and the ATA ports.

## Instrument check, done before writing this (2026-09-28)

**Installed already; nothing was installed:**
- OVMF 2024.02 (`/usr/share/OVMF/OVMF_CODE_4M.fd` + `OVMF_VARS_4M.fd`);
- QEMU 8.2.2;
- GRUB 2.12 `x86_64-efi` and `i386-pc`;
- mtools, dosfstools, gdisk and syslinux.

**OVMF runs headless with serial on stdio.** In a 25 s run with no disk,
serial showed `BdsDxe: starting Boot0001 "EFI Internal Shell"`, `UEFI
Interactive Shell v2.2` and `EDK II`. This OVMF has **no CSM**, and the
non-secboot CODE image does not enforce Secure Boot, which matches the
ASUS with Secure Boot off.

## The red: `uefi1_RED_stick_boots_to_ok_under_ovmf`

**File:** `tests/test_uefi_boot.py`. **Target:** `make test-uefi-boot`,
wired into `make test`.

**What it boots.** A disk image built the way `tools/make-uefi-usb.sh`
builds the stick, **without root and without any block device**:
- a GPT with the script's two partitions (`ef02` BIOS boot from sector
  2048, +1 MiB; `ef00` ESP to the end);
- the ESP formatted FAT32 with the label `FORTHBOOT`;
- the script's own files: `memdisk`, `forth.img` = `build/combined.img`,
  and `boot/grub/grub.cfg`;
- `EFI/BOOT/BOOTX64.EFI` from the **same `grub-mkstandalone` command**.

**Against drift (rule 28).** The grub.cfg is read **from the script's
heredoc at test time**, not copied. The test also asserts that the
script's `grub-mkstandalone` block is the text it replays. If either
changes, the test FAILs outright and does not XFAIL.

**Not exercised (named):**
- the i386-pc half, because `grub-install` needs a block device. OVMF
  never reads it, and the HP exercises it on iron;
- the image size (64 MiB, not the stick's).

**The fixture:**
- `qemu-system-x86_64 -M q35`;
- OVMF CODE read-only plus a scratch copy of VARS, as pflash;
- the image on `qemu-xhci` + `usb-storage`, which is removable USB media
  like the stick;
- serial on stdio to a log, `-display none`, 60 s.

**Checks:**
- **Instrument control (fatal, unscored).** Serial must show the title
  of the grub.cfg's first UEFI-branch `menuentry`, which is parsed from
  the heredoc. That proves OVMF found BOOTX64.EFI on the image and ran
  GRUB. Without it the result is `INSTRUMENT FAIL`, exit 3, and no
  score: a red that did not reach GRUB would say nothing about ForthOS.
- **The red.** Serial shows the kernel banner `Bare-Metal Forth v0.1 -
  Ship Builders System` (`forth.asm:5755`) followed by `ok`. The banner
  is the criterion because GRUB can never print it.

**Outcomes:**
- **Today, predicted: XFAIL.** The UEFI branch of grub.cfg boots
  nothing: it prints instructions and waits at `read`
  (`make-uefi-usb.sh:98-120`). The test prints `XFAIL (expected)` and
  exits 0, so `make test` stays green.
- **XPASS** (banner + `ok` seen) prints `XPASS … remove the red` and
  exits 1, which fails `make test`. That is the gate UEFI-3 must trip.

### Where the red is registered: the owner rules

- **No Python suite has an XFAIL convention yet.** Only the translator's
  C suites do.
- **The translator register cannot hold this red.**
  `x64-open-register-2026-09-20.md`'s union check reads only those C
  suites' `xfail_names[]`, so a row for a Python red fails the census as
  "register lists X, which no suite registers".

**Proposed:**
- The red's name lives in `UEFI_REDS` in the test (the same shape as
  `xfail_names[]`) and in this document.
- A boot-path register, if the owner wants one, is its own file.
- Extending `suite_census.py` to read Python reds is **not** done here.

## Also in UEFI-1: `make-uefi-usb.sh:102`

**Wrong today:** "ForthOS is a 16-bit real-mode bare-metal kernel". The
kernel is 32-bit protected mode (`forth.asm:39`). Only its 512-byte
boot sector is 16-bit, and it is loaded through BIOS INT 13h via
memdisk.

**Fixed in the UEFI branch's text only.** The menu titles do not change,
so the instrument control is unaffected. The `pc` branch that boots the
HP is byte-identical.

## Must not move (for UEFI-1, and restated at every later stage)

| # | what | baseline, measured 2026-09-28 on `combined.img` `51cad6cf…` | check |
|---|---|---|---|
| M1 | the BIOS/memdisk path reaches `ok` in QEMU | `tests/test_memdisk_blk_writer.py` (pxelinux → memdisk → combined.img under SeaBIOS): **20/20**, rc 0 (`uefi-1-m1-memdisk-baseline-2026-09-28.log`) | the same run after each stage |
| M2 | full `make test` | all green at 84e07c2 (pushed); 12 expected XFAILs, all translator reds | `make test`: unchanged except the new `test-uefi-boot` XFAIL line |
| M3 | the HP boots | HDA-3, 2026-09-27, image 51cad6cf | UEFI-1 changes neither `boot.asm`, `forth.asm` nor any `.fth`, so **the stick image is unchanged**. Only the script's UEFI-branch text changes, and the HP boots the `pc` branch. No iron trip is owed for UEFI-1; one is owed from UEFI-2, which changes the kernel |

**M1's gap, named.** The existing gate boots memdisk from pxelinux with
`harddisk`. The stick uses GRUB i386-pc with `linux16 /memdisk raw`.
From memdisk onward the chain is the same (boot sector → kernel), but
GRUB i386-pc and the `raw` flag are exercised only on the HP.

---

## Outcome

(written after the run; nothing above this line changes)

### Outcome — 2026-09-28

**Commits:** prereg 7dec02e, red 56e7098, `make-uefi-usb.sh` text fix
d5a7487.

**The red is XFAIL, as predicted** (`uefi-1-red-2026-09-28.log`; serial
in `uefi-1-red-serial-2026-09-28.log`). Inputs: image `combined.img`
`51cad6cf…`, script `2e93ee34…`.
- **The control was seen.** OVMF found `EFI/BOOT/BOOTX64.EFI` on the
  replica and GRUB drew its UEFI menu on serial.
- The default entry then printed its CSM instructions and waited at
  `read`.
- **No kernel banner or `ok` appeared in 60 s.**
- After the text fix (script `ce252cc6…`) the red is still XFAIL with the
  control seen. The fix changes only the UEFI branch's echo lines.

**Two instrument faults, fixed before the counted run.** The first run
ended `INSTRUMENT FAIL` (exit 3, no score), although GRUB's echo text
did reach serial. The kept serial log showed why:
1. The menu title's em dash arrives as UTF-8 (`E2 80 94`), and the
   serial was decoded as Latin-1.
2. **GRUB truncates menu titles to the menu width** (`…as non-U`), so
   the full title never appears.

**The fix:** decode as UTF-8 and match the title's first 40 characters.
The control stays fatal. Neither fault touched the criterion: the kernel
banner + `ok`.

**Must not move:**
- **M1 HELD.** `test_memdisk_blk_writer.py` passed **20/20**, rc 0, after
  the stage (`uefi-1-m1-after-2026-09-28.log`), the same as the baseline.
- **M2 HELD.** `make test` rc 0, "All tests passed!"
  (`uefi-1-make-test-2026-09-28.log`):
  - 13 `XFAIL (expected)` = the 12 translator reds + the new
    `uefi1_RED_stick_boots_to_ok_under_ovmf`;
  - 0 other failures;
  - wiring gate 40/40 (`test-uefi-boot` wired);
  - check-sync OK.
- **M3 HELD by construction.** No `boot.asm`, `forth.asm` or `.fth`
  changed, so `combined.img` is still `51cad6cf…`. The HP boots the
  script's `pc` branch, which is untouched. No iron trip is owed for
  UEFI-1.

**Still with the owner:** where a Python red is registered (see above).
Until the owner rules, `UEFI_REDS` in the test and this document are the
registration.

**Next stage (not started):** UEFI-2, own GDT (selector 0x08) and an
abstract block base, landed on the BIOS path first.
