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
