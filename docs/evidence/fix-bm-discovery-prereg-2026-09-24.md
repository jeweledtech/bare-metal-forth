# (bm) discovery takes a direct call's target as decoded: pre-registration (2026-09-24)

**Written before the fix.** Owner ruling, 2026-09-24: (bm) then (bk).
(bm) is **a defect in the denominator of most of this arc's measurements**:
every figure whose unit is *a function* was computed on its boundaries. The
candidate list of those figures is written down **here, before the fix
lands**, so that afterwards the result is a comparison and not a
re-derivation. Which of them move is measured, not deduced. Outcomes go BELOW
the line.

## The change, and only this

`sem_discover_functions()` step 2: for an `X86_OP_REL` operand, the target
is **`imm`**, which the decoder already made absolute (`x86_decoder.c`
`E8`/`E9`/`EB`: `imm = base_address + offset + rel`). Today it is
`address + length + imm`. **One line.** The `X86_OP_IMM` branch is
unchanged.

**Not in this change** (owner ruling 3): collecting `jmp` targets as entries.
That is a behaviour change, since a `jmp` target may be a tail call or an
intra-function branch, and it gets its own letter, red and justification.
The 31 class-library thunks reached only by a direct `jmp` stay absorbed.

**Other readers of a REL operand's `imm`, checked.** The lifter
(`uir.c`, `X86_OP_REL` → `UIR_OPERAND_ADDR`, `imm` copied as-is) and the
semantic analyzer's direct-call edges (`edge->target_addr = dest.imm`)
already treat it as absolute. Discovery step 2 was the one reader that
re-offset it.

## Reach, measured before the fix (the population the change should touch)

`bm_extent_v2.py` counts objdump's direct-call targets inside the
translator's own discovery range (`.text` widened to every executable
section, `translator.c:989–995`) that are not function entries today:
- **225 of the 1,322** kernel drivers; **19,329 of 483,053** targets;
- the HP eight: **0**;
- among the snapshot inputs: ReactOS `serial.sys` **2**, `nmap_service.exe`
  **93**; `beep.sys` and the ELF fixture **0**.

The differential's `dump_starts` does not call discovery.

## Candidate figures whose unit is the function (written before the fix)

1. per-driver **total functions** and the three buckets;
2. the **park census** outcomes (`park-census-cross-vendor-2026-09-22.md`,
   marked provisional today): 65 / 78 / 83 Dell / older ASUS / newer ASUS
   sites sit in affected drivers, and HP 0;
3. **stage 2** and the **320 hardware functions**: HP-only, and HP is clean,
   so **candidates that should not move**;
4. `(bk)`'s thunk ownership (239 absorbed of 291);
5. X1, X2 and X3: import-only, so **should not move** in value, though the
   report bytes carrying them will on the affected drivers.

## Predictions

**Must not move**

| # | prediction |
|---|---|
| N1 | the **1,097** kernel drivers with 0 missing entries: report bytes **identical, 1,097 of 1,097** (sha256 of the full report, before `343e89fa…` against after) |
| N2 | UIR: **10 of the 12** snapshot inputs identical (the HP eight, `beep.sys`, the ELF fixture). The differential's **16 dumps identical** |
| N3 | X1 **0** hex on all 1,322; X2 `import_family` unchanged on **1,322 of 1,322**; each driver's four-DLL (DLL, name, category, source) set unchanged on **1,322 of 1,322** |
| N4 | the park census: **HP row identical**; site counts **12 / 172 / 171 / 184 unchanged** (a site is an instruction, whatever function holds it) |
| N5 | the gate fires on **exactly** `sem_RED_bm_call_target_is_entry`; `(bk)` **stays red**; 418 tests; reds 14 → 13 |

**Should move** (direction and size, the owner's point 2)

| # | prediction |
|---|---|
| S1 | **all 225** affected drivers' report bytes change, and `total_functions` **rises on each of the 225** |
| S2 | total functions over the 225 rise by **18,800** (range **17,000–19,600**). The bound is the 19,329 missing targets. It can fall short where objdump's instruction boundary and ours differ, since a target that is not one of our instruction starts maps to the next, which may already be an entry. It can exceed it slightly where our decode sees a call objdump does not |
| S3 | bucket direction over the 225: **unclassified rises and carries most of the increase (> 50% of ΔTotal)**. **Hardware does not fall in total.** Splitting a function can only separate hardware evidence from code that has none. It cannot remove the evidence |
| S4 | the park census: **≥ 1 outcome changes, and every changed outcome sits in an affected driver**. Direction: toward **`none`**, because a park walk ends at its function's end and functions get shorter. Size **not predicted** |
| S5 | snapshot UIR: `serial.sys` **+2** functions (36 → 38); `nmap_service.exe` **15 → between 90 and 108** |
| S6 | `(bk)`'s thunks: of the 239 absorbed, the **199 with a direct `call`** become functions of their own, **exactly 199**. The 31 reached only by `jmp`, and the 9 with no direct reference, stay absorbed. Measured with the 664-0 instrument (`m664.py` v2) |

**Independent checks:**
- report-hash comparison over the 1,322 (N1, S1–S3, one run);
- the park census harness (N4, S4);
- the UIR and dump snapshot (N2, S5);
- the suites (N5);
- thunk ownership with objdump and UIR (S6).

**Five.** A fix that lands inside N1–N5 but misses S1–S6 is the more
interesting outcome, and will be read that way.

---

## Outcome

*(below this line, from the artefact only)*

**Inputs hashed:** `bin/translator` before `343e89fa8fe39611`, after
`60df7c753af56625`, built from private `2dbcdb3` (red `03e932f`), mirror
identical. Readings are in `~/corpus/tools-2026-09-24/`: `bm-reports-{pre,post}.tsv`,
`bm-park-census-{pre,post}.json` and `bm-m664-post.json`, all in `SHA256SUMS`.
0 empty outputs in either report run. The census's fresh before-reading
reproduces the site counts 12 / 172 / 171 / 184.

### Must not move: five of five held

| # | observed |
|---|---|
| N1 | **1,097 of 1,097** clean drivers' reports byte-identical |
| N2 | UIR: exactly the two predicted files differ (`serial.sys`, `nmap_service.exe`), **10 of 12 identical**; dumps **0 of 16** differ |
| N3 | **0** hex; `import_family` unchanged on **1,322 of 1,322**; four-DLL sets unchanged on **1,322 of 1,322** |
| N4 | site counts **12 / 172 / 171 / 184** unchanged; **0** sites appear or disappear; the HP row is identical |
| N5 | the gate fired on exactly `sem_RED_bm_call_target_is_entry` (`fix-bm-xpass-gate-2026-09-24.log`); `(bk)` still red; 418 tests, 13 reds |

### Should move: two held, two partly, two missed, and the misses are the finding

| # | predicted | observed |
|---|---|---|
| S1 | all 225 change, and `total_functions` rises on each | **missed**: **218** of 225 changed. The count **rose on 198** and **fell on 20**. **7** are byte-identical, each with only 1–4 missing targets. That they map onto existing entries through a boundary difference is reasoned, not checked |
| S2 | ΔTotal ≈ **+18,800** (17,000–19,600) | **missed, sign reversed: −71,502.** The 198 rose **+16,593**, just below the range for the rise alone. The 20 fell **−88,095** |
| S3 | unclassified > 50% of ΔTotal; hardware does not fall | **partly.** On the 198, unclassified is +17,348 (all of the rise, with scaffolding −838), and hardware is +83 net but **fell on 4**. On the 20, hardware **−1,745** |
| S4 | ≥ 1 census outcome changes, all in affected drivers, toward `none` | **held on count and place, missed on direction**: **3** changed, all in affected drivers (one each on Dell, older ASUS and newer ASUS). All three are **`none` → `frame`**, away from `none`: the walks found a park they had missed |
| S5 | `serial.sys` 36 → 38; `nmap_service.exe` 15 → 90–108 | **held**: 36 → **38**; 15 → **108** |
| S6 | exactly 199 absorbed thunks become their own function | **held exactly**: **199** called thunks → own; 31 `jmp`-only and 9 unreferenced stay absorbed; the 52 already-own unchanged |

### What the misses found: (bm) was two-sided

**All 20 drivers whose function count fell have image base `0x10000`.** For
them, the old `address + length + absolute` landed **back inside** the
discovery range, at a wrong address. So the defect did not only *miss*
entries: on low-base images it **fabricated** them, at addresses no call
targets. Examples:
- `RTKVHD64.sys`: **53,468 → 5,472** and 39,292 → 8,841 (two builds);
- `megasr`, `iaStorV`, `amdsbs`, `nvraid`, `nvstor`, `vsmraid`: each ×3
  builds, roughly halved.

**My extent instrument could not see this side.** It counted direct-call
targets that were *not* entries. A fabricated entry is an entry that no call
targets, which it never looked for. **The should-move prediction is what
exposed it.** A fix landing inside N1–N5 with only a must-not-move set would
have read as clean. This is the owner's point 2, observed.

**So earlier function-unit figures are inflated on those 20 drivers** by
88,095 fabricated functions, 1,745 of them hardware, and 8,867 scaffolding.
That includes the (bi)-0 counterfactual's denominator ("16,400 hardware
functions on 921 drivers") and (bj)'s bucket totals, to the extent those
drivers are in them. **They are not re-derived here.** They are named, so a
reader of those documents knows which drivers carried fabricated functions.

### The park census, resolved

(bm) moved **3 of 539** census outcomes, all `none` → `frame`, one on each
non-HP machine, and moved no site count. The provisional mark on
`park-census-cross-vendor-2026-09-22.md` is resolved with those three
named. Its table's structure shares stand to within one site per machine.

**The commit message of `2dbcdb3`** says "missing entries on 205 drivers and
fabricating them on 20". All 225 had missing entries, and 20 of them also had
fabricated ones. This paragraph supersedes it.

**Independent checks: five,** as pre-registered. Two of six should-move
predictions held exactly, two held in part, and two missed. The two misses
found the fabricated side.
