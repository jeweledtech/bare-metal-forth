# TASK: kernel pad, room before the embedded stream grows again

Status: PLAN ONLY (2026-10-10), no change. Owner ruling 2026-10-10: queued
ahead of anything that grows the embedded stream.

## 1. Where it stands

- Pad `KERNEL_PADDED_SIZE` = 0x1C000 = 114,688 B. Kernel content 111,809 B
  (public `f3f46d1`, image `c33f0d3a…`); **2,879 B left**. The embedded
  token stream is 92,925 B of that; the rest of the kernel is
  18,884 B.
- Overflowing the pad fails loudly at assembly (`times` negative).
- The dictionary is a separate budget: test-meta's smallest margin is
  35,468 B below 0x7F800 (TASK_TOKEN_STREAM_LIMIT). Embedded code spends
  both: the stream from the pad, its compiled form from the dictionary.

## 2. Embedded vocabularies (EMBED_VOCABS, full build, in order)

Stream bytes from `tools/embed-vocabs.py` per file (they sum, with one
joining byte each, to 92,925). Dictionary bytes from the boot dump of
2026-10-10 (TASK_TOKEN_STREAM_LIMIT §7; catalog-resolver before
RELOAD-VOCAB). "Deps" = the file's `ALSO` / `REQUIRES:` names.

| # | file | stream | dict | deps |
|---|---|---|---|---|
| 1 | hardware | 4,933 | 5,832 | |
| 2 | port-mapper | 2,883 | 3,628 | HARDWARE |
| 3 | echoport | 2,570 | 3,252 | HARDWARE |
| 4 | pci-enum | 3,574 | 4,856 | |
| 5 | catalog-resolver | 7,364 | 5,168 (+RELOAD-VOCAB) | |
| 6 | ahci (paid) | 8,864 | 12,444 | HARDWARE PCI-ENUM |
| 7 | rtl8168 (paid) | 4,687 | 5,416 | ECHOPORT HARDWARE PCI-ENUM |
| 8 | ntfs (paid) | 8,711 | 10,472 | AHCI HARDWARE |
| 9 | auto-detect (paid) | 2,232 | 2,508 | AHCI NTFS PCI-ENUM RTL8168 |
| 10 | fat32 (paid) | 5,024 | 9,992 | AHCI HARDWARE |
| 11 | ui-core | 7,210 | 7,348 | |
| 12 | ui-parser | 2,689 | 2,796 | CATALOG-RESOLVER UI-CORE |
| 13 | ui-events | 2,759 | 6,724 | UI-CORE UI-PARSER |
| 14 | gui-harvest | 2,114 | 2,188 | CATALOG-RESOLVER UI-CORE |
| 15 | ps2-keyboard | 2,151 | 1,540 | |
| 16 | file-editor-core | 7,117 | | HARDWARE PS2-KEYBOARD |
| 17 | file-editor-disk (paid) | 545 | 78,900 for 16-18 | AHCI FILE-EDITOR NTFS |
| 18 | notepad-form | 1,771 | (64 KB is FE-BUF) | CATALOG-RESOLVER |
| 19 | notepad | 2,819 | 4,128 for 19-20 | FILE-EDITOR GUI-HARVEST UI-* |
| 20 | hello-form | 1,074 | | CATALOG-RESOLVER |
| 21 | hello-app | 1,444 | 1,116 | GUI-HARVEST UI-* |
| 22 | file-stream | 3,109 | 7,772 for 22-23 | AHCI NTFS RTL8168 |
| 23 | file-browser-form | 1,102 | | CATALOG-RESOLVER |
| 24 | file-browser | 6,156 | 6,180 | FILE-EDITOR GUI-HARVEST NTFS UI-* |

The free build has its own list (EMBED_VOCABS_FREE: no paid files, adds
settings-form and settings); this plan is about the full build.

## 3. What needs each one before blocks are readable at boot

At boot the embedded stream only defines words and sets data: no device
is initialised (`HARDWARE-INIT` is stripped by embed-vocabs.py), the only
output is auto-detect's `[AD-OK]` (no test, tool or doc reads it).
Whether blocks are readable depends on the boot path:

- **memdisk (PXE, the HP stick) and the UEFI module path**: the whole
  combined image is in RAM (`BLK_IMAGE_BASE` != 0), BLOCK reads it from
  the first instruction. Nothing embedded is needed to read blocks.
- **QEMU / legacy IDE disk boot**: BLOCK reads by ATA PIO directly
  (forth.asm 2847-2862). Nothing embedded is needed.
- **The installed instance on the HP** (VBR chainload, no memdisk;
  TASK_INSTALL_BOOT_ENTRY): BLOCK's ATA PIO path cannot reach an AHCI
  disk; blocks become readable only through AHCI, which overrides BLOCK
  (`' BLOCK CONSTANT KERNEL-BLOCK`, ahci.fth 532). So **AHCI and its
  deps HARDWARE and PCI-ENUM**, and **CATALOG-RESOLVER** (to load
  anything at all, and RELOAD-VOCAB, which must be resident: P1), must
  stay embedded.

  **Correction (2026-10-11, docs/TASK_KERNEL_PAD_MOVE.md §3):** "to load
  anything at all" is wrong for the installed instance. The installer
  writes no block store (only the kernel sectors and the VBR), so AHCI's
  BLOCK finds no catalog there and nothing can be loaded. AHCI stays
  embedded for disk access itself, not for loading. The "installed block
  store" task is queued. To be confirmed by observation: red I1 of the
  pad-move task.

Tests that boot the kernel with no blocks image (ACTIVE_IMAGE /
bmforth.img) and use embedded words: `test-phys-alloc` (HARDWARE, AHCI,
NTFS, RTL8168) and `test-pci-typing` (PCI-ENUM). Moving NTFS or RTL8168
means moving those tests to the combined image (and a LOAD-VOCAB). The
other no-blocks tests (smoke, loops, abort, dict-bounds, squote-laydown,
file-stream helpers, carrier-write-safe, uefi2-gdt, vbr) use no
embedded vocabulary.

## 4. Candidates for block-loading, and the cost of each

Rule (feedback_embed_deps): an embedded file whose `ALSO X` names a
moved vocabulary must move too, or the boot fails silently. So
candidates move as closed groups (a group = the file and everything
embedded after it that depends on it).

| group | files | stream freed | dictionary freed | cost |
|---|---|---|---|---|
| A apps | hello-form, hello-app | 2,518 | ~1.1 KB+ | demo only; `S" HELLO-APP" LOAD-VOCAB` first |
| B notepad | notepad-form, notepad | 4,590 | ~4 KB+ (NF-DATA 3 KB) | same; HP demos type NOTEPAD after a load |
| C file browser | file-browser-form, file-browser | 7,258 | ~6-8 KB | same |
| D editor | file-editor-core, file-editor-disk (+B, C: they ALSO FILE-EDITOR) | 7,662 + B + C = 19,510 | ~79 KB with B/C (64 KB FE-BUF) | the biggest dictionary win; every editor/app user loads first |
| E GUI stack | ui-core, ui-parser, ui-events, gui-harvest (+A, B, C: they ALSO UI-*) | 14,772 + A+B+C = 29,138 | ~19 KB + A/B/C | all forms load first; the widget checks in RELOAD-VOCAB find nothing (fine: looked up by name) |
| F PS2 | ps2-keyboard (+D) | 2,151 + D | | keyboard words load first |
| G diagnostics | port-mapper, auto-detect | 5,115 | ~6 KB | `[AD-OK]` gone (unused) |
| H file-stream | file-stream | 3,109 | ~7 KB | net file send loads first |
| I storage/net | ntfs, fat32, rtl8168 (+echoport if rtl8168 goes; +auto-detect, file-stream, file-editor-disk, file-browser) | 18,422 (20,992 with echoport), + dependents | ~29 KB+ | test-phys-alloc moves to the combined image; the HP net console and NTFS reads load first (blocks are in RAM on every HP boot path, so this works) |

Must stay (§3): HARDWARE, PCI-ENUM, AHCI, CATALOG-RESOLVER = 24,735 B of
stream.

A cheap first step that frees most of the pad without touching storage:
**A + B + C** (14,366 B of stream, the demo apps; no test boots them from
a kernel-only image), or **E** (29,138 B, the whole GUI stack). Every
group also frees boot dictionary, which raises test-meta's margin by the
same amount.

What it costs in every case: the words are not there at the `ok`
prompt; a user or a test types `S" NAME" LOAD-VOCAB` first. Tests that
use these words on the combined image (test-gui, test-vocabs,
test-integration, test-file-stream's recipe) need checking one by one in
the change task; this plan has not read each of them.

## 5. Growing the pad instead

The pad's end is pinned on both sides:

- **Memory.** The return stack runs from ORG + pad (0x23E00) to
  `RETURN_STACK_TOP` 0x28000, and the build asserts
  `RETURN_STACK_MIN` = 0x4200, which equals that headroom today exactly.
  Any pad growth fails that assert unless the system area moves. The
  system area is fixed: system variables from 0x28000 (STATE, HERE,
  LATEST, BASE, ..., search order 0x28020, FORTH LATEST 0x28048, block
  headers 0x28060, the block vectors 0x2809C/0x280A0), TIB 0x28100,
  block buffers 0x28200-0x291FF, IDT 0x29400, ISR hook table 0x29C00.
  The dictionary starts at 0x30000, so there is 0x2A000-0x30000 (24 KB)
  above the system area to move into.
- **Addresses written as literals outside the kernel** (would all change
  with the system area): catalog-resolver 12 (now includes RELOAD-VOCAB's
  0x28020/0x28044/0x28048), hardware 3 (HOOK-TABLE 29C00), mirror 10,
  target-x86 100 (the metacompiler's target image layout), disasm 2,
  xhci 2, install 2, firstboot 1, ahci 1; and 16 test/tool files.
- **Disk layout.** `BLOCKS_LBA_BASE` = boot sector + pad = 225 sectors:
  block N is at LBA 225 + 2N. Growing the pad moves every block: the
  combined image layout; 13 test/tool files that hard-code 225; the VBR's
  `KERNEL_SECTORS` (224, derived from the pad); tools/build-meta-image.py
  (hard-codes 114,688); the metacompiler's 225-sector image
  (target-x86.fth 1322); the installer's P6 sizing and the write floor
  (P6 on the HP is 34-582; HP_WRITE_CEILING block 910 = LBA < 2048;
  settings 192-207 and telemetry 208-215 are block numbers, so their
  LBAs move); every stick and installed instance built before the change
  stops matching.

**Collision history** (pattern_memmap_collision, six instances), all
"embed or dictionary growth runs into a fixed address", all fixed by
moving or growing the structure:

1. Bug #18: embed data grew past the data stack at 0x10000; stack moved
   to 0x7C00.
2. Kernel pad 96 KB -> 128 KB (kernel outgrew it).
3. Bug #26: embed growth into the return stack at 0x20000; return stack
   moved to 0x28000 with its own region and a NASM assert.
4. Pad 0x1A000 (2026-05-07): count-sort pushed the embed past 104 KB.
5. Pad 0x1A000 -> 0x1C000 (2026-05-11): TREE-RENDER, overflow by 1,015 B;
   the return-stack region silently shrank by 8 KB with it and its
   comment stayed stale for four months.
6. 2026-05-14: three VARIABLEs in file-browser (dictionary, not pad)
   crashed the HP; reverted, no structural fix.

Instance 5 is the warning for this option: the last pad growth quietly
took return-stack space. Today the assert would stop that, which is why a
pad growth now has to move the system area as well.

## 6. Recommendation (for the owner)

Block-load first, grow the pad only if that is not enough. Moving demo
apps (A + B + C, 14,366 B) or the GUI stack (E, 29,138 B) costs one
`LOAD-VOCAB` before use and touches no address, no disk layout, no
installed instance and no stick. Growing the pad moves the system area
(dozens of literal addresses in Forth, tests and tools) and every block
on every medium, the exact class of change that produced the six
collisions above.

The change task, if approved: pick the group; red first (a test that the
group's words are absent at boot and present after `LOAD-VOCAB`, plus the
pad figure); the dependents of each moved file listed from the source;
gates: make -k test, test-meta margins, test-install, the HP stick
check.
