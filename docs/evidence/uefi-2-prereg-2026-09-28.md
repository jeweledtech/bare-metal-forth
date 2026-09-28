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

---

## Outcome

(written after the build; nothing above this line changes)
