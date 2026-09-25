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
