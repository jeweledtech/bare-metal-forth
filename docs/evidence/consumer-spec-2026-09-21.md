# Specification: a consumer of instruction identity (2026-09-21)

**Status: specification only. No code is written, and none should be
until this is read.** The decoder queue closed with 18 reds green; this
is what starts now.

**The discipline changes shape, and the change is stated first.** This
is **new construction**, not a repair: `src/codegen/codegen.c` is a
35-byte placeholder and `src/optimize/optimize.c` a 30-byte one, so two
of the four pipeline stages do not exist. What carries over from the
decoder arc is **a written spec before code** and **a failing test
first**. What does not carry over is the method that made that arc
work — predicting an instrument's delta — because that needs an
existing artefact to predict *about*. Section 6 says what replaces it.

---

## 1. The one fact that decides the shape

**The product has exactly one instruction-derived hardware signal
today — port I/O — and it produces nothing on the corpus.**

Measured, `serial.sys`, the most port-heavy driver in the set:

| | value |
|---|---|
| `IN`/`OUT` instructions in the file (by bytes) | **135** |
| `hardware_functions` in the report | 48 |
| functions with `ports_accessed` non-empty | **0** |
| `port_operations` in the report | **0** |
| functions with `has_port_io` true | 31 |

Those 31 are true **from the import table**, not from an instruction:
`semantic.c:426` sets `has_port_io` when a matched IAT import is
categorised `PORT_IO`. The same holds for `has_mmio`, `has_timing` and
`has_pci` at lines 427–429.

**Corrected 2026-09-21: the figure is 320, not 8,224.** The first draft
counted `"address"` occurrences in the JSON instead of parsing the
array, which counts every address the report prints anywhere. Re-taken
by parsing:

| driver | hardware functions | instruction-derived |
|---|---|---|
| storport | 85 | **0** |
| usbxhci | 58 | **0** |
| serial | 48 | **0** |
| ACPI | 45 | **0** |
| i8042prt | 31 | **0** |
| pci | 29 | **0** |
| HDAudBus | 21 | **0** |
| disk | 3 | **0** |
| **total** | **320** | **0** |

**Zero of 320.** Every hardware function across the eight drivers is
classified from imports alone, and not one carries an
instruction-derived hardware fact. The smaller denominator makes the
statement stronger, not weaker: 320 is the whole claim the product
makes about hardware, and none of it rests on an instruction.

So the honest statement of today's tier 2 is narrower than it looks: it
attributes **imports** to call sites. It reads no instruction.

## 2. What the corpus actually contains, and why MMIO is the target

| signal | corpus total (8 drivers, 555,240 instructions) |
|---|---|
| `IN`/`OUT` | **166** |
| `INS`/`OUTS` | 8 |
| memory-referencing `MOV` | **140,250** |

**Port I/O is a rounding error in this corpus and MMIO is the
surface.** These are modern Windows drivers: a driver calls
`MmMapIoSpace`/`MmMapIoSpaceEx`, gets a pointer, and every subsequent
hardware access is an ordinary load or store through it. No import
appears at the access site, which is exactly why import-only
attribution cannot see it.

**That is what a consumer of instruction identity is for.**

## 3. What it reads

- **The UIR instruction stream per function** — now trustworthy at the
  identity level, which it was not two days ago: the decoder reports
  `UNKNOWN` for what it cannot name instead of `NOP`, and `INVALID` for
  what it refuses.
- **The existing call graph and IAT edges** (`sem_call_edge_t`,
  `iat_rva`), which already say *which call site* reached *which
  import*.
- **Nothing new from the decoder.** This consumer needs no further
  decoder work; that is what the queue bought.

**One precondition, and it is already lettered.** (af): the lifter maps
17 modelled identities to `UIR_NOP`, **1,089 corpus rows** — `SBB` 481,
`SETcc` 469, `CBW` 52, `CDQ` 32, `LEAVE` 23, `ROR` 14, `ADC` 9, `ROL`
9. A consumer that reads identity must not read a no-op where a
subtract-with-borrow was. **(af) is a dependency of this work and
should land first**, and it is one arm.

## 4. What it produces

A per-function record of **hardware access evidence derived from
instructions**, beside the import-derived record that exists:

| field | meaning | evidence |
|---|---|---|
| `mmio_regions` | values traced from an `MmMapIoSpace*` return to their uses | a call edge plus a def-use chain |
| `mmio_accesses` | loads/stores through such a value, with offset and width | instruction identity plus operand form |
| `port_accesses` | `IN`/`OUT` with the port operand resolved where it is an immediate, and named as DX-sourced where it is not | instruction identity |
| `access_confidence` | `direct`, `through-call`, or `unresolved` | which of the above applied |

**And it produces a refusal**, which is the part the arc has earned:
where the chain cannot be followed, the record says so rather than
omitting the function. A function whose accesses are `unresolved` must
be distinguishable from one that has none.

## 5. Which tier-2 claims it makes sayable

Today tier 2 can say: *"this function calls `MmMapIoSpaceEx`."*

With this consumer it can say: *"this function maps a region and writes
four bytes at offset `0x10`, then reads two at `0x24`"* — which is the
first thing in the product that resembles the brief's own sentence,
naming what a driver **does** with a device rather than which API it
links against.

**What it still cannot say, stated now so it is not claimed later:**
which *device* the region belongs to (that needs the PCI BAR
assignment, a separate input), and what the offsets *mean* (that needs
a device model, which is the vocabulary work, not this).

**That boundary belongs in the brief, not only here**, and is written
into `docs/FORTHOS_MULTIARCH_DESIGN.md` beside (ah)'s as-built section,
where a reader of the vision meets it.

## 6. What replaces delta-prediction, since there is no artefact yet

Four substitutes, each borrowed from something that worked:

1. **A denominator before a numerator.** The first deliverable is not
   a pass but a **census**: how many functions reach an
   `MmMapIoSpace*` call, and of those how many have a def-use chain the
   analysis can follow. The count of *followable* over *reachable* is
   the figure this work is judged by, and it is printed from the first
   run.
2. **A red per claim, before the claim is implemented.** A test per
   output field asserting the refusal case first: an unfollowable chain
   must be reported `unresolved`, not omitted.
3. **A hand-checkable fixture**, as `x64_reds` is for the decoder: a
   small driver-shaped binary with a known map-then-access sequence, so
   every claim has one instance a person can verify by reading bytes.
4. **Two instruments where possible**, at the level each can actually
   reach — see §7.1, which withdraws the first draft's claim that the
   hardware trip could attest this driver.

## 7. The exit number, fixed before the first line

**The decoder queue ended at eighteen reds green, and that number is
why it ended rather than drifting. New construction has no natural end,
which is this arc's standing failure mode, so the number is fixed
now.**

> **The consumer is done when it produces, for ONE NAMED DRIVER, a
> per-function statement in this specification's own form — region
> mapped, offset, width, direction — attested by a SECOND INSTRUMENT.**

The named driver is **`i8042prt.sys`** (the HP copy), chosen before the
work: 31 hardware functions, 21,373 instructions, and — the reason that
matters — **exactly one `MmMapIoSpaceEx` call site**, which is one
hand-checkable instance of precisely the chain this consumer exists to
follow.

### 7.1 What the second instrument attests: the function, NOT the device

**A claim in the first draft is withdrawn.** It said the HP trip
"recorded its behaviour independently". **It did not.** The trip
recorded xHCI (`BAR0 = 0xb1210004`); searching the banked iron logs for
`i8042` or `keyboard` returns **nothing**. There is no device-level
record for this driver, and the sentence was written without checking.

**So the attestation is at the instruction level, and that is what the
exit means:**

| claim | second instrument | what it can reach |
|---|---|---|
| this function calls `MmMapIoSpaceEx` | Ghidra's own analysis; objdump plus the import table by hand | **the function** |
| the returned pointer reaches this load/store at this offset | Ghidra's decompiler; a hand derivation from bytes | **the function** |
| the device was actually driven | **nothing available for this driver** | — |

**Worded to match what the instruments can do:** the exit is a
per-function statement **corroborated by a second analysis of the same
bytes**, not by a device. **A device-level record would confirm that
*something* drove the controller, never *which function did*** — so
even where such a record exists (xHCI), it could not discharge this
exit. That distinction is the reason to say it now rather than to
discover it at the exit.

### 7.2 A followed chain, not a resolved port number

**Finding (z), 20 September: the attested immediate-port set is EMPTY
across all eight HP drivers** — every port instruction they really
contain addresses its port through `DX`. Confirmed on the chosen
driver: `i8042prt` contains exactly **two** port instructions, `in
(%dx),%al` at `.text+263` and `out %al,(%dx)` at `.text+285`. **Both
DX-addressed.**

**So the easier bar is unavailable by measurement, not by choice, and
the exit takes the harder one: a FOLLOWED CHAIN suffices; a resolved
port number is NOT required.**

The statement the exit demands is of the form *"the value returned by
the call at X reaches the store at Y, offset Z, width W"* — a chain
with a named origin and a named use. **Where the origin cannot be
followed to a constant, the statement says so and remains a pass**,
because "followed to a register whose source is a parameter" is a true
statement about the function and a resolved number would be a
fabricated one.

**And for this driver the relevant chain is not a port chain at all.**
Its hardware access is one `MmMapIoSpaceEx` region plus HAL calls
(`KeSynchronizeExecution` 20, `KeInsertQueueDpc` 19,
`KeStallExecutionProcessor` 12). The single mapping site is the exit's
subject.

**Anything past that is a new phase with its own exit.** Not "the other
seven drivers", not MMIO for the general case, not a device model.
Those are decisions taken after there is one statement to judge.

**What does NOT count as meeting it:** a statement produced for a
function whose chain the analysis followed but whose result no second
instrument confirms. The attestation is the exit, not the output.

## 8. Order, and what waits

**First (af), PROMOTED from parked to prerequisite** — recorded as a
promotion rather than slipped in, and it gets its own
pre-registration, because 1,089 rows across 17 identities is a larger
change than (ad)'s one row was. A consumer of identity must not read a
no-op where an `SBB` was.

**Then the census** of §6.1, which decides whether the rest is worth
building at the size the corpus implies.

**Waiting behind this, per the ruling, unchanged:** (ai) at 450 rows,
(u)'s `0F 0F`, (ab), (t), (ae), (ah), the ARM64/RISC-V emitter join,
and the fourteen standing expected failures.

**What I am not proposing.** No decoder work. No new architecture. No
code generator or optimizer — those are two more pipeline stages, and
whether they are ever built is a separate decision that this
specification does not touch.
