# Stage 2 of the identity consumer: pre-registration (2026-09-23)

**Written before stage 2's code.** Outcomes go BELOW the line.

**What this run tests, per the owner's ruling.** The 14 targets in
`stage2-row-targets-prereg-2026-09-23.md` were read from the bytes by hand
while the product could vouch for none of them, and banked before (p),
(ba) and (bb) existed. Nothing could have shaped them to what the
instrument now produces. So this is **a test of the hand read as a method**,
not only of the rows:
- **Agreement** establishes hand reading as a reliable source of targets
  the product cannot yet produce.
- **Disagreement is the more valuable case and is not smoothed.** If a row
  differs, one of the two is wrong. The bytes are read again before
  either is touched. **No banked target is adjusted to match the product,
  and the product is not assumed right because it is now capable.**

## The exit (ruled 2026-09-23)

> **14 accesses through 1 park**, stated as an **exact set**, and never
> without **independent sample count 1**: one pointer, one park, one
> function, one driver. `HDAudBus.sys` (sha256 `9966d998035daae0…`),
> function `1c0022510`, region mapped at `1c0022671`, parked at `1c002267d`
> `mov %rax,0x58(%rdi)`. Each access is a per-access statement, *"reads N
> bytes at offset X of the region mapped at `0x1C0022671` and parked at
> `0x58`"*.

**Attestation, stated exactly:**
- The pinned oracle's `MmioChains.java` attests the **region and its
  park** (`mmio-chain-census-2026-09-21.log`:
  `MMIOPARKED 1c0022510 1c0022671 … 1c002267d`). Its forward flow ends
  where the pointer is filed, so it attests **no access**.
- `FuncRanges.java` and `.pdata` attest the function boundary.
- **The 14 accesses rest on the hand read alone**, which is what this run
  tests.

## What stage 2 does (the rules the bound fixed before any code)

For a region parked in a **plain structure slot**, meaning not indexed and
not a frame slot, with base register P and displacement D:

1. **Continue the walk after the park**, in address order to the end of the
   product's function.
   - P stays live while nothing writes it. That is read from
     `uir_writes()`, as the park walk reads it.
   - A CALL leaves P live when P is non-volatile under the Win64 ABI.
     This is a cited convention, not a measurement, as recorded in the
     consumer spec.
   - **An instruction whose writes the UIR does not show stops the walk**.
     Every later reload is then undetermined, and the report says where
     (`accesses_undetermined_at`).
2. **A reload** is a load `mov D(P),R` (no index) while P is live.
3. **Its access** is the first instruction after the reload that uses R as
   a memory base. The search stops if R is written first, if a CALL, JMP
   or RET intervenes, or at the function end.
   - An unseen instruction in that span makes the access undetermined,
     reported per reload.
   - `lea` is not an access. It computes an address and touches nothing.
4. **Size and offset** come from the memory operand. **Route** is
   `address_order` if a JMP or RET was crossed between the park and the
   access, and `path` otherwise.

**Report, per region:** `accesses_analysed: true` (zero-measured must not
print as zero-found), and `accesses: [{reload, reg, access, kind, size,
offset, route, statement}]`. The regions of all drivers get these fields.
Stage 2's exit is about the one region above.

## Predictions

| # | prediction |
|---|---|
| T1 | the red `stage2_RED_hdaudbus_14_accesses` XPASSes. The `0x58` region's `accesses` list is **exactly** the 14 banked rows, matched on (reload, reg, access, size, offset) and in the same order, and there is **no** `accesses_undetermined_at` for it. All 14 are reads |
| T2 | **nothing else moves** in any existing test or measurement: park outcomes identical on all four machines (stage 2 adds fields and changes no park); `-t uir` and the differential byte-identical (lifter and decoder untouched); suites green with **tests +1**, and 13 reds → 12 |
| T3 | the second region in the same function (mapped at `1c0022697`, parked at `1c00226a7`) is **reported as observed, with no prediction**. It is not part of the exit |
| T4 | the route of each of the 14 is reported as observed, with no prediction. The hand read went in address order, and a `path` label is not claimed in advance |

**If T1 fails on any row, the row is listed with both versions, and the
bytes are read again before anything else is done.** The outcome is stated
as an exact set either way, with independent sample count 1.

---

## Outcome

*(below this line, from the artefact only)*

**Inputs hashed:** `semantic.c` `29340274786ac3a0`, `semantic.h`
`8f30e90fb58f6ec7`, `bin/translator` `e596b360c4f2eb27`, and `HDAudBus.sys`
sha256 `9966d998035daae0…` (unchanged). The banked targets file was not
edited; its last commit precedes this run.

### The result, as an exact set

**Stage 2 produces 14 accesses through 1 park, and they are exactly the
14 banked rows, matched on reload, register, access, size and offset, in
the same order, with nothing extra and no undetermined marker. Independent
sample count: 1.** One pointer, one park, one function, one driver.

| # | reload | reg | access | statement | route |
|---|---|---|---|---|---|
| 1 | `1C00226A3` | rcx | `1C00226D2` | reads 4 bytes at offset 0x8 | path |
| 2 | `1C00226DE` | rax | `1C00226E2` | reads 2 bytes at offset 0x0 | path |
| 3 | `1C00226E6` | rax | `1C00226EA` | reads 2 bytes at offset 0x0 | path |
| 4 | `1C00226ED` | rax | `1C00226F1` | reads 2 bytes at offset 0x0 | path |
| 5 | `1C00227CC` | rax | `1C00227D0` | reads 2 bytes at offset 0x0 | address_order |
| 6 | `1C002284A` | rax | `1C0022865` | reads 1 byte at offset 0x3 | address_order |
| 7 | `1C0022869` | rax | `1C002286D` | reads 1 byte at offset 0x2 | address_order |
| 8 | `1C002297D` | rax | `1C0022981` | reads 2 bytes at offset 0x0 | address_order |
| 9 | `1C0022984` | rax | `1C0022994` | reads 2 bytes at offset 0x0 | address_order |
| 10 | `1C0022997` | rax | `1C00229A4` | reads 2 bytes at offset 0x0 | address_order |
| 11 | `1C0022BFE` | rax | `1C0022C02` | reads 2 bytes at offset 0x14 | address_order |
| 12 | `1C0022C79` | rax | `1C0022C7D` | reads 2 bytes at offset 0x0 | address_order |
| 13 | `1C0022CB9` | rcx | `1C0022CBD` | reads 2 bytes at offset 0x4 | address_order |
| 14 | `1C0022D0B` | rcx | `1C0022D0F` | reads 2 bytes at offset 0x6 | address_order |

Every statement continues "…of the region mapped at 0x1C0022671 and
parked at 0x58".

### The first run disagreed, and the defect was mine, in the pass

**The first build reported 0 accesses and `accesses_undetermined_at:
0x1C0022697`.** Per the ruling, both sides were read before either was
touched:
- **The bytes at `1c0022697`** are `48 FF 15 …`, which is `rex.W call
  *…(%rip)`, the second `MmMapIoSpaceEx` call, and the product's own report
  names it as that region's call site. It is not an instruction the product
  cannot see.
- **The source:** `uir_writes()` answers *unseen* for every CALL
  (`uir.c:876`, "the callee writes what it likes"). The park walk never asks
  it about a CALL: it applies the Win64 ABI rule and continues. **My stage-2
  loop asked it**, which contradicts the rule this pre-registration states
  ("a CALL leaves P live when P is non-volatile").

**So the pass did not implement its own pre-registered rule.** The fix
makes the CALL follow the ABI, as the park walk does. The re-run matches all
14 banked rows, and **no target was edited**. The row set was never in
question: the first run disagreed on a mechanism the bytes showed was
misapplied, not on any row.

### The predictions

| # | predicted | observed |
|---|---|---|
| T1 | the red XPASSes; exactly the 14 banked rows in order; no undetermined marker; all reads | **held on the second build**: the gate fired on exactly `stage2_RED_hdaudbus_14_accesses`, and all 14 are reads. The first build failed it, as recorded above |
| T2 | nothing else moves | **held**: park census 0 outcome changes over all 539 sites (identical site set); `-t uir` byte-identical on 12 of 12 inputs; `dump_starts` byte-identical on all 16 differential inputs; 406 tests across 27 suites (+1), 12 reds |
| T3 | the second region: observed only | the `0x60` region (mapped `1c0022697`, parked `1c00226a7`) walks to the function's end with **0** same-function accesses and no stop. That is consistent with the consumer spec's census, where all of this function's proven dereferences were at `0x58` |
| T4 | routes: observed only | rows 1–4 **path**; rows 5–14 **address order**, reached past a JMP or RET in address order, as the hand read went. The `path` label is not claimed for them |

**What this establishes about the method.** Fourteen accesses read from
the bytes by a person, at a time when the product could vouch for none of
them, came back exactly from an instrument built afterwards. The instrument
reads the bytes independently of the hand read, through the decoder, lifter
and walk. **The hand read held on every row.** That is what made (p), (ba)
and (bb) buildable against targets. It is one agreement, on one function
of one driver, and it is claimed as nothing more.

**Wording fixed after the gate, asserted by no test:** the statement read
"reads 1 bytes" and now reads "reads 1 byte".
