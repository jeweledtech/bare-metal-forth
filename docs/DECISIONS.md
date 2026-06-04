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
