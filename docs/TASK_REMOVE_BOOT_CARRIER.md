# TASK: Remove the Boot Carrier

**Owner:** JeweledTech · A Jolly Genius Inc. company
**Status:** SCOPING — CARRIER-0 complete, CARRIER-1/2 blocked on N1
**Date:** 2026-09-29 (rev. 2, folds in CARRIER-0)
**Repo:** `jeweledtech/bare-metal-forth`
**Related:** `TASK_INSTALL_BOOT_ENTRY.md` (Branch D, `BUILD-VBR`), the UEFI arc
(UEFI-2…UEFI-5), `docs/evidence/carrier-0-memdisk-coupling-2026-09-29.md`,
the parked Creator spec (`forthos-creator/docs/`, separate repo)

---

## 1. The problem

ForthOS's pitch is that nothing sits between a word and the silicon. The boot
path contradicts it. `tools/make-uefi-usb.sh` produces a stick carrying:

- GNU GRUB, installed twice (i386-pc for legacy, x86_64-efi standalone)
- syslinux `memdisk`, in `raw` mode
- `forth.img` as an initrd payload on a FAT32 ESP

All of that executes on the target machine, in the boot path, before ForthOS
gets control. It is a Linux-world bootloader stack being used to start an OS
whose entire premise is the absence of such stacks. Every evaluator who looks
at the stick sees GRUB first.

**Goal: firmware hands control directly to ForthOS code. Nothing in between.**

---

## 2. Two halves, one goal

The carrier exists because firmware offers two entry contracts and ForthOS
currently satisfies neither on its own.

| Path | What replaces the carrier | Status |
|---|---|---|
| BIOS / CSM | ForthOS's own VBR — a 512-byte boot sector the firmware loads at 0x7C00 | **The code exists.** `BUILD-VBR` bakes `vbr.asm` for the disk install (Branch D). It needs retargeting to a removable stick. |
| UEFI | A UEFI application that starts the i386 kernel — the "C0a loader gap" named in `TASK_INSTALL_BOOT_ENTRY.md` | **This is the UEFI arc**, in flight at UEFI-5. |

This is not a new arc competing with the UEFI work. It is the same work, named
for what it buys: **UEFI-5 closing is what removes GRUB from modern machines.**
This doc scopes the BIOS half and the stick-specific pieces the install arc
does not cover.

---

## 3. What the BIOS half needs

`BUILD-VBR` writes a boot sector for a *partition on a fixed disk*. A stick
needs the same sector aimed at removable media. From the Branch D reuse audit,
most of it carries over:

- The read path is already DAP-driven, and the start LBA is a patchable field
  at `dap+8`. Retargeting is a value change, not a code change.
- The handoff — DL preserved, A20, GDT, PE bit, far jump, `jmp 0x7E00` — is
  LBA-agnostic and unchanged.
- `KERNEL_SECTORS = 224`, derived from `KERNEL_PADDED_SIZE` (0x1C000 / 512).
  Define it from `KERNEL_PADDED_SIZE` so a kernel-size change cannot desync it.
- CHS fallback becomes a fail path (EDD-or-die). Already decided; frees ~70
  bytes and cannot mask a wrong read.

---

## 3a. The memdisk coupling — CARRIER-0 findings

**This bites the UEFI arc before it bites carrier removal.** A UEFI-booted
ForthOS has no memdisk — there is no `memdisk raw` in a UEFI load path. The
moment UEFI-5 brings the kernel up on firmware with no CSM, the kernel is
already in the "base cell reads 0" case. CARRIER-0 is UEFI prep, not carrier
prep.

CARRIER-0 (`docs/evidence/carrier-0-memdisk-coupling-2026-09-29.md`) audited
every reader of the base cell. Three findings, in ascending order of how much
work they add:

### F1 — One cell, four names

`0x28098` is reached as `BLK_IMAGE_BASE`, `MEMDISK-VAR`, `MEM-BASE` and
`MEMDISK-BASE@`, duplicated because public code cannot name paid words. That
is a drift hazard independent of this task: four names means four places to
miss when the meaning changes, and the meaning is about to change. Worth its
own finding doc and a single canonical accessor before CARRIER-1 touches any
of them.

### F2 — The installer loses its kernel-byte source

`ABE-READY?` gates on `MEM-BASE != 0`. The installer's only pristine source of
kernel bytes is the memdisk RAM image (Decision B). On any non-memdisk boot —
native VBR *or* UEFI — the guard is unsatisfiable and the installer refuses.
A refusal is the safe failure, but it is still a failure: **installing ForthOS
from a UEFI-booted stick does not work today**, and nothing says so out loud.

### F3 — The cell means two things, and a native stick needs a third

This is the finding that resizes the task. The kernel's `BLOCK`/`LOAD`/`-->`,
the read/write vectors, and the paid AHCI `BLOCK` override all branch on this
cell to choose between **blocks in RAM** and **blocks on the internal disk**.
There is no third case for *blocks on the boot medium*.

So on a cell-0 boot, block access resolves to the **host's internal disk** —
not to the stick it booted from. Consequences:

- A native-VBR stick has no path to its own blocks until that third meaning
  exists. CARRIER-1 and CARRIER-2 must add it; discovering this at CARRIER-3
  would mean rewriting the stick layout after it shipped.
- **Open question for the UEFI arc, and it is urgent:** the audit names the
  *write* vector as one of the branchers. If a block write from a cell-0 boot
  resolves to the internal disk, then a UEFI-booted ForthOS writing a block
  writes to the host's disk rather than its own medium. Verify this before
  UEFI-5 closes. If it holds, it is a host-safety issue on the UEFI path, not
  merely a carrier-removal prerequisite, and it outranks everything else in
  this document.

### 3a.1 — CARRIER-0b follow-up: the fail-closed default is N1's first half

CARRIER-0b (`docs/evidence/carrier-0b-write-vector-2026-09-29.md`) confirmed
the write-vector concern from the code, with the nuances now folded into gate
C5 (compare a written LBA span, not LBA 0 — block writes start at LBA 225 and
never touch LBA 0).

**Is a stock installed instance's block write path working today?** (asked to
size whether a blanket fail-closed default is free):

- **The installer does not use block writes.** `ADD-BOOT-ENTRY` / `ADD-PARTITION`
  write the VBR, the 224 kernel sectors, and partition metadata through
  `SAFE-WRITE` / `SEC-WRITE-VEC` (raw sector writes, AHCI), never the block
  layer. So install is unaffected by the block write vector entirely.
- **Block writes (`SAVE-BUFFERS`) exist and are used** by `editor.fth`,
  `mirror.fth`, `net-dict.fth`, `video.fth`. On a cell-0 boot the default is
  `(BLK-WRITE-ATA)` → IDE-slave 0x1F0. On real AHCI/NVMe hardware nothing
  answers there, so working block persistence on the HP requires the paid
  `AHCI-RW`, which **overrides** the vector at runtime (`BLK-WRITER!`) — the
  boot-time default is moot for that path.
- **Nothing wired into `make test`, nothing on real hardware, and not G6**
  (whose "persist" is the monitor channel, not blocks) relies on the default
  ATA block writer. Only QEMU-with-IDE does (`test_persist_quick`, unwired).

**Therefore:** a blanket `(BLK-WRITE-NONE)` cell-0 default is *nearly* free but
not entirely — an installed instance is also cell-0 and legitimately wants ATA
writes (the QEMU-IDE / legacy-IDE case), so a blanket default trades a
host-safety risk for a regression on that path. **The fail-closed default is
therefore the first half of N1, not a separate decision:** fail-closed needs
the legitimate case to carry a *positive* signal first (a "this is my medium"
state), which is exactly N1's three-state design.

**UEFI-5 should define the third state for its own path without waiting for the
general N1 design.** A UEFI-booted kernel sets the base cell to a
**not-internal-disk** value, so its block writes land in the NONE (refuse)
branch. That closes the host-safety hole on the path where it is live, at
UEFI-5, and the general N1 design generalizes it afterward. This is the surgical
move: it does not touch the installed-ATA default that the QEMU-IDE path relies
on.

---

## 4. Stages

| Stage | Work | Runnable when |
|---|---|---|
| CARRIER-0 | Read-only audit of every reader of the base cell | **Complete** (9b86e8d) |
| CARRIER-0b | Verified (write-vector host-safety); **fail-closed default shipped**: cell-0 arms `(BLK-WRITE-NONE)` (708d1b4), gated by `test-carrier-write-safe` | **Done** |
| CARRIER-1 | Single canonical accessor for the base cell (F1); add the third block-source meaning (F3); retarget `BUILD-VBR` to removable media; stick layout | after N1 |
| CARRIER-2 | Resolve the installer's kernel-byte source (F2) | after N1 |
| CARRIER-3 | `make usb-image-native` — composed stick image with no GRUB, no memdisk, no FAT32 ESP | after CARRIER-1 |
| CARRIER-4 | UEFI stick entry, once the UEFI arc provides the loader | after UEFI-5 |

---

## 5. Gates

| # | Gate |
|---|---|
| C1 | QEMU: stick image boots to `ok` with no GRUB and no memdisk on the medium. `strings` on the image finds neither. |
| C2 | HP iron: same, via F9 → the USB entry. This is the real gate. |
| C3 | Blocks resolve to the boot medium, not the internal disk, on a native-stick boot. Red-first: prove the gate fails against today's two-meaning cell. |
| C4 | Installer either works from the native stick, or fails loudly and specifically — never silently half-installs. |
| C5 | Host untouched: LBA 0 of every fixed disk byte-identical before and after a native-stick boot *and* after a block write from one. |

---

## 6. What this does *not* solve

- Machines with no CSM still need the UEFI loader. Carrier removal on the BIOS
  side does not help them; UEFI-5 does.
- The Creator app, if unparked, still writes a composed image — just one with
  nothing but ForthOS on it. Carrier removal makes that work more defensible.

---

## 7. Open decisions

| # | Decision |
|---|---|
| N1 | How the base cell expresses three states instead of two (RAM / internal disk / boot medium). Blocks CARRIER-1 and CARRIER-2. Widened from "installer byte source" by CARRIER-0 F3. **First half = the fail-closed write default (CARRIER-0b): the legitimate installed-ATA case needs a positive "this is my medium" signal before a cell-0 boot can safely refuse; UEFI-5 sets the cell to a not-internal-disk value for its path ahead of the general design (§3a.1).** |
| N2 | Does the native stick keep a FAT32 partition for interop, or is it raw ForthOS blocks end to end? Raw is purer; FAT32 is how a user gets files on and off. |
| N3 | Ship carrier removal before or after the UEFI stick entry? BIOS-only means two stick formats in the wild for a while. |
| N4 | Canonical accessor for the base cell across the public/paid boundary (F1) — which side owns it, and what the public name is. |
