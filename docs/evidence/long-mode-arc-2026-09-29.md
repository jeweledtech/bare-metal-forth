# LONG-MODE arc: 64-bit execution on ForthOS (scoping, 2026-09-29)

Written as a staged plan, not code. It follows the UEFI arc's shape:
each stage is its own commit, red before green, with a must-not-move set
that keeps the shipping 32-bit kernel intact. **No stage starts before
the owner picks the fork in §3.**

**Owner direction (2026-09-29):** a 64-bit vocabulary, with the option
to run 32-bit software. The motherboards are 64-bit; the interesting
applications are PE32+.

## 1. Where we start (measured 2026-09-29)

- The kernel is **32-bit protected mode, no paging**. It enters at
  `KERNEL_ORG` 0x7E00, runs on its own GDT since UEFI-2 (code 0x08, data
  0x10), and its IDT gates hard-code 0x08.
- It is **Direct Threaded Code on 32-bit assumptions**: `ESI`=IP,
  `EBP`=return stack, `ESP`=data stack, `EAX`=TOS, `NEXT` = `lodsd ;
  jmp [eax]`, cells 4 bytes. 202 `DEFCODE`/`DEFWORD` primitives are
  written to that model; ~433 lines name a 32-bit register directly.
- The fixed low-memory layout (data stack < 0x7C00, return stack to
  0x28000, variables 0x28000, dictionary 0x30000-0x80000, physical pool
  0x100000-0x400000) is **32-bit physical addressing with no page
  tables**.
- The application corpus is **PE32+** (64-bit): the kdrv set is
  `pe32plus=True`, and the one app-closure run (dbInstaller.exe, 26100)
  is a 64-bit binary reaching win32u/kernelbase.

**So the mismatch is real:** the target software is 64-bit, and every
part of the kernel that would host it is 32-bit.

## 2. What entering long mode actually requires (from the ISA)

Long mode is not a mode bit on top of today's kernel. The CPU requires,
in order: PAE on (`CR4.PAE=1`), a 4-level page table built and loaded
(`CR3` → PML4), `EFER.LME=1`, then paging on (`CR0.PG=1`), then a far
jump to a **64-bit** code segment (a GDT descriptor with the L bit set).

Two consequences the current kernel has never faced:
- **Paging becomes mandatory.** The kernel has run on flat physical
  addresses with no page tables. Long mode has none of that; even an
  identity map must be built and maintained.
- **A 64-bit GDT.** The UEFI-2 GDT is 32-bit descriptors. Long mode
  needs 64-bit code/data descriptors (and, for 32-bit compat, a 32-bit
  compatibility descriptor alongside).

**Compatibility mode is the good news.** x86-64 runs 32-bit code under a
64-bit kernel through a 32-bit code segment (compat mode). So "run 32-bit
software" does not mean a second kernel — it is a segment selector away
once long mode exists. That is why the owner's "64-bit with a 32-bit
option" maps onto the hardware, not against it.

## 3. THE FORK — the owner decides before any stage

What becomes 64-bit?

- **Model A — a 64-bit Forth kernel.** Rewrite the DTC core for 64-bit:
  `RSI`/`RBP`/`RSP`/`RAX`, 8-byte cells, `NEXT = lodsq ; jmp [rax]`, and
  every primitive and the dictionary layout with it. Native 64-bit
  substrate; effectively a kernel rewrite touching all 202 primitives.
- **Model B — the 32-bit Forth kernel hosts a 64-bit execution
  environment.** Keep the Forth kernel 32-bit. It builds long-mode page
  tables and switches a context into long mode to run **translated
  64-bit application code**, returning to the 32-bit kernel for
  OS-surface (vocabulary) calls. The substrate is untouched; the
  mode-switch boundary and the 32/64 calling bridge are the new hard
  parts.
- **Model C — decide after LONG-1.** Prove the machinery (enter long
  mode, run a trivial 64-bit stub, return) before committing A or B.
  Cheapest first step; keeps both doors open.

**B's cost, named so it is not discovered later (owner, 2026-09-29):**
B introduces a **mode boundary**, and every OS-surface call from a
64-bit app crosses it (64-bit app → transition → 32-bit Forth vocabulary
→ back). A 32↔64 transition layer *is* a layer, and that sits awkwardly
against the project's "nothing between a word and the silicon" pitch. It
is not assumed away: **its per-call cost is measured at LONG-2**, not
hand-waved. The reason to accept it anyway is that the boundary is
**explicit and inspectable** — a named trampoline you can read — rather
than a HAL hiding the hardware behind a device model. That is a different
thing from the layers the Non-Goals reject, and the doc says so on the
record.

**Recommendation: C first, then most likely B.** B preserves the shipped
32-bit kernel and every gate that guards it, and it matches the
project's actual goal — the 64-bit code we care about is *application*
code, not the Forth core. A is a rewrite whose cost lands before any app
runs. But this is the owner's call, and it is the one decision the rest
of the arc hangs on.

## 4. Staged plan (red-first; exact shape depends on §3)

Sequenced **after UEFI-5**: UEFI brings the kernel up on modern firmware;
long mode builds on that. Each stage keeps the 32-bit kernel booting.

- **LONG-0 — probe (read-only, before code).** In QEMU with a 64-bit
  CPU, confirm the guest CPU reports long-mode support (CPUID
  0x80000001 EDX bit 29) on the machine types we boot. Record it. No
  kernel change.
- **LONG-1 — enter and return (the mechanism).** From the 32-bit kernel:
  build an identity-mapped PAE page table over the low region, a GDT
  with a 64-bit code descriptor, enter long mode, run a stub that writes
  a known value, return to 32-bit PM. **Red:** a QEMU check that the
  known value appears and the kernel survives (a monitor read, like
  UEFI-2's). This is the go/no-go for A vs B — it tells us the switch is
  reliable before either path is built.
- **LONG-2 — the model.** Build A or B per §3. This is the large stage;
  it gets its own pre-registration with its own reds once §3 is decided.
- **LONG-3 — 32-bit compatibility.** Run a 32-bit code segment under the
  64-bit context; prove a known 32-bit sequence runs and returns.
- **LONG-4 — the application bridge.** Connect a translated application
  (from the closure work) to the OS-surface vocabularies across the
  32/64 boundary. Depends on the application-translation arc, which is
  separate.
- **LONG-5 — iron.** On a 64-bit machine, after UEFI. Its own card.

## 5. Must not move, every stage

- The shipping **32-bit kernel still boots to `ok`** (M1 memdisk, the HP
  card).
- **`make test`** stays green (expected XFAILs only).
- **Image size:** long-mode page tables and a second GDT cost kernel
  bytes; `check-kernel-size` (115200 limit today) is a hard gate. If the
  tables do not fit, that is a finding, reported, not worked around by
  raising the limit silently.

## 6. Open questions (not decided here)

- §3 itself.
- Where page tables live in the fixed layout, and whether they collide
  with the pool or dictionary (the UEFI-MMAP-0 method applies).
- Whether B's 32/64 call bridge can reuse the existing vectored-execution
  pattern or needs a new trampoline. Its per-crossing cost is a LONG-2
  measurement (see the named boundary cost in §3).
- The addressing "tool" the owner mentioned: with paging, 64-bit
  addresses are virtual. A translated app's pointers become page-table
  entries, not raw physical addresses. This is B's core mechanism, sized
  in LONG-2, not before.

**Prerequisite, stated plainly:** none of this starts before UEFI-5
closes and the owner picks §3. LONG-0 is read-only and can run any time.
