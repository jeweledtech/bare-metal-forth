# Two findings, read only, 2026-09-20: the emission path, and tier-1 from imports

Read at the owner's request before (a) is pre-registered. No code
changed, no decoder touched. Both read from source and from bytes.

## 1. The UIR → Forth emission path: an emitter exists, but nothing
##    consumes UIR to produce code

**Files.** `src/codegen/forth_codegen.c` (417 lines) with
`include/forth_codegen.h` (117); `src/codegen/codegen.c` is a
one-line placeholder (`/* Placeholder - Code generator */`). The
lifter is `src/ir/uir.c`.

**What the emitter consumes.** `forth_generate()` takes a
`forth_codegen_input_t`, whose per-function payload is
`forth_gen_function_t`: `{ name, address, port_ops[], hal_calls[],
is_init, is_poll }`. That is **semantic summary data**, not UIR. Grep
for `uir` in `forth_codegen.c` returns 10 hits and every one is the
substring inside `requires` / `forth_dependency_t`: **no UIR type, no
UIR instruction, no opcode reaches the emitter.**

**What it writes.** `emit_function` has four arms: no port ops and no
HAL calls → an empty stub `: name ( -- ) ;`; HAL calls only → the HAL
word names in sequence with stack effects; one port op → one register
read or write; several port ops → that sequence. There is no
translation of arithmetic, tests, branches or loops. The UIR's blocks
and edges are consumed by the *semantic analyzer* (to find port ops
and HAL calls per function) and then discarded.

**Plainly:** the lifter produces UIR; the semantic analyzer reads UIR
to classify; **nothing reads UIR to emit code.** The third leg of
translate-and-run is not a stub returning nothing and not a design
document — it is a working emitter of vocabulary *skeletons*, and the
instruction-level leg does not exist.

**And the emitter is gated by (a) today.** `STRIP` lines, measured:

| input | total | kept | scaffolding | unclassified |
|---|---|---|---|---|
| ACPI | 2577 | 13 | **0** | 2564 |
| disk | 193 | **0** | **0** | 193 |
| HDAudBus | 346 | **0** | **0** | 346 |
| i8042prt | 203 | 2 | **0** | 201 |
| pci | 1642 | **0** | **0** | 1642 |
| HP serial | 177 | 31 | **0** | 146 |
| storport | 1620 | 20 | **0** | 1600 |
| usbxhci | 1466 | **0** | **0** | 1466 |
| ReactOS serial (PE32) | 36 | 9 | **25** | 2 |
| ReactOS beep (PE32) | 9 | 3 | **6** | 0 |

On both 32-bit controls the classifier works in both directions: it
keeps hardware functions *and* recognises scaffolding. On **every**
64-bit driver, scaffolding recognised is **0** and nearly everything
is unclassified, because classification attributes imports to call
sites through the IAT cross-reference, and that matches 0 on 64-bit
(the (a) defect, measured corpus-wide 2026-09-19). The few "kept" on
ACPI, i8042prt, HP serial and storport come from *direct* IN/OUT
instructions, not from imports. So the Forth output for a 64-bit
driver today is a catalog header plus a manifest of unclassified
function addresses. **(a) is the gate on the product's existing
output, not only on a row count.**

## 2. Tier 1 from the import directory alone: the data already
##    separates the corpus

Counted from each PE's import directory by bytes (descriptors walked,
thunk arrays to their terminators, hint/name strings read).

| input | funcs | DLLs (the discriminator, ntoskrnl elided) | hardware marks in the names |
|---|---|---|---|
| ACPI | 272 | HAL(12), WMILIB, WppRecorder, ext-ms-win-ntos-ksr | MMIO map, interrupt, timing, PCI config |
| HDAudBus | 91 | HAL(2), WMILIB, **portcls**, WppRecorder, WDFLDR | MMIO map, interrupt, timing |
| disk | 95 | **CLASSPNP(33)** | — |
| i8042prt | 97 | HAL(1), WMILIB, WppRecorder | MMIO map, interrupt, timing |
| pci | 256 | HAL(6), **PSHED**, WppRecorder, ext-ms-win-ntos-ksr | MMIO map, DMA, interrupt, timing, PCI config |
| HP serial | 70 | HAL(1: KdComPortInUse), WMILIB | MMIO map, interrupt |
| storport | 264 | HAL(2) only | MMIO map, DMA, interrupt, timing |
| usbxhci | 143 | HAL(2), WppRecorder, **SleepStudyHelper**, WDFLDR | MMIO map, timing |
| ReactOS serial | 47 | hal(5) | **port I/O** (READ_PORT_UCHAR/WRITE_PORT_UCHAR), interrupt |
| ReactOS beep | 23 | hal(5: incl. **HalMakeBeep**) | — |
| nmap | 70 | ADVAPI32, KERNEL32, msvcrt, libssp | — (not a driver) |

**Do the import sets alone separate the brief's categories? Largely
yes, and the exceptions are informative.**
- **Unambiguous from the DLL set alone:** disk → storage class
  (`CLASSPNP.SYS`, 33 functions); HDAudBus → audio (`portcls.sys`);
  usbxhci → WDF bus device (`WDFLDR.SYS` + `SleepStudyHelper.sys`,
  and no WMILIB); pci → bus/platform (`PSHED.dll` plus
  `HalGetBusDataByOffset`, `HalTranslateBusAddress`); ACPI → platform
  (the richest HAL set, 12 functions, plus the kernel-soft-restart
  extension DLL); nmap → not a driver at all (user-mode CRT/Win32).
- **Needs function names, not DLLs:** storport imports only ntoskrnl
  and HAL, so its DLL set is indistinguishable from a generic driver;
  its signature is in the names (DMA adapter + common buffer +
  `KeQueryPerformanceCounter`), which the marker scan finds.
- **Genuinely close:** i8042prt and HP serial are both thin-HAL legacy
  port devices and differ only by `WppRecorder`. Calling both "legacy
  port device" is arguably the correct answer rather than a failure.
- **The strongest single signals are in HAL:** `READ_PORT_UCHAR` /
  `WRITE_PORT_UCHAR` mark the ReactOS serial driver as port-I/O
  outright, and `HalMakeBeep` names beep.sys's entire function.

**Is it already exposed, or parsed and discarded?** Exposed, and
partly wasted. `translator -t report` emits an `imports` array with
one object per import: `{dll, name, category, is_hardware}` (disk:
95 entries, 62 ntoskrnl + 33 CLASSPNP, matching the byte count
exactly). Two defects in what it exposes, both small:
- `category` is printed as a **raw hex number** (`"0x80"`, `"0x0"`,
  `"0x86"`) rather than the category's name, so the one field that
  carries the classification is opaque to any reader of the JSON.
- `is_hardware` is `false` for all 95 on disk, consistent with the
  classifier's driver-API vocabulary not covering `CLASSPNP.SYS`.

**Conclusion for tier 1.** Naming what a driver *is* does not need the
decoder, the lifter, or (a): the import directory is already parsed,
already counted correctly against the bytes, and already in the
report. What is missing is a naming layer over data in hand plus two
one-line reporting repairs (category as a name; a vocabulary that
covers the class DLLs). Tier 2 — "this *region* is the disk path",
attributing imports to call sites — is what (a) buys, and the STRIP
table above is the measurement of how little exists without it.

**Queue unchanged:** (a) next, then (o). Nothing here was built.

---

## Addendum 2026-09-20: what the two-byte NOP class bounds, against the tier ladder

Recorded here and not only on the defect register, because this is a
product-level bound and not only a decoder one.

**46% of every two-byte instruction in the corpus is currently reported
as a no-op** — 22,034 of 48,244, over 576,083 corpus instructions in 15
inputs plus the fixture. Of those, 11,047 are genuine multi-byte NOPs
(`0F 18`–`0F 1F`) and are correct. **The remaining 10,987 are real
instructions reported as doing nothing**, and the class behind them is
211 of the 256 two-byte opcodes.

**With (ad) unlanded the boundary is sharper still.** The lifter's
`default:` arm maps every unmodelled identity — including
`X86_INS_INVALID` — to `UIR_NOP`, so a refusal and a no-op are the same
value in the IR. Until that lands, **no amount of decoder repair
changes what any analyzer pass reads.**

**Against the ladder:**

- **Tier 1 — naming what a driver *is*, from the import directory —
  is untouched.** It never reads an instruction. Everything the tier-1
  section above concludes stands unchanged.
- **Tier 2 — attributing imports to call sites, which is what (a) was
  bought for — is bounded by this.** Every function-level claim about
  a function containing a two-byte instruction is unsound today: the
  analyzer cannot distinguish "this function does nothing here" from
  "we could not read this". A call-site attribution that walks past a
  mis-rendered instruction is not wrong at that instruction only; it is
  a claim about a region whose contents were not read.

**So the honest tier-2 statement, until (aa), (ac) and (ad) land:**
attributions are sound for regions containing no two-byte instruction
and unverified elsewhere, and the corpus is 48,244 two-byte
instructions deep. That is the size of the caveat, stated before anyone
quotes a tier-2 number.
