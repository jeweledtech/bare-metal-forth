# UEFI-2: own GDT and one block-image base (pre-registration, 2026-09-28)

Written before any UEFI-2 code. The outcome goes **below**, and nothing
above the Outcome line is edited after the first build.

**Owner ruling (2026-09-28):**
- The kernel loads its own GDT, in kernel memory, keeping code selector
  0x08 and whatever data selector `boot.asm` uses today.
- The block image base becomes one kernel variable. Today's boot sector
  still sets it, so the MEMDISK_BASE path is unchanged in behaviour.
  UEFI-3 will set it from the multiboot2 module.
- **This lands on the BIOS path first.**

## What the source says today (read, 2026-09-28)

### The GDT

- **Where it is.** `boot.asm` builds the only GDT, inside the **boot
  sector** at 0x7C00: `gdt_start` l.282, null l.284, code l.287, data
  l.295, descriptor l.305. It loads it at l.187 (`lgdt`) and far-jumps
  with `CODE_SEG` at l.191.
- **Selectors.** `CODE_SEG = gdt_code - gdt_start` (l.309) = **0x08**.
  `DATA_SEG = gdt_data - gdt_start` (l.310) = **0x10**, loaded into
  DS/ES/FS/GS/SS at l.267-272. Both descriptors are flat 4 GB, ring 0
  (l.287-301).
- **The kernel never loads a GDT** (no `lgdt` in `forth.asm`) and
  **never reloads a segment register** (no `mov ds/es/fs/gs/ss`). It
  runs on the boot sector's GDT and selectors. Its IDT gates hard-code
  code selector 0x08 (`forth.asm:3863`), and `lidt` is at `:3895`.
- **Why it matters.** Under multiboot2 (UEFI-3) there is no boot
  sector: GRUB's GDT is not ours, and the spec does not promise the
  selectors. Even today, the GDT lives in memory the kernel does not
  own: the boot sector, just above the data stack that grows down from
  0x7C00 (`forth.asm:48`).

### The block-image base

- **One cell.** `MEMDISK_BASE equ 0x28098` (`forth.asm:141`), written only
  by the boot sector (`boot.asm:172-174`; 0 = not memdisk).
- **Six readers:**
  - boot vector selection, `forth.asm:340` (write) and `:349` (read);
  - `BLOCK`, `:2819`;
  - `LOAD`, `:3153`;
  - `-->`, `:3216`;
  - `ram_read_block`, `:5382`. The source is base +
    `COMBINED_HEADER_SIZE` + block × 1024 (`:5368-5382`), so the base is
    the start of a whole `combined.img` in RAM.

## What gets built

1. **The kernel's own GDT.** It lives in the kernel image (between
   `KERNEL_ORG` 0x7E00 and `+ KERNEL_PADDED_SIZE` 0x1C000, i.e. below
   0x23E00) and holds the same three descriptors, byte for byte as
   `boot.asm:284-301`: null, code at **0x08**, data at **0x10**.
   - **Loaded first thing in `kernel_start`:** `lgdt`, a far jump to
     reload CS with 0x08, then DS/ES/FS/GS/SS reloaded with 0x10.
   - **Then** the existing stack setup.
   - Nothing else changes: IDT gates stay 0x08.
2. **One block-image base.** `BLK_IMAGE_BASE equ 0x28098`, the **same
   cell** at the same address, so `boot.asm` is untouched. It is
   documented as "physical base of a whole `combined.img` in RAM; 0 =
   none". All six readers use it.
   - The name `MEMDISK_BASE` remains only as a comment at the boot
     handoff ("the boot sector's memdisk probe writes it").
   - UEFI-3 adds a second writer (the multiboot2 module tag). No reader
     changes then.

**Behaviour is unchanged by construction:** the same address, the same
0/non-0 decisions, the same arithmetic.

## The red: `uefi2_RED_kernel_runs_on_own_gdt`

**Written after this document is accepted.** File
`tests/test_uefi2_gdt.py`, registered in the register's "Python reds",
so gate C goes to 2.

**The fixture.** `bmforth.img` on floppy + `combined.img` on IDE, the
standard block fixture, with the QEMU HMP monitor on TCP. At the `ok`
prompt, the test reads **`info registers`**, an instrument outside the
kernel, and so needs no new kernel word.

**Instrument control (fatal, unscored):** the monitor answers, and
`info registers` has a `GDT=` line and a `CS =` line.

**Checks:**

| # | check | today | after |
|---|---|---|---|
| 1 | GDT base in the kernel image, `0x7E00 <= base < 0x23E00` | **red**: the base is inside the boot sector (predicted `0x7Cxx`; the exact value is printed) | pass |
| 2 | GDT limit ≥ 0x17 (three descriptors) | pass (control: boot.asm's is 0x17) | pass |
| 3 | CS = 0x0008 | pass (control) | pass |
| 4 | DS = ES = SS = 0x0010 | pass (control) | pass |
| 5 | the interpreter is alive after `878 884 THRU`, so blocks still load | pass (control) | pass |

Checks 2–5 are controls that must pass **both** before and after. A GDT
move that broke the selectors or the block path would show there.

**Red → XPASS:** check 1 flips, and the test prints XPASS and exits 1
until the red is removed from `UEFI_REDS` and the register.

**No red for the block-base rename, and why:**
- It is a pure rename of the same cell. There is no behaviour to go
  from red to green.
- Its protection is M1 (the memdisk RAM path through BLOCK, LOAD and
  `-->`) and M2 (the ATA path through the floppy+IDE suites,
  test-block-reload among them). Both paths are exercised.

## Must not move

| # | what | baseline | check |
|---|---|---|---|
| M1 | memdisk path | `test-memdisk` **20/20** (wired c0a8db8) | the same, after |
| M2 | `make test` | rc 0 with **13** expected XFAILs (12 translator + uefi1) at c0a8db8 | rc 0; XFAILs 13 + 0 (UEFI-2's red is XPASS-removed in the fix commit, so the final count is 13); wiring 41/41 |
| M4 | UEFI-1 red | XFAIL, control seen, replica reproducible | XFAIL, control seen. The replica sha changes because `combined.img` changes, and the new sha must repeat on two runs |
| M3 | **the HP boots (OWED from this stage)** | HDA-3, image `51cad6cf…` | the iron card below, on the new image |

**Named moves:**
- **`bmforth.img` and `combined.img` change** (the kernel changes). Their
  new sha256 values are recorded at the build and written into the card.
- **`KERNEL_PADDED_SIZE` does not change** (0x1C000). So
  `BLOCKS_LBA_BASE` and every catalog range stay put: PCI-BAR stays
  **878–884**. This is re-checked with the host resolver at the build.

## M3 — the HP iron card (DESK-CARD-UEFI-2, written with the build)

Read-only. It carries the HP's usual net-console listener, the hash gate
and the byte-replay of erased lines.

- **Section 0:** image sha: ______ (filled from the build; the listener's
  hash gate must PASS).
- **Section 1: boot to `ok`.** The banner, auto-detect, AHCI and NTFS as
  HDA-3 logged them.
- **Section 2:**
  ```forth
  ONLY FORTH DEFINITIONS
  DECIMAL
  878 884 THRU                 \ PCI-BAR loads from blocks
  ALSO PCI-ENUM
  : DEF? WORD FIND NIP ;
  DEF? NO-SUCH-WORD .          \ expect 0
  DEF? PCI-BAR .               \ expect nonzero
  ALSO PCI-BAR
  HEX
  0 1F 3 0 PCI-BAR64@ .H8      \ expect B1228000 (HDA-1/-3)
  DEPTH .                      \ expect 0
  DECIMAL
  ```
- **What passes:** `ok`, the blocks load, and B1228000 is read through
  the kernel's own GDT on iron.
- **Dry run:** in QEMU with intel-hda before printing (rule 16).

## Amendments (owner, 2026-09-28, before any code)

**(a) What the controls read.** They read **CS = 0x0008** and
**DS = ES = SS = 0x0010** (FS and GS are also 0x0010). They parse QEMU
HMP `info registers` lines of exactly this form, captured 2026-09-28 on
today's image (`bmforth.img` `dfd7c5f3…` on floppy + `combined.img` on
IDE, at `ok`):
```
CS =0008 00000000 ffffffff 00cf9a00 DPL=0 CS32 [-R-]
DS =0010 00000000 ffffffff 00cf9300 DPL=0 DS   [-WA]
ES =0010 00000000 ffffffff 00cf9300 DPL=0 DS   [-WA]
SS =0010 00000000 ffffffff 00cf9300 DPL=0 DS   [-WA]
GDT=     00007d90 00000017
IDT=     00029400 000007ff
```
- **The GDT base.** Check 1's red is **measured**, not only predicted:
  **0x7D90**, inside the boot sector (0x7C00–0x7DFF). Limit 0x17.
- **The parse.** Selector = the 4 hex digits after `CS =`, `DS =`,
  `ES =` and `SS =`. GDT base and limit = the two hex words after
  `GDT=`.
- **Noted, not in scope:** the kernel's IDT is at **0x29400**. That is
  outside the kernel image, in the variables area above 0x28000, and
  UEFI-MMAP-0 checks that range.

**(c) The HP card's PCI-BAR line** runs inside a HEX block, with DEPTH
shown before and after:
```forth
HEX
DEPTH .                        \ expect 0
0 1F 3 0 PCI-BAR64@ .H8        \ expect B1228000
DEPTH .                        \ expect 0
DECIMAL
```
**Expect B1228000.** It is the config value B1228004 with its flag bits
masked (bit 2 = 64-bit type; PCI-BAR64@ masks with FFFFFFF0):
- the raw B1228004 is config 0x10 as read on the HP in
  `hda-iron-and-spec-2026-09-25.md` l.10;
- the masked B1228000 is what HDA-3 logged through PCI-BAR64@
  (`hda3-iron-2026-09-27.log` l.84, `B1228000ok`).

**(b) The memdisk gate's false pass.** `test_memdisk_blk_writer.py`
printed `SKIP` and exited 0 when pxelinux or memdisk was missing
(l.131-133). Under `make test` that reads as a pass. It becomes
`INSTRUMENT FAIL`, exit 3, as in `test_uefi_boot.py`, in its own commit
with a negative control.

**(d) UEFI-MMAP-0**, a read-only probe, runs **before any UEFI-2 code**.
It boots OVMF in QEMU to the EFI shell, runs `memmap`, keeps the output
as evidence, and reports every range covering:
- 0x7C00–0x9FFFF;
- 0x30000–0x80000;
- 0x100000–0x400000.

Conventional or BootServices* memory = free after ExitBootServices; any
other type = a collision, reported and not designed around. If
practical, it also answers from GRUB 2.12's source whether the
x86_64-efi multiboot2 loader accepts load address 0x7E00.

**Named gap, no action:** the two sibling topology tests from bc06026
(`test_persist_quick`, `test_ahci_blk_writer`) are unwired.

**(e) The red's boot path** (owner, 2026-09-28, before code).
`uefi2_RED_kernel_runs_on_own_gdt` boots **`bmforth.img` on floppy +
`combined.img` on IDE**, the path the (a) register lines were captured
on. So its controls read the same path those lines came from, and no
re-capture is needed. On that path `MEMDISK_BASE` is 0 and blocks load
over ATA PIO. The memdisk path is covered by M1 (`test-memdisk`), not by
this red.

---

## Outcome

(written after the build; nothing above this line changes)

### Outcome — 2026-09-28 (QEMU; M3 is the HP trip, pending)

**Commits:** amendment (e) 9205d17, red 0eb5a33, then the fix and this
outcome.

**The fix (`forth.asm`):**
- **The kernel's own GDT.** `kernel_start` now opens with `lgdt
  [kernel_gdt_descriptor]`, a far jump through `KERNEL_CODE_SEL` (0x08),
  and `KERNEL_DATA_SEL` (0x10) into DS/ES/FS/GS/SS, before the stacks
  are set.
- **Where it lives.** `kernel_gdt` is a byte copy of `boot.asm:284-301`,
  next to `idt_descriptor`, inside the kernel image.
- **One block-image base.** `MEMDISK_BASE` became `BLK_IMAGE_BASE` at the
  same cell, 0x28098. The **6 code reads** were renamed (vector choice,
  BLOCK, LOAD, `-->`, `ram_read_block`), and the old name survives only
  in the handoff comments. `boot.asm` is untouched.
- **Size and lint.** `check-kernel-size` is OK (115200 of 115200), and
  asm lint is OK.

**Images:**
- `bmforth.img` `dfd7c5f3…` → **`848971e185ff08e8…`**;
- `combined.img` `51cad6cf…` → **`be05f8e7f53305e7…`**.

**The red: XFAIL, then XPASS, then removed.**
- **Before**, on bmforth `dfd7c5f3`: `GDT= 00007d90 00000017`, outside the
  kernel image. XFAIL, with every control passing
  (`uefi-2-red-2026-09-28.log`).
- **After**: `GDT= 0000abc8 00000017`, inside [0x7E00, 0x23E00), with
  CS=0008, DS=ES=SS=0010, limit 0x17 and the interpreter alive after the
  PCI-BAR THRU. That is XPASS, exit 1
  (`fix-uefi2-xpass-gate-2026-09-28.log`).
- **Removed.** The name came out of `UEFI_REDS` and out of the register.
  **Gate C showed both states: 2/2 at the XPASS, 1/1 after.** The same
  test now reports `PASS: uefi2 kernel runs on own GDT`.

**Must not move:**
- **M1 HELD.** `test-memdisk` 20/20 on the new image.
- **M2 HELD.** `make test` rc 0, "All tests passed!"
  (`uefi-2-make-test-2026-09-28.log`): 13 `XFAIL (expected)` (12
  translator + uefi1), 0 other failures, wiring 42/42, test-uefi2-gdt
  PASS.
- **M4 HELD.** The UEFI-1 red is still XFAIL with the control seen. The
  replica's new sha is **a9a796da5bc1afb6**, identical on two runs.
- **Block range held.** PCI-BAR is still 878–884:
  - the host resolver says so;
  - in the new `combined.img`'s own bytes, block 878 begins
    `\ CATALOG: PCI-BAR`, block 885 begins `\ CATALOG: PCI-ENUM`, and
    block 884 holds PCI-BAR's last lines. `KERNEL_PADDED_SIZE`, and so
    `BLOCKS_LBA_BASE`, are unchanged.
- **M3: the card is written and dry-run; the trip is pending.**
  `tools/pxe/DESK-CARD-UEFI-2.md` has both image hashes filled.
  - **The dry run** (`uefi-2-dryrun-2026-09-28.log`) booted pxelinux →
    memdisk → combined.img, as the HP does, with intel-hda at 00:04.0:
    - `878 884 THRU` loads from the RAM image, and `DEF? PCI-BAR` is
      nonzero;
    - the never-defined control prints 0;
    - `0 4 0 0 PCI-BAR64@ .H8` reads FEBB0000, with DEPTH 0 before and
      after;
    - it exits with DEPTH 0 and BASE 10.
  - **The dry run caught a false claim on the card.** It said
    `PCI-BAR vocab loaded` prints during the THRU, and it does not: not
    in the dry run, and not in HDA-3's iron log l.37-38, where the THRU line
    is followed by an empty line. (Corrected: l.61 was first written
    here from memory, and the log reads l.37-38.) The card now relies on
    `DEF? PCI-BAR`, and the dry run was repeated on the corrected card
    (sha `036c91da…`).
  - **Named, not taken:** the interpret-mode `."` at the end of a
    block-loaded vocabulary prints nothing.

**Carried into the UEFI-3 pre-registration** (desk finding, not acted
on). GRUB places the multiboot2 MBI and the `combined.img` module
wherever it likes, and either could land inside a fixed window
(0x7C00–0x9FFFF, 0x30000–0x7FFFF, 0x100000–0x3FFFFF). The kernel must
read both and, before touching those windows, either copy them clear or
refuse on overlap.
