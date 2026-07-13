# ForthOS Decision Log

Durable record of architectural and project decisions that aren't obvious
from the code itself. Each entry captures what was decided, why, and what
it means going forward.

---

## C/Python are bootstrap scaffolding, not part of ForthOS (April 2026)

**Principle:** The OS that boots on hardware is pure x86 assembly + Forth.
The build-time tools (C translator, Python block packer, test harnesses)
are host-side cross-development scaffolding. They never run on the target
and are not part of ForthOS.

**Origin:** Articulated in response to Forth2020 community pushback (April
2026) — the group made the classic Forth-purity critique: Forth means small,
no bloatware, no external toolchain, the system should rebuild itself "from
the ashes" in kilobytes. Resolution: every Forth needs something outside
itself to build the first image (bootstrapping); the metacompiler is what
eventually eliminates that external dependency so ForthOS rebuilds from its
own blocks.

**Consequences:**
- C translator is FROZEN as a finished bootstrap artifact. Its one job
  (binary → Forth vocabulary) works and is validated on real drivers
  (i8042prt and others on HP bare metal).
- Native-codegen branches (-t x64 / -t arm64 / -t riscv64), the optimizer,
  the RISC-V decoder, and the API mapper are abandoned by design, not
  unfinished by accident. Do NOT propose completing them.
- Dead CLI flags that parse but produce no output should either be removed
  or made to error honestly rather than silently succeeding.

**Forth-hosted translator (long-term, not a current task):** Translation in
Forth remains a legitimate future direction, philosophically aligned with the
project. Its prerequisite vocabularies already exist and work — DISASM (x86
decode, currently used for live debugging), the X86/ARM64/Thumb-2 assemblers
(machine-code emission), and the metacompiler (self-hosting) — but they have
NOT been composed toward binary translation. The C translator remains the
only working translation path. A future session should not assume the Forth
translator is partway built (it isn't), nor dismiss it as impossible (the
parts exist). The gui-harvest.fth UBT stub marks the intended hook point.

## UEFI is out of scope (May 2026)

**Decision:** UEFI support will not be implemented. ForthOS boots via
BIOS INT 13h/EDD by design. Future assessments should state "BIOS:
working, UEFI: out of scope" — not "partial."

**Reasoning:** UEFI is a giant firmware abstraction layer. "No HAL, no
abstraction layer" is the project thesis. Implementing UEFI would
contradict the design, not complete it. The February 2026 assessment
listed UEFI as a gap under Req #7 (Direct BIOS/CPU Communication);
the May 2026 audit confirmed this is a philosophical boundary, not a
missing feature.

---

## RTL8168 RX deferred — serial covers all inbound (May 2026)

**Decision:** RTL8168 receive-side Forth words are not a current task.
Serial (COM1) covers all inbound traffic on the HP.

**Context:** The NE2000 driver has full bidirectional capability
(NE2K-RECV, BLOCK-RECV, NET-RECV in net-dict.fth), but NE2000 is
QEMU-only. The RTL8168 (HP production NIC) enables RX in hardware
config but has no Forth-level receive words — it is TX-only. UDP TX
is proven on HP bare metal.

**Reopen trigger:** High-bandwidth inbound transfer to the HP over
Ethernet that serial cannot keep up with. Nothing in the current work
(form engine, network console, file streaming) requires this. A
TCP/IP stack is downstream of this decision — moot without RX.

---

## Gap #7 gated on HP foundation boot (May 2026)

**Decision:** Gap #7 (VOCABULARY-in-target) is gated on first
validating the current metacompiled kernel boots and runs
CREATE...DOES> on HP bare metal. The two are sequenced, not
combined -- foundation on metal first, then VOCABULARY on confirmed
ground.

**Rationale:** The metacompiler is QEMU-only to date (open gap #3 in
metacompiler_open_gaps.md). ATA block reads and memory map are the
historical QEMU/HP divergence points (Bug #24 stack-collision lineage,
AHCI PRDT DBAU, VGA-CLR-ROW masking). VOCABULARY emission may lean
on the same DOES> machinery, so designing it on the unconfirmed
assumption that DOES> works on HP would braid two risks. If the
foundation boot surfaces a hardware divergence, that changes the
VOCABULARY design; if it boots clean, Gap #7 proceeds on confirmed
ground.

---

**Distinguish UBT exposure from metacompiler exposure:** When marketing or
product claims are reconciled against reality, treat these two differently.
UBT (the C translator) was marketed against the maximalist vision, so its
claims must be narrowed DOWN to the working reality (binary → Forth vocab).
The metacompiler genuinely works as claimed; if it has any commercial gap it
is in packaging/docs for a customer to invoke it, not in the capability. The
correct direction is: lower UBT's claims to match engineering; raise the
metacompiler's productization to match the capability that already exists.
Neither case is a backlog of features to build.

---

## Test targets remain full-tier-only by design (June 2026)

**Decision:** `test-vocabs`, `test-gui`, `test-integration`, `test-flush`,
and `test-file-stream` chain through `$(COMBINED)` → `$(IMAGE)` →
`$(EMBED_VOCABS)`, which includes paid vocabularies. These targets are
not part of the public build surface and will fail on a public-only clone.
This is deliberate.

**Context:** The Makefile auto-detects the build tier via
`$(wildcard forth/dict/ahci.fth)`. User-facing targets (`all`, `iso`,
`run`, `run-gui`, `run-serial`, `debug`, `test-smoke`, `test-loops`)
route through `$(ACTIVE_IMAGE)` and work on both full and free clones.
The combined-image test targets require paid vocabs by nature (they test
AHCI, NTFS, RTL8168 functionality) and cannot meaningfully run without
them.

**Residual leak:** The `EMBED_VOCABS` variable on Makefile line 44 still
names all paid vocabulary filenames in the public source. This is a
build-graph information leak (a reader can see `ahci.fth`, `ntfs.fth`,
etc.). A future refactor could move the full-tier block into a separate
`Makefile.paid` that only exists in the private repo. Low priority —
the filenames are not secret, just the content.

---

## Kernel size ceiling clarification (June 2026)

**Correction:** Prior commit messages and session handoffs stated "kernel
is at the 0x1C000 ceiling, can't add words." This was a misreading that
conflated two distinct constraints and steered decisions since 2026-05-24.

**What's actually true:** `KERNEL_PADDED_SIZE` = 0x1C000 (114,688 bytes)
is the padded image size. Code+data ends at ~111,172 bytes (measured
2026-06-11), leaving **~3,500 bytes of slack** within the current limit.
Adding small kernel words (e.g., 64 bytes for two DEFCODE words) fits
trivially with no padded-size bump and no memory-map check.

**The real constraint:** Bumping `KERNEL_PADDED_SIZE` itself (not adding
words within it) requires a memory-map collision check against the
return-stack region at 0x1C000+ (Bug #24/#26 territory). As long as
code+data stays under 114,688 bytes, no bump is needed.

**How this propagated:** Commit `4d62781` said "Not added to full-tier
EMBED_VOCABS — kernel is at 0x1C000 ceiling." Session handoffs repeated
it as a hard constraint. The settings-form vocab was kept out of
`EMBED_VOCABS` on this basis. The actual measurement (3,500 bytes free)
shows the constraint was not binding.

**Going forward:** Before claiming "no room in the kernel," measure:
build, then check `(padded_size - last_nonzero_byte)` in kernel.bin.
The padded-size ceiling is real but the headroom within it is nonzero.

---

## Firmware-provided facts are read, not hardcoded (July 2026)

**Date:** 2026-07-11
**Status:** Accepted
**Scope:** All boot paths, all architecture ports

### Statement

Any value that firmware owns — memory ranges, table locations, hardware
description structures (ACPI tables, Device Tree blobs), core topology,
interrupt routing — must be read from the authoritative firmware source at
boot. A constant in ForthOS source that duplicates a firmware-assigned value
is a defect of the stale-constant class, same severity as a silent failure
or a false `ok`.

Where a constant must exist anyway (an origin choice like `A64-ORG`, a load
address, a buffer placement), it must be paired with a boot-time assertion
that validates the choice against the firmware-provided data and fails
loudly on collision. An unvalidated origin is a latent Bug #24-class
boundary collision waiting for a firmware revision to expose it.

### Motivating incident

The ARM64 virt port placed `A64-ORG` at 0x40000000 — the same address where
QEMU places the Device Tree blob at the base of RAM. The collision corrupted
the DTB and was found by observation, not by any check. The fix (moving
`A64-ORG` to 0x40100000) is currently another unvalidated constant. This
decision requires it to be backed by an assertion: at boot, read the DTB
header at the address firmware hands us, extract `totalsize`, and verify the
kernel image and `A64-ORG` region do not overlap `[dtb_base, dtb_base +
totalsize)`. Loud failure on overlap. This assertion lands as part of the
current ARM64 Phase C arc, not after it.

### Framing

This is the five-planes discipline applied at the boot boundary. Firmware
tables (E820, ACPI, DTB) are the machine's own statement of its physical
map plane. A hardcoded firmware-owned address in vocabulary or kernel source
is the address plane leaking into the code plane — the same plane-leak class
as the UI-CORE hardcoded-address crash on the HP. The fix is the same:
factor the address out of source and into data read from the authority at
runtime.

This is explicitly **not** a hardware abstraction layer. ForthOS parses
firmware tables the same way it walks an MFT: as data structures at
addresses, exposed as named Forth words, inspectable from the prompt.
Firmware tables are inputs to the surveyor, not layers to live behind.

### Enforcement

1. **Read, don't assume.** E820 (legacy x86), UEFI GetMemoryMap (when the
   UEFI path exists), and DTB memory nodes (ARM) are parsed during survey
   and exposed as words.
2. **Assert every origin.** Any load-address or region-placement constant
   gets a boot-time (or build-time, where the data is static) assertion
   against the firmware map. Assertions fail loudly — no `ok` on a machine
   whose map contradicts our constants.
3. **Fact vs. policy filter.** External "OS best practices" material is
   evaluated item by item: does this describe a fact about the machine
   (adopt: parse it, name it, expose it) or a policy about who may touch
   the machine (evaluate against VISION.md; usually reject)? Rejections are
   documented in docs/FIRMWARE-CONTRACT.md so they are strategy, not
   omissions.

### Consequences

- Immediate: DTB-overlap assertion added to the ARM64 boot path (this arc).
- Near-term: the embed-boundary HERE-delta assertion (already queued from
  the SHUTDOWN/Bug #24 work) is the x86 sibling of this rule and should
  cite this decision when it lands.
- Ongoing: per-platform boot contracts live in docs/FIRMWARE-CONTRACT.md;
  every new port's survey-phase checklist gates on them.

---

## ARM64 boot stub: trampoline, not larger reservation (July 2026)

**Decision:** The 0x100 boot-stub reservation stays fixed. Future growth
(DTB capture, additional init) uses a trampoline: the stub captures x0
and branches to a boot-extension routine emitted in normal code space.

**Motivating incident:** VBAR_EL1 install (2026-07-12) filled the stub to
exactly 256/256 bytes. The build-time assertion (VBAR-STUB-OVF) now fires
on any addition. The next queued task (TASK_DTB_ASSERT) requires at least
one more instruction in the boot path.

**Why trampoline over a larger reservation:**
- A raised ceiling (0x200, 0x400) is still a ceiling — it invites filling
  and eventually hits the same problem at a higher address.
- The trampoline removes the ceiling entirely: the stub becomes a fixed
  preamble (capture, branch) and the extension routine lives in the same
  address space as all other emitted code, growing freely.
- The 0x100 reservation and its assertion become a guard on a stable,
  known-size trampoline rather than a slowly-growing blob.

**Rejected alternative:** Growing the reservation to 0x200 or larger.

**Implementation:** Lands with TASK_DTB_ASSERT (next after #33e).
