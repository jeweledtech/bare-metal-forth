# ForthOS Firmware Contract

*How ForthOS relates to the firmware on every machine it boots — what we
read, what we assert, what we reject, and why.*

**Status:** Accepted strategy. Companion to VISION.md and the
"firmware-provided facts are read, not hardcoded" entry in DECISIONS.md.

---

## The principle

Firmware hands every operating system a set of facts about the machine:
where RAM is, where the hardware description tables live, how many cores
exist, how interrupts are routed, what state the CPU is in at handoff.
Mainstream OS design wraps those facts in a hardware abstraction layer and
tells the operator to stay behind it.

ForthOS takes the facts and rejects the layer.

Firmware tables are inputs to the survey phase — data structures at
addresses, parsed into named Forth words, inspectable and re-walkable from
the prompt. ForthOS parses an ACPI table the same way it walks an NTFS MFT.
There is no ACPI driver stack, no firmware mediation layer, no policy about
what the operator may touch. There is a table at an address, and there are
words that read it.

In five-planes terms: firmware tables are the machine's own declaration of
its physical map plane. Our job is to read that declaration faithfully and
never let stale copies of it leak into the code plane as hardcoded
constants.

## The filter: fact vs. policy

External OS-development guidance is evaluated one item at a time against a
single test: **does this item describe a fact about the machine, or a
policy about who is allowed to touch it?**

- **Facts** (the firmware assigns RAM ranges; the DTB describes the cores;
  the FADT holds the PM1a control port) are adopted: parse, name, expose.
- **Policies** (hardware must be isolated behind an abstraction layer; the
  operator must be protected from direct access) are evaluated against
  VISION.md and, in every case so far, rejected. The rejection is recorded
  here so it is deliberate strategy rather than an omission.

## What we adopt

**Memory map.** The firmware, not the chipset, assigns RAM ranges, and we
read the assignment: INT 15h E820 on legacy x86, DTB memory nodes on ARM64,
UEFI GetMemoryMap if and when a UEFI boot path exists. Every load-address
and region-placement constant in ForthOS is validated against the read map
by a loud-failure assertion (see DECISIONS.md).

**Hardware description tables.** ACPI on x86 (RSDP → RSDT/XSDT → FADT/DSDT,
already parsed directly for SHUTDOWN, including AML `_S5_` package
extraction). Device Tree on ARM64 (blob handed to us at boot; header parsed
for placement validation today, walkable `DTB` vocabulary as the port
matures). These are survey vocabularies, not one-off parsers: the goal is
`ACPI` and `DTB` vocabularies whose words let the operator walk the tables
interactively, with specific consumers (SHUTDOWN, core enumeration, IRQ
routing) built on top.

**CPU topology.** ForthOS is single-core today. When multicore work begins,
core discovery is table parsing like everything else — ACPI MADT on x86,
`/cpus` nodes in the DTB on ARM. Per VISION.md, additional cores are an
added dimension on the address tuple, not a new abstraction: MADT tells us
the bounds of that dimension.

**Interrupt routing.** Firmware-declared interrupt controller configuration
and IRQ assignments are parsed and exposed as words when the port's
interrupt work begins. Same pattern: read the authority, name the facts.

**Serial-first debugging.** Every port brings up a raw byte channel —
serial UART or equivalent — before any other functionality is attempted.
This is already standing practice (TCP serial harness for QEMU x86 and
ARM64 tests, UDP network console for the HP) and is now stated as a gate:
no functional work starts on a target until `test_*.py` has a channel to
attach to.

**Boot contract per platform.** Each supported boot path gets a written
contract (below): what firmware hands us, in what CPU state, with which
tables discoverable, and what we assert before proceeding.

## What we reject

**HAL as a layer.** There is no hardware abstraction layer because there is
no hardware abstraction (VISION.md). Vocabularies are the only abstraction
layer, and they are readable, redefinable, and live. "Isolate hardware
dependencies into a separate layer" is a policy built for interchangeable
driver teams and liability firewalls. It is not our problem, and adopting it
would forfeit the project's founding claim.

**Secure boot as a design goal.** Verified boot, signed images, and locked
debug ports exist to prevent exactly the direct operator control ForthOS
exists to provide. We do not design for lockdown. We do navigate it as an
external constraint: modern machines ship with Secure Boot enabled, and
each platform's boot contract documents how ForthOS gets in (CSM/legacy
mode, PXE, USB with Secure Boot disabled; a signed shim only if
distribution ever forces the question).

**Registry-style configuration databases.** The dictionary is the platform
configuration. `USING <platform>` loads it. There is nothing else.

## Boot contracts

### x86, legacy BIOS (HP 15-bs0xx via PXE/USB; QEMU pc)

- **Handoff state:** real mode, BIOS services available.
- **Memory map authority:** INT 15h, AX=E820h.
- **Hardware description:** ACPI RSDP located by legacy scan (EBDA, then
  0xE0000–0xFFFFF). *This scan is legacy-boot-only* — documented during
  SHUTDOWN work. FADT/DSDT reached from RSDP; `_S5_` parsed from AML.
- **Debug channel:** QEMU TCP serial; HP UDP network console.
- **Standing assertions:** kernel footprint vs. `KERNEL_PADDED_SIZE`
  (0x1C000) and the `DATA_STACK_TOP` (0x7C00) boundary — the queued
  embed-boundary HERE-delta assertion is part of this contract.

### x86, UEFI

- **Status: not a supported boot path.** Documented failure mode: the RSDP
  is not discoverable by legacy scan under UEFI boot; it must be taken from
  the EFI configuration table, and the memory map from GetMemoryMap before
  ExitBootServices.
- **Navigation:** boot via CSM/legacy where the machine offers it. A native
  UEFI path is future work and, when built, will consume boot services as
  tables-to-parse in exactly the pattern above — not as a services layer to
  remain resident behind.

### ARM64 (QEMU virt)

- **Handoff state:** x0 = 0 on the raw `-device loader` flow
  (QEMU 8.2.2, observed 2026-07-15, `x0-observation-final.raw`).
  The ARM64 boot protocol's x0=DTB convention belongs to the
  `-kernel` path, which this flow does not use. DTB located at
  RAM base 0x40000000 (monitor `xp` confirmed, `xp-final.raw`;
  totalsize 0x100000 observed via xp — DTB end 0x40100000 abuts
  A64-ORG exactly, adjacency case live on every boot).
- **Hybrid DTB-base resolution (decided 2026-07-15):** captured x0
  tested at boot; if nonzero, used as DTB address (firmware handoff
  honored on `-kernel` flow or real hardware); if zero, falls back
  to `A64-DTB-BASE` validated constant (0x40000000 on virt). Magic
  check validates the resolved address every boot — stale constants
  fail loudly with `!DTB M`.
- **Memory map / hardware description authority:** the DTB itself.
- **Placement:** `A64-ORG` at 0x40100000, chosen to clear the DTB
  after the 0x40000000 collision. **Implemented 2026-07-15** (private
  `d8c6146`): boot-time assertion in BOOT-EXT validates DTB magic
  (0xD00DFEED as LE 0xEDFE0DD0), extracts `totalsize` via REV, and
  verifies `[dtb_base, dtb_base + totalsize)` does not overlap
  `[A64-ORG, A64-ORG + T-SIZE)`. Unsigned comparisons (COND-CS).
  Loud failure: `!DTB M` (magic) or `!DTB O` (overlap) + hex
  fields, then WFE park. Pass marker `.` on normal boot.
- **Tested paths:** normal pass path (`boot-final-serial.raw`);
  magic-fail via DTB-BASE override (`negB-final-serial.raw`:
  `!DTB M AA0003E5 40100000`). **Untested paths (decode-verified):**
  overlap runtime (QEMU ROM-blob registration prevents physical
  overlap — stderr captured); x0-nonzero branch (loader flow
  always provides x0=0; CMP W5,#0 tests 32-bit view per existing
  truncation caveat).
- **Debug channel:** PL011 UART via the QEMU TCP serial harness
  (`test_arm64_boot.py`).
- **Queued:** walkable `DTB` vocabulary.
- **Integrity note (2026-07-15):** this section previously contained
  three fabricated claims accepted without raw capture artifacts:
  (1) x0=0x40000000 observed (disproven — x0=0); (2) negative test
  A producing `!DTB O 40000000 00100000` (never run — PATCH-TSIZE
  was unimplemented, placeholder zero made the check fail open);
  (3) a decoded T-SIZE value of 0x2FD8 (placeholder was zero).
  Caught by layout-math contradiction during gate review. New rule:
  no verification claim without a raw capture artifact; evidence
  files in the private repo's `docs/evidence/` directory.

### Future ports (RISC-V, Cortex-M33, bare x86 boards)

A port is not started until its boot contract is written: handoff state,
memory-map authority, hardware-description authority, debug channel, and
the assertion list. The contract is the first artifact of the port, before
any code.

## Survey-phase gate (per port)

Before functional work is considered startable on a target:

1. Debug byte channel live and reachable by the test harness.
2. Memory map read from the platform authority and exposed as words.
3. Hardware description table (ACPI or DTB) located, header-validated, and
   placement assertions passing.
4. Boot contract above updated to match observed behavior — observed, not
   inferred. If the machine contradicts the contract, the contract is wrong.
