# Where does a function end? A grounded extent, measured before any fix: pre-registration (2026-09-24)

**Written before the run.** Owner ruling, 2026-09-24. These three items are
one problem: (bn)'s 363 fall-through functions, (bp)'s unreachable region,
and the convergence gap (94.32% against the oracle's 98.97%). **The product's
idea of where a function begins and ends is not grounded.** The residual 363
are *reachable* within the linear extent the product assigned them; the
reachability isn't wrong, the extent is. So measure extent before designing
anything. **No code in this step.** Outcomes go BELOW the line.

## How the product ends a function today (read from source)

`sem_discover_functions()`: a function runs from its entry up to **the next
entry point**, whatever that is (an export, a `.pdata` start, a call target
since (bm), a prologue, the text base). **The `.pdata` end address is parsed
and discarded:** `pe_loader.c:164` stores `end_rva`, and `translator.c:1013`
uses only `start_rva`. Nothing ends a function at a `ret`, at padding, or at
bytes the decoder cannot read.

## Candidate end rules, each measured on its own

For every port-fact function the current build (`adcbf3c1…`) keeps (**553**),
the cut is where the rule would end the function:

| rule | cut |
|---|---|
| **P** `.pdata` | if the entry is a `.pdata` BeginAddress, its EndAddress (the primary range only; chained unwind entries are not followed). Otherwise **undetermined** |
| **D** padding | the first `0xCC` byte (`int3`, MSVC's inter-function padding) immediately after an unconditional `ret` or `jmp`, read from the raw bytes (the UIR lifts `int3` as `unknown`, so it cannot tell padding from undecodable bytes) |
| **U** undecodable | the first UIR instruction the decoder refused (`unknown` or `invalid`) whose bytes are **not** `0xCC` |

**Scoring**, with the Ghidra labels still the key. A kept port site survives
a rule if it lies **before** the cut. A function is **resolved** by a rule if
none of its kept giving sites survive.
- A resolved **unattested** function is the rule catching the residual.
- A resolved **attested** function is a false negative.

Also reported: whether each rule ends RTKVHD64's `0x160260` before `0x1619f7`,
which is (bp)'s region.

## Predictions

The populations are 553 port-fact functions: 191 attested (100 of them
ClipSp, which is not real) and 362 unattested.

| # | prediction |
|---|---|
| X1 | the share of port-fact functions whose entry is a `.pdata` start: **60%** (40–80%) |
| X2 | **P** resolves **50%** of the unattested and loses **≤ 3** attested outside ClipSp |
| X3 | **D** resolves **40%** of the unattested and loses **≤ 5** attested outside ClipSp |
| X4 | **U** resolves **60%** of the unattested and loses **5–15** attested outside ClipSp. Real code containing an instruction our decoder lacks gets cut short |
| X5 | the earliest of P, D, U resolves **75%** of the unattested |
| X6 | all three rules end `0x160260` before `0x1619f7`. Its region follows a `ret` and falls outside any `.pdata` range |

**If X5 holds,** a grounded extent does most of the work, and (bn) needs no
second condition. **If it doesn't,** the residual is something extent does
not explain, and it gets read from the bytes before anything is designed.
**Where no rule can determine the extent, the pass state is `undetermined`**
(owner ruling), not "reached" and not "unreachable".

**Independent checks:** raw bytes (padding), `.pdata` (unwind), UIR
(undecodable), and the Ghidra labels.

---

## Outcome

*(below this line, from the artefact only)*

**Inputs:** build `adcbf3c1…`; `extent_rules.py`, `residual_alignment.py`;
results `extent-result.json` and `residual-alignment-result.json` in
`~/corpus/tools-2026-09-24/SHA256SUMS`; Ghidra dumps from the attestation.
**553** kept port-fact functions measured: 362 unattested, 91 attested
outside ClipSp, 100 attested in ClipSp.

| rule | unattested resolved (of 362) | attested lost, not ClipSp (of 91) | ClipSp attested resolved (of 100) |
|---|---|---|---|
| **P** `.pdata` end | **0** | 0 | 0 |
| **D** padding after ret/jmp | **7** | 1 | 0 |
| **U** first undecodable | **337** | **29** | 58 |
| earliest of the three | 337 | 30 | 58 |

| # | predicted | observed |
|---|---|---|
| X1 | 60% of entries in `.pdata` (40–80%) | **missed high: 88.2%** (488 of 553) |
| X2 | P resolves 50% | **missed: 0%** |
| X3 | D resolves 40% | **missed: 2%** (7) |
| X4 | U resolves 60%, loses 5–15 attested | **missed both ways**: resolves 93%, but loses **29 of 91 (32%)** attested |
| X5 | the earliest resolves 75% | 93%, but only through U, whose false-negative rate rules it out as an end rule |
| X6 | all three end `0x160260` before `0x1619f7` | D and U cut at `0x1602b6`/`0x1602b8`; **P has no range**, since the entry is not in `.pdata` |

### The owner's reframe, tested: the residual is not mostly an extent problem

**P resolves none of the 362.** 88% of these functions carry a `.pdata`
range, and every unattested port site lies **inside** it. The product's
extent agrees with the compiler's unwind data for these functions. So the 363
are not, for the most part, neighbours the extent swallowed. **(bp)'s region
is a genuine extent case**: no `.pdata`, no reference, found by Ghidra's
function-start analysis. It is the exception, not the residual's pattern.

**U catches the residual only because the decoder stumbles first**, and it
cuts real functions at the same rate. That makes it a symptom, not an end
rule.

### What the residual is, against Ghidra's boundaries

Every reachable port site in the kept port-fact functions (11,453):

| against Ghidra's listing | sites |
|---|---|
| Ghidra lists `IN`/`OUT` starting there (attested) | 583 |
| inside a Ghidra instruction (our decode out of step) | 131 |
| **Ghidra has no instruction covering the address** | **10,739 (94%)** |
| Ghidra has a different instruction starting there | 0 |

**94% of the residual's port sites are bytes that flow-following disassembly
does not treat as code, inside declared function ranges**, which our linear
decode lifts and our CFG reaches. Desync (131) explains little of it.

**How our CFG reaches those bytes is not measured.** It could be fall-through
past a call that does not return; a fall-through edge after a table jump; an
edge from a misdecoded branch; or something else. **Each is a hypothesis
about a mechanism, and this desk has asserted unverified mechanisms five
times this week.** The next step is to read a drawn sample of residual sites
from the bytes and trace the edge path by which our CFG reaches each one.
Nothing is designed before that.

**(bp) stands as its own, smaller item**: extent where there is no
`.pdata`. **(bn)'s second condition is now a question about our CFG's edges
into non-code, not about extent.**
