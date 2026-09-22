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

---

# Amendment: the second instrument, named and run once (2026-09-21)

**"Attested by a second instrument" was an exit with an unnamed gate** —
the same shape as a prediction with no named baseline, which has bitten
this arc three times. So it is named here, and **run once before any
pass exists that could be tuned against it**.

## The instrument

**Ghidra 12.1.2's own decompiler data flow**, pinned at snap revision
47 — the same pin as every other oracle run in this arc.
`tools/ghidra/MmioChains.java`, committed: for each call to a mapping
API it decompiles the containing function and walks the high-level
P-code varnode graph **forward from the call's output**, reporting
every load or store the returned pointer reaches, with size and offset.

It is a genuine second opinion rather than a re-run of our own logic:
different disassembler, different lifter, different data-flow engine,
and it was written and run before the pass it will judge exists.

## What it CAN reach, and what it CANNOT — measured, not asserted

**First run, `i8042prt.sys` (HP), the whole file:**

```
MMIOCHAIN  1c0012a70  1c0012b58  MmMapIoSpaceEx  1c0012b70  STORE  8  0x0
MMIOSUMMARY  calls=1  followed=1  unfollowed=0
```

One mapping call, and the chain is followed. **And the chain's end is
the instrument's limit, which is the point of running it early.** The
bytes:

```
1c0012b58:  call *-0x1aef(%rip)        # MmMapIoSpaceEx
1c0012b64:  mov  %rax,%rcx
1c0012b70:  mov  %rcx,0xd0(%rax,%rbx,8)
```

**The mapped pointer is stored into a global table** at `0x1c000f100`,
offset `0xd0`, indexed by `rbx`. The forward walk correctly stops
there, because continuing requires reasoning about that structure and
its later reloads elsewhere in the driver.

| | |
|---|---|
| **CAN reach** | the call site; the returned pointer; every use in the same function, up to and including the store that parks it |
| **CANNOT reach** | any use *after* the pointer is stored into a global or a struct field and reloaded in another function — which is **exactly what this driver does** |
| **CANNOT reach, restated** | the device. Confirmed separately: the HP trip recorded xHCI `BAR0`; the iron logs return nothing for `i8042` or `keyboard` |

**So the exit's bar is now concrete.** For this driver the attestable
statement is *"the function at `1c0012a70` maps a region at
`1c0012b58` and parks the pointer at `1c0012b70`, offset `0xd0` of a
global table"* — not *"and then writes four bytes at offset `0x10`"*,
because neither instrument can follow the reload without a store/load
model neither has.

**That is a narrower exit than §7 first implied, and it is narrowed
now rather than at the exit.** If the consumer is to make the fuller
statement, a memory-parking model is a **named prerequisite** and its
absence is not something to discover when the exit is claimed.

---

# The census, taken before any pass exists — and it stops the build (2026-09-21)

**§6.1 said the census "decides whether the rest is worth building at
the size the corpus implies". It has decided, and the answer is no at
that size.** This is what a census before a pass is for, and it cost
one afternoon instead of one phase.

## The figure

`docs/evidence/mmio-chain-census-2026-09-21.log`, all eight HP drivers,
the second instrument:

| driver | mapping calls | chain followed | unfollowed | **reaches a real access** | pointer parked |
|---|---|---|---|---|---|
| ACPI | 3 | 3 | 0 | **0** | 3 |
| serial | 2 | 2 | 0 | **0** | 4 |
| HDAudBus | 2 | 2 | 0 | **0** | 2 |
| pci | 2 | 1 | 1 | **0** | 1 |
| i8042prt | 1 | 1 | 0 | **0** | 1 |
| storport | 1 | 0 | 1 | **0** | 0 |
| usbxhci | 1 | 1 | 0 | **0** | 1 |
| disk | 0 | — | — | — | — |
| **total** | **12** | **10** | **2** | **0** | **12** |

> **Zero of twelve mapping calls have a chain reaching an access to the
> mapped region.** ~~All twelve park the pointer into memory instead.~~
> **Corrected 2026-09-21: TEN park the pointer.** Two of the twelve
> stores are one byte from a byte register and cannot be an eight-byte
> base — see the classification below.

**So the consumer as specified would produce zero statements on this
corpus.** Not few — none. The statement §4 promises — *"maps a region
and writes four bytes at offset `0x10`"* — has **no instance** in the
eight drivers, because no driver dereferences a mapped pointer in the
function that maps it.

## The instrument was corrected before the census was banked

**The first run reported 12 "accesses" and would have been wrong.** It
counted any load or store the returned pointer *reached*, which
conflates two different facts:

| the pointer is… | means |
|---|---|
| the **address** of a load/store | **the device is touched here** |
| the **value** being stored | it is **filed into memory**; the device is not touched |

On `i8042prt` the chain ends at `mov %rcx,0xd0(%rax,%rbx,8)` — the
mapped pointer is the **value**, parked into a global table at
`0x1c000f100`. Reporting that as an access would have been a fabricated
claim that a device was driven. The verdicts are now separate
(`MMIOACCESS` / `MMIOPARKED`), and **the corrected count is 0 accesses
and 12 parkings**.

*Caught because the first result — 12 accesses, every one a `STORE`,
every one at offset `0x0` — was too uniform to be real. A number that
tidy is a signature of the instrument, not the data.*

## What this changes

**The prerequisite is no longer optional and is no longer at the end.**
A store/reload model across functions is **the** thing standing between
this corpus and any statement of the specified form. §7.1 named it as a
"named prerequisite" for the fuller statement; the census promotes it
to **the whole of the work**.

**Three options, and the choice is the owner's:**

1. **Build the parking model** — follow a pointer from a mapping call
   into a global or struct slot, then find the reloads of that slot and
   the accesses through them. This is real interprocedural work, and
   the census says it is the *only* path to the specified statement.
2. **Change the exit to what the corpus supports.** A statement of the
   form *"the function at X maps a region and parks it at slot Y"* is
   attestable **today**, for 10 of 12 sites, by the instrument already
   built and run. It is a weaker claim than §4's and an honest one.
3. **Stop here.** The census is itself a product finding: **these
   drivers do not touch hardware where they map it.** That is worth
   knowing and is now measured.

**What I am not doing: writing the pass.** §6.1 made this census the
gate, and the gate says the specified pass has no instances to find.
Building it anyway would produce an empty output and a green test,
which is the exact shape this arc has spent three weeks removing.

**Also measured, and it sharpens the choice:** the two unfollowed sites
(pci `1c0068c44`, storport `1c00381b0`) are refusals the instrument
printed itself — *"return reaches no load or store"* — so even the
weaker statement of option 2 is unavailable for 2 of the 12.

---

# Staged, per the ruling — and the classification changes both stages (2026-09-21)

## Stage 1's revised exit, worded before any code

> For **`i8042prt.sys`**, a per-function statement of the form
> ***"function F at address A maps a region and parks the returned base
> at device-extension slot S"***, attested by `MmioChains.java`, with
> the single call site hand-checked against bytes. **A slot that cannot
> be named prints `offset-unknown` rather than being omitted.**

**And the named driver's only park is in the awkward class, which the
exit must not paper over.** Its site is
`mov %rcx,0xd0(%rax,%rbx,8)` — a **scaled-indexed slot, an array
element, not a fixed field**. The honest statement is *"parked at
displacement `0xd0` of an indexed slot"*; *"parked at offset `0xd0`"*
would overstate it. The driver stays — one call site, hand-checkable,
chosen before the work — and **stage 1 therefore tests the hard path
immediately** instead of earning false confidence on an easy one.

## The twelve parks, classified

Re-read from the banked log and **disassembled**, because the
instrument prints `offset-unknown` for every park: it computes an
offset only for the address role, which is the correct conservatism and
is why the classification had to come from bytes.

| driver | park instruction | class |
|---|---|---|
| ACPI `1c0029e8f` | `mov %rax,(%r14)` | plain, offset `0x0` |
| ACPI `1c00b08e9` | `mov %rax,0x5c(%rsi)` | plain |
| ACPI `1c00b0950` | `mov %rax,0x28(%rsi)` | plain |
| HDAudBus `1c002267d` | `mov %rax,0x58(%rdi)` | plain |
| HDAudBus `1c00226a7` | `mov %rax,0x60(%rdi)` | plain |
| pci `1c0040c05` | `mov %rax,0x10(%rbp)` | plain |
| serial `1c000c720` | `mov %rax,0xe8(%rdi)` | plain |
| serial `1c000c806` | `mov %rax,0xf0(%rdi)` | plain |
| usbxhci `1c006f967` | `mov %rax,0x18(%rbx)` | plain |
| **i8042prt `1c0012b70`** | `mov %rcx,0xd0(%rax,%rbx,8)` | **scaled-indexed** |
| serial `1c000c71a` | `mov %cl,0x262(%rdi)` | **not a park** |
| serial `1c000c800` | `mov %cl,0x263(%rdi)` | **not a park** |

**Two of the twelve are not parks at all.** They store **one byte**
from `%cl`, and a mapped base is eight. They are a derived value — a
success flag, by their placement — that the forward walk reached
through a truncation. So **the real count is 10 parks: 9 plain, 1
scaled-indexed, 0 unjoinable.**

**That is a much better result for stage 2 than the ruling assumed:**
nine of ten join on a constant displacement directly, and the awkward
one is the named driver's. *And it is a third instrument artefact
caught by reading bytes — the first was the address/value conflation,
the second the tidy `offset 0x0`, this the size-1 stores.*

## Stage 2's census, taken before stage 2's code

**By the rule that just paid for itself.** Join: for each park
displacement, count loads from that displacement, and of those, how
many feed a memory dereference within a short window. Padding `nop`s
and `lea` are excluded — `lea` computes an address without touching
memory, and a padding `nop` with a memory operand is not an access.

| driver | slot | loads | reach a dereference |
|---|---|---|---|
| ACPI | `0x0` | 1,305 | 604 |
| ACPI | `0x28` | 581 | 212 |
| usbxhci | `0x18` | 514 | 55 |
| pci | `0x10` | 260 | 70 |
| HDAudBus | `0x58` | 213 | 108 |
| serial | `0xe8` | 155 | 122 |
| HDAudBus | `0x60` | 61 | 1 |
| **i8042prt** | **`0xd0`** | **9** | **0** |
| ACPI | `0x5c` | 5 | 0 |
| serial | `0xf0` | 5 | 2 |
| **total** | | **3,108** | **1,174** |

**Stage 2 does not die: 1,174 is not zero.** But **the figure is a
ceiling with a measured false-positive class**, and the measurement is
on the named driver.

**`i8042prt`'s `0xd0` is loaded nine times. Eight are
`mov 0xd0(%rcx),%rcx` — plain, a DIFFERENT structure that merely shares
the displacement.** Only one, `mov 0xd0(%r8,%rbx,8),%rcx` at
`1c0013a2b`, matches the park's actual scaled-indexed form, and it
reaches no dereference within 24 instructions. So on this driver the
displacement-only join is **8 false positives and 1 true candidate that
goes nowhere**.

**That is exactly the weakness the ruling predicted for the
scaled-indexed class**, and it is now measured rather than anticipated.
For the nine plain slots the join is on a constant against a constant
and is far stronger; for the indexed one it is displacement-only and
demonstrably noisy.

## What stage 2 needs, stated now

**A base-register identity check**, not a wider window: the join must
know that the register holding the loaded value came from the *device
extension*, not from any structure sharing an offset. That is a
smaller thing than general store-and-reload modelling — the ruling was
right — but it is **not free**, and the 1,174 must not be quoted as a
finding until it is applied.

**Stage 2 is scoped, not started.** Its own exit and its own red come
before its code, as stage 1's did.

---

# The identity check run early, the window retired, and the count corrected (2026-09-21)

## 1. The named exit driver passes stage 1 and yields nothing at stage 2

**Run now rather than at stage 2's gate, and the risk was real.**

The park is `mov %rcx,0xd0(%rax,%rbx,8)`, and `%rax` comes from
`mov -0x3a70(%rip),%rax` — **the global at `0x1c000f100`**. So the join
key is that global, scaled by `%rbx*8`, displacement `0xd0`.

Of the **9** loads at displacement `0xd0` in this driver, **8 fail the
identity check**: they are `0xd0(%rcx)` or `0xd0(%rax)`, unscaled, and
their bases trace back to `0xd8(%rcx)` and `0x40(%rcx)` chains — **a
different structure that merely shares the number**.

**Exactly one passes**, at `1c0013a2b`:

```
1c0013a1c:  mov  -0x4923(%rip),%r8      # 0x1c000f100   <- the SAME global
1c0013a23:  xor  %ebx,%ebx
1c0013a25:  cmp  %ebx,0x40(%r8)                          <- loop bound
1c0013a2b:  mov  0xd0(%r8,%rbx,8),%rcx                    <- the reload
1c0013a3c:  call *-0x2923(%rip)         # 0x1c0011120
```

**Same global, same scale, same displacement — a true reload.** And
what it reaches is a **call**, with the base as the first argument.
That slot has **exactly one call site in the whole driver**, and the
function containing it (`0x1c00139d0`) is the one the report says calls
**`MmUnmapIoSpace`** — the driver's only other `Mm*` import.

> **`i8042prt` maps a region, parks the base in a global table, and the
> only correctly-joined reload passes it straight to `MmUnmapIoSpace`.
> It never dereferences the mapped region at all.**

**So the named exit driver passes stage 1 and yields nothing at stage
2 — and not because the analysis is too weak. Because the driver does
not do it.** That is the second-instrument catch's shape exactly, and
the census discipline surfaced it before the work rather than at the
gate.

**This is a ruling the owner owns**, and the options are stated rather
than chosen:

- **Keep `i8042prt` for stage 1 and name a different driver for stage
  2.** Stage 1's exit is about parking and this driver parks; stage 2
  needs a driver that dereferences. The census says which do.
- **Move both stages to one driver that does both.** `serial`
  (`0xe8`, 122 candidate derefs) and `HDAudBus` (`0x58`, 108) are the
  strongest candidates, and both park at a **plain** displacement,
  which loses the hard-path property that made `i8042prt` a good
  stage-1 subject.
- **Keep `i8042prt` for both and accept that stage 2's exit is "no
  accesses, and here is why"** — a true statement, attested, and a
  weaker deliverable.

## 2. The window was an undeclared knob. It is retired, not tuned

**Provenance, stated plainly: there is none.** I picked 8, then 24, to
see whether the answer moved. **A knob with no provenance moving a
finding is exactly what the alias table is hashed to prevent**, and
this one was worse than unhashed — it was invented mid-measurement.

**Replaced by liveness**, which is a property of the program rather
than a number I chose: the scan stops when the destination register is
**overwritten**, or when a **call** clobbers it. Both are facts about
the code.

| bound | dereferences found |
|---|---|
| window 8 | 900 |
| window 24 | 925 |
| window 48 | 933 |
| window 128 | 935 |
| **liveness** | **935** |

**The answer is window-independent once liveness bounds it** — 935 is
the asymptote, reached by 128 and equalled exactly by liveness.

**And the earlier figure was inflated.** The 1,174 reported last round
did **not** stop at overwrites or calls, so it counted dereferences of
registers whose value had already been destroyed. **The honest figure
is 935, which is 239 lower.** The larger number is withdrawn.

**On the named driver, liveness settles it in three instructions**: the
reload at `1c0013a2b` is consumed by the call at `1c0013a3c`, and a
call clobbers `%rcx`. No window of any size changes that.

## 3. The count is ten, not twelve

**Corrected wherever it was carried**, by the seventeenth rule — a
corrected source does not refresh the figures derived from it:

- **12 mapping calls** — unchanged, that figure was always right.
- **~~12 parks~~ → 10 parks.** Two of the twelve store one byte from a
  byte register and cannot be an eight-byte base.
- **9 plain + 1 scaled-indexed + 0 unjoinable**, summing to 10.

**Still a ceiling, and the reason is now measured.** 935 is a
**displacement-only** join. On the one driver where the identity check
has been applied it removed **8 of 9** candidates. Until that check is
applied corpus-wide, **935 is an upper bound with a measured
false-positive rate of ~89% on its single tested site**, and it is not
quotable as a finding.

---

# The identity check applied corpus-wide — and it withdraws my own correction (2026-09-21)

## First: the "8 of 9 false positives" claim is WITHDRAWN. It was my bug

**Last round I reported that eight of the nine loads at `i8042prt`'s
`0xd0` failed the identity check, reading "a different structure that
merely shares the number", and quoted an ~89% false-positive rate. That
was wrong, and the cause was a defect in my own tracer.**

`objdump` appends a comment to a RIP-relative operand:

```
mov 0xa625(%rip),%rcx        # 0x1c000f100
```

My backward trace matched the setter with `,%r[a-z0-9]+$` **against the
whole operand string including the comment**, so it never matched a
RIP-relative load. It skipped past every one of them and reported the
next-older setter instead — which is where `0xd8(%rcx)` and
`0x40(%rcx)` came from. Those instructions are real; they are simply
**not** the setters.

**Corrected: all nine loads at `0xd0` read the same global,
`0x1c000f100`.** The identity check keeps **9 of 9**, not 1 of 9.

**This is the fourth appeal-to-the-bytes instance, and the first
against a correction rather than an original claim.** The tell was the
same as before: my first corpus-wide run classified **all ten** parks
as `PARAM`, which is too uniform to be real when one of them was
already known to be a global.

## The i8042prt conclusion stands, and is now stronger

With the identity check keeping all nine loads, **none of the nine
reaches a dereference before its register dies**. Eight read the array's
first element unscaled (`0xd0(%rcx)`), one reads element `%rbx`
(`0xd0(%r8,%rbx,8)`), and the one that is followed goes to the unmapper.

> **`i8042prt` maps a region, parks the base, and no identity-checked
> load of that slot ever dereferences it.** Nine loads, not one —
> a stronger negative than last round's, and reached by a fixed
> instrument.

**And the ruling's explanation is confirmed by the bytes.** This driver
drives a port-mapped device; finding (z) measured its real traffic as
DX-addressed port instructions. The mapping call is a resource claimed
and released. **The driver was chosen against a mapping-call criterion
while its device access is port-based** — good reasons, wrong axis.

## Part 3: the identity check corpus-wide. 935 loses the word "ceiling"

| driver | slot | base class | loads | identity-checked | dereference |
|---|---|---|---|---|---|
| HDAudBus | `0x58` | param | 213 | 172 | **83** |
| ACPI | `0x28` | param | 581 | 215 | **78** |
| serial | `0xe8` | param | 155 | 116 | **53** |
| pci | `0x10` | param | 260 | 114 | **23** |
| usbxhci | `0x18` | param | 514 | 186 | **17** |
| ACPI | `0x0` | stack | 1,305 | 9 | **5** |
| HDAudBus | `0x60` | param | 61 | 46 | 0 |
| serial | `0xf0` | param | 5 | 4 | 0 |
| ACPI | `0x5c` | stack | 5 | 2 | 0 |
| i8042prt | `0xd0` | **global** | 9 | 9 | 0 |
| **total** | | | **3,108** | **873** | **259** |

**The identity check removes 72% of the loads (3,108 → 873) and 72% of
the dereferences (935 → 259).** The false positives were real and
large; only my single-site *rate* was wrong.

> **259 is a number, not a ceiling.** Every load counted has been
> traced to a base with the same provenance as its park's base.

**What it still is not:** for the seven `param` slots, "same
provenance" means *both bases are an incoming parameter of their own
function* — it does **not** prove the same object. That is the residual
interprocedural gap, named rather than hidden. Only `i8042prt`'s global
slot is proven to the same storage, and it is the one with no accesses.

## Part 2: stage 2's driver, selected by measurement

**`HDAudBus.sys`, slot `0x58` — 83 identity-checked dereferences**,
the most of any slot, and hand-checked:

```
1c00027dd:  mov    0x58(%rsi),%rax        <- reload of the parked base
1c00027e1:  movzbl 0x3(%rax),%ecx         <- reads ONE byte at offset 0x3
1c00027e5:  mov    0x58(%rsi),%rax
1c00027e9:  movzbl 0x2(%rax),%eax         <- reads ONE byte at offset 0x2
1c0002803:  mov    0x58(%rsi),%rax
1c0002807:  mov    0x24(%rax),%eax        <- reads FOUR bytes at offset 0x24
```

**That is the specification's own sentence, in bytes:** *"reads one
byte at offset `0x3`, one at `0x2`, four at `0x24`."* Stage 2 has a
subject.

**Runner-up, and worth keeping as the control:** ACPI `0x28`, 78
dereferences, a different driver and a different structure.

## And stage 2 is not dead corpus-wide

The gate the ruling set — *"if no driver survives with real accesses,
stage 2 is dead"* — **does not fire**. Six of the ten slots survive
with at least one identity-checked dereference, and the top one has 83
that a person can read.

---

# The 259 split, and stage 2's exit bounded to the proven class (2026-09-21)

## The split, and my hand-checked example was in the weak class

**Function boundaries from the pinned oracle** (`FuncRanges.java`,
Ghidra 12.1.2), joined against the identity-checked dereferences:

| driver | slot | dereferences | **same-function (proven)** | cross-function |
|---|---|---|---|---|
| **HDAudBus** | `0x58` | 83 | **13** | 70 |
| ACPI | `0x28` | 78 | 0 | 78 |
| serial | `0xe8` | 53 | 0 | 53 |
| pci | `0x10` | 23 | 0 | 23 |
| usbxhci | `0x18` | 17 | 0 | 17 |
| ACPI | `0x0` | 5 | 0 | 5 |
| **total** | | **259** | **13** | **246** |

> **13 proven, 246 joined by displacement plus a parameter-provenance
> type hint.**

**And the instance I hand-checked last round was one of the 246.** The
park is in function `1c0022510`; my example at `1c00027dd` is in
`1c0002760` — **a different function**. It reads
`0x58(%rsi)` where the park wrote `0x58(%rdi)`, and "both bases are an
incoming parameter" is satisfied by two different device extensions
passed to two different functions. **The owner's item 1 was exactly
right, and the example was in the weak class.**

## The proven class exists, and it is a better subject

**All 13 are in `HDAudBus`, and all are in the same function as the
park** — `1c0022510`, which both maps and accesses:

```
1c002267d:  mov    %rax,0x58(%rdi)      <- the park
1c00226de:  mov    0x58(%rdi),%rax      <- reload, SAME function, SAME register
1c00226e2:  movzwl (%rax),%r8d          <- reads TWO bytes at offset 0x0
1c002284a:  mov    0x58(%rdi),%rax
1c0022865:  movzbl 0x3(%rax),%edx       <- reads ONE byte at offset 0x3
1c0022869:  mov    0x58(%rdi),%rax
1c002286d:  movzbl 0x2(%rax),%eax       <- reads ONE byte at offset 0x2
```

**Park and access in one function, one register lineage, both visible.**
No interprocedural assumption is needed, which is what makes these 13
proven where the 246 are not.

## Stage 2's exit, bounded

> **Stage 2 is done when it produces, for `HDAudBus.sys` function
> `1c0022510`, per-access statements of the form *"reads N bytes at
> offset X of the region mapped at `1c0022671` and parked at `0x58`"*,
> for the SAME-FUNCTION class only, attested by `MmioChains.java` and
> `FuncRanges.java`, with at least one instance hand-checked against
> bytes.**
>
> **Cross-function candidates are reported with
> `provenance: not proven`** — same displacement, same parameter class,
> different function — **and still pass**, exactly as the DX-addressed
> ruling allowed a followed chain without a resolved number.
>
> **The count 83 is not claimed. 13 is.**

**This is the same presence-versus-identity distinction (z) forced on
the port signal**, one layer up: a port operation had to be attested by
both instruments before it could be emitted, and a dereference has to
be attested to the same object before it can be claimed.

## What the split costs and what it buys

**Costs:** stage 2's headline drops from 259 to 13, and from 83 to 13
on its own driver.

**Buys:** every one of the 13 is checkable by a person reading one
function, and none of them rests on an assumption about two device
extensions being the same object. **Against "0 of 320", thirteen proven
instruction-derived accesses is the first positive entry of any size.**

---

# The base register checked, and my checker was wrong twice (2026-09-21)

## 1. Same register name is not same value — measured, and it holds

**The claim "one register lineage" was an ABI assumption dressed as an
observation.** `%rdi` is callee-saved on Win64, which makes it likely,
not proven. Checked directly:

| | |
|---|---|
| reloads of `0x58(%rdi)` in the park function | **13** |
| **bare writes to the `rdi` family** (`%rdi`/`%edi`/`%di`/`%dil`) between the park and the last reload | **0** |
| calls in that span | 27 |
| **reloads whose base is proven unwritten since the park** | **13 of 13** |

**Two independent grounds, and they are different in kind.** The *code*
claim is measured: this function never writes the register. The *ABI*
claim covers the 27 intervening calls and is a **cited convention**
(`%rdi` is non-volatile on Win64), not a measurement. Both are stated;
neither is presented as the other.

## And my checker was wrong twice, the same way

**First:** it matched writes with `,%rdi$` — **only the 64-bit name**.
Writing `%edi` zeroes the upper half and therefore writes `%rdi`, so
the first check could not have seen a whole class of writes.

**Second, after widening to the family:** it reported **2 writes**,
`xchg %eax,0x100(%rdi)` and `xchg %eax,0x104(%rdi)`. **Neither writes
`%rdi`** — in both, `%rdi` is a **memory base**, and the exchange is
between `%eax` and memory. My rule was `'di' in ops`, a **text match
where a value was meant**, which is the identical error to the
`,%reg$`-against-a-comment bug that withdrew the last correction.

**That is the fifth instance, and it was in the checking script rather
than the instrument.** Fixed by splitting operands on commas *outside
parentheses* and requiring a **bare** register in a writing position.
The corrected count is 0 writes, and the 13 stand.

## 2. The exit says one park, one function, one driver

**Reworded, because "13 proven" read alone overstates the
independent-sample count, which is one:**

> **Stage 2 is done when it produces 13 accesses through 1 park in 1
> function of 1 driver** — `HDAudBus.sys` function `1c0022510`, park
> `1c002267d` at `0x58` — as per-access statements *"reads N bytes at
> offset X"*, attested by `MmioChains.java` and `FuncRanges.java`, with
> at least one hand-checked against bytes.

**Never "13 proven" standing alone.** A reader six months out would
take that as thirteen confirmations, and it is thirteen dereferences of
one pointer in one place. It is still the first positive entry against
0 of 320, and it does not need inflating to be that.

## 3. The offset-0 access here is genuine, and that is noted deliberately

`1c00226e2: movzwl (%rax),%r8d` reads **two bytes at offset 0x0**, and
it sits beside `movzbl 0x3(%rax)` and `movzbl 0x2(%rax)`.

**"Every one at offset zero" was the tell of an earlier instrument
defect** — the chain walker's offset extraction handled only a simple
constant add and printed `0x0` for everything. **This is not that.**
Offset 0 appears here alongside 0x2 and 0x3 in the same register
window, from bytes a person can read, and a mapped region's first word
is an ordinary thing to read. Recorded so a later reader does not
mistake a real zero for the old artefact.

---

# Stage 1's red, written before its code (2026-09-21)

**`tests/test_mmio_consumer.c`, wired into `test-all` as
`test-mmio-consumer`. 27 suites, 0 warnings, exit 0.**

**The red is on the TYPE, and that is deliberate.** `sem_function_t`
has no mapped-region record — `grep` for `mmio_region`,
`mapped_region`, `park` over `include/semantic.h` returns nothing — so
the failure message is:

> *"`sem_function_t` carries no mapped-region record: the analysis has
> nowhere to say which region a function maps or where it parks the
> base, so it cannot make the statement stage 1 requires."*

**A statement the record cannot hold is a statement the analysis cannot
make.** Putting the red there means it cannot pass by accident, and the
pass state behind `#ifdef SEM_HAS_MAPPED_REGION` names every field the
exit requires: call site, park site, displacement, and **whether the
park is indexed** — because reporting `i8042prt`'s as a plain offset
would overstate it.

**The expected values are held as constants, from the census and
hand-checked against bytes:** function `1c0012a70`, call `1c0012b58`,
park `1c0012b70`, displacement `0xd0`, indexed. The test names what it
wants rather than asking whether some field is non-empty.

## And the parsing contract absorbed the sixth defect

**The role parser now lives in `scripts/objdump_screen.py`**, not in
the next ad-hoc script. `writes_register`, `reads_register_as_memory_
base`, `split_operands`, `canonical_register` — answering the *role*
question that six substring tests stood in for.

**It carries a self-test built from the six defects themselves**, so
the contract is tested by the errors that produced it: `xchg
%eax,0x100(%rdi)` must not write `%rdi`, a write to `%edi` must write
`%rdi`, a RIP-relative load with an objdump comment must still be seen
to write its destination. **10 cases, 0 failures**, run inside
`test-shipped-binary` beside the other two self-tests.

*The contract hash changed to `41e0da34717c`, which is the point of
hashing it.*

## On the six, since the count reads badly alone

**Six artefacts in one afternoon is a high defect rate for throwaway
analysis scripts.** All six were caught, **none shipped**, and every
one was caught the same two ways: by going to the bytes, or by a
uniformity tell. The rate is a fact about writing one-off scripts under
time pressure. The catch rate is a fact about the method, and it is the
one that decides whether the output can be trusted.

**And the sixth is now structurally harder to repeat**, because the
seventh would have to be written against a contract that already
answers the question correctly.

---

# The register check widened to the union (2026-09-21)

**Two reds outside the check within a day is a pattern, not an
exception**, and it is exactly the condition the trap-row work exists
to prevent: a list checked by nothing.

**Fixed with the machinery that exists.** The check now parses
`xfail_names[]` out of **every** `tests/test_*.c` that carries one and
asserts the register against the **union**. It reports
`(15 reds across 5 suites)` and the suite count is asserted, so a
renamed or deleted suite cannot shrink the union silently. The register
table gained a `suite` column and **no red is carried in prose any
more**.

**Control run:** unregistering `(aj)` in `test_mmio_consumer.c` makes
the decoder suite fail with *"register lists
`aj_report_names_the_mapped_region_and_its_park`, which no suite
registers"*. **The check now sees across files**, which it could not
before. Restored, green.

## Three parser defects on the way, all the same shape

| the parser did | the bug |
|---|---|
| took every quoted string in the block | comments quote things; it reported a missing red named `(s)`, which is a **defect letter in a comment** |
| assumed the array spans several lines | `xfail_names[] = { NULL };` **opens and closes on one line**; skipping the rest of that line ran the parser into the file body, where it collected `rb` from an `fopen` mode string |
| — | fixed by requiring a **C identifier** and by scanning from just after the opening brace |

**Seventh and eighth instances of matching text where a value is
meant**, both caught by the check's own output naming the nonsense it
had collected — `"(s)"` and `"rb"` are not test names, and a parser
that reports them is telling you what it actually matched.

*The role parser added to the contract earlier today does not cover
this case — it parses **operands**, not C source — so these two are not
a failure of that remedy. They are the same error class in a different
medium, which is worth recording rather than glossing.*

**27 suites, 0 warnings, exit 0 from a clean build.**

---

# Two assertions the suite could not make about itself (2026-09-21)

## 1. The test total is now asserted, and it caught the deliberate removal

**Nothing asserted the pass side.** The arc fixed the *xfail* side long
ago — a registered name with no test behind it used to print `38/38`
silently — but **deleting a passing test still printed "All tests
passed"**. A scripted edit removed two tests today and a person caught
it from the compiler's errors, not a check. Scripted source edits are
routine here, so the risk was live.

**`scripts/suite_census.py`**, first in `test-all`, against a committed
baseline (`tests/suite_census.tsv`): **381 tests across 27 suites**. A
count that **falls** fails and names the suite; a count that **rises**
updates with `make suite-census-update` and the rise is visible in the
diff.

**Control, run before anything was rebaselined:** deleting one test by
a scripted edit gives

```
TESTS LOST: test_uir.c 26 -> 25
test totals: 381 across 27 suites (baseline 382)
```

**And it immediately caught a real one** — moving the register check
out of the decoder suite dropped that suite 112 → 111, reported by
name, and the baseline was updated deliberately rather than drifting.

## 2. One C-source contract, after eight instances

**Three consumers, three hand-rolled parsers**: the register union
check, the rule-30 sweep, and the `xfail_names[]` reader. That is the
same argument that produced `objdump_screen.py` after **two**
instances. This was **eight**.

**`scripts/c_source.py`** is the contract: `strip_comments` (leaving
string literals and line numbers intact), `initialiser_body`
(brace-counted, so a one-line array and a nested one both work),
`string_literals`, `identifiers`, `registered_xfails`,
`test_macro_names`. **It carries a self-test built from the three
defects that produced it** — 6 cases, 0 failures — and its hash is
printed by every consumer.

**All three consumers now use it.** The register check moved out of
`test_x86_decoder.c` entirely, so there is no longer a C parser reading
C source; `rule30_sweep.py` uses `registered_xfails` in place of its own
`split('xfail_names[] = {')`, which would have taken quoted prose from
a comment as a registered name exactly as the register check did.

**Four self-tests now run inside the suite**: the shipped-binary
checks (7 cases), the denominator refusals (3), the operand roles (10),
and the C-source contract (6). **Each built from the defects that
produced its module.**

**27 suites, 0 warnings, exit 0 from a clean build.**

---

# Stage 1 built and green, and the rebaseline bypass closed (2026-09-22)

## The census cannot be laundered

**`--update` refuses a decrease.** Rebaselining is the tempting
resolution the moment the check fires, and it is the same shape as
loosening a threshold, which rule 33 refused: it makes the instrument
agree with the defect instead of reporting it.

> **A census drop is never resolved by rebaselining; only a rise is.**

**Controlled:** a scripted deletion of one test gives

```
REFUSED: test_uir.c would drop 26 -> 25
A census drop is never resolved by rebaselining.  Tests were lost:
explain or restore them.  If the loss is deliberate, re-run with
--allow-loss, which records it in the baseline so the path taken is
visible.
```

**`--allow-loss` writes the override into the baseline file** —
`# LOSS ALLOWED 2026-09-22: test_uir.c 26 -> 25` — so the laundering
path is visible in the diff whenever it is taken, and it clears on the
next honest update.

## Stage 1 is green, and the report has its first instruction-derived field

```json
"mapped_regions_analysed": true,
"mapped_regions": [
  { "api": "MmMapIoSpaceEx",
    "call_site": "0x1C0012B58",
    "park_site": "0x1C0012B70",
    "park_indexed_displacement": "0xD0" }
]
```

**Every value matches the census and the hand-check byte for byte.**
The test asserts the **key name** as well as the value, because this
park is `mov %rcx,0xd0(%rax,%rbx,8)` — a scaled-indexed array element —
so `park_offset` would overstate it. Asserting the key is what stops
the weaker statement passing as the stronger one.

**It is asserted end to end through the shipped path**, on the report a
reader actually sees, not on an internal struct.

**Two defects in the first implementation, both found by running it:**

| the pass did | why it was wrong |
|---|---|
| looked for a store whose source is the **return register** | the return is **copied first** (`mov %rax,%rcx`), so it reported *"not stored"* — **false**, it is stored through one copy |
| stopped at the end of the call's **basic block** | the park sits **past** that boundary |

Both are now handled: a small def-use set follows the value through
register copies, and the walk continues in program order.

**Gate: exactly one name**, `test_mmio_consumer` back to an empty
expected-failure list. **27 suites, 0 warnings, exit 0 from a clean
build**, census 381 across 27, register union matching at 14 reds.

## House style, named because it arrived by accumulation

**Every instrument carries a regression suite made of its own
history.** Four now run inside the suite, each built from the defects
that produced its module:

| self-test | cases | built from |
|---|---|---|
| shipped-binary checks | 7 | a mixed link, a skip that read as a pass, a stale ratio |
| denominator refusals | 3 | a missing input, an input yielding zero |
| operand roles | 10 | six instances of matching text where a value was meant |
| C-source contract | 6 | quoted prose in a comment, a one-line initialiser, a non-identifier literal |

**It arrived by accumulation rather than decree**, which is why it
stuck: each was written the hour its module's defect was found, not
from a policy.
