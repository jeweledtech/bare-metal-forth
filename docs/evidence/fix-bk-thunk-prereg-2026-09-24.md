# (bk) a thunk function's `jmp [IAT]` is a call to the import: pre-registration (2026-09-24)

**Written before the fix.** Owner ruling: (bm) then (bk). After (bm), 251 of
the 291 class-library thunks are their own functions. **Scope, as ruled:**
(bk) resolves `jmp [slot]` **inside a thunk's own function**. That is, a
`UIR_JMP` whose memory target is an import slot counts as a call to that
import **only when it is the function's entry instruction**. Outcomes go BELOW
the line.

**Why the entry restriction.** A `jmp [slot]` that is not a function entry
is either a genuine tail call inside a body or a thunk still absorbed into a
neighbour. The 40 class-library thunks reached only by `jmp`, or not at all,
stay absorbed after (bm). Resolving those would give the import to the
neighbour, the misattribution (bm) was fixed to avoid. **2,432 such non-entry
sites** exist across the 1,322. They stay unresolved, counted, and are not
part of this change.

**The fix site** (`semantic.c`, the IAT branch of the call walk):
`if (ins->opcode != UIR_CALL) continue;` admits a `UIR_JMP` at the function's
entry address whose memory operand resolves to an import slot. The lifter
resolves RIP-relative targets for any operand (fix (a)).
- A tail jump **does not run stage 1's park walk**: the mapped base returns
  to the thunk's caller, not here.
- It **does not set `mapped_regions_analysed`**: the walk did not run, and
  zero-measured must not print like zero-found.

## The population, counted from the input (not from a run of the change)

`bk_thunks.py` (pefile IAT slots, objdump `jmp [slot]` sites, the shipped
translator's function entries, and each import's category from today's
report), over the 1,322:

| | |
|---|---|
| thunk functions (`jmp [slot]` at a function entry) | **3,611** on **764** drivers |
| … to a scaffolding import / a hardware import / other (unclassified, no public reference) | **509 / 11 / 3,091** |
| … to a `MmMapIoSpace*` import | **1** |
| drivers with ≥ 1 hardware or scaffolding thunk | **165** |
| non-entry `jmp [slot]` sites (unresolved by design) | **2,432** |
| HP eight | ACPI 14 (5 scaffolding), pci 18 (5 scaffolding), i8042prt 1, serial 1, storport 1 (other); **0 hardware** |
| the 66 thunk-only WDF drivers with ≥ 1 scaffolding thunk | **66 of 66** |

## The red

`sem_RED_bk_import_thunk_jmp_resolved`, registered 2026-09-24, with its
harness control (the same fixture with `call` passes). Its thunk is a
function whose entry is `jmp [slot]`, which is inside this scope.

## Predictions (from the counts above; no dry run)

| # | prediction |
|---|---|
| K1 | the gate fires on **exactly** `sem_RED_bk_import_thunk_jmp_resolved`; 419 tests; reds 13 → 12; the domain guard stays `[accepted=14]` |
| K2 | **per driver, `iat_edges` rises by exactly its thunk count** on all 1,322 (**+3,611** in total), and `iat_slot_hits` likewise |
| K3 | report bytes change on **exactly the 764** drivers with a thunk, and **558 are identical** |
| K4 | hardware functions **+11** in total, each on a driver with a hardware thunk; **no other hardware change**. HP stays **266** |
| K5 | buckets move on **exactly the 165** drivers with a hardware or scaffolding thunk; scaffolding rises by **≥ 509** (the thunks, plus transitive callers); unclassified falls by the same amount plus 11 (conserved) |
| K6 | **all 66** thunk-only WDF drivers move buckets |
| K7 | park census: sites **12 / 172 / 171 / 184**, **0 of 539** outcomes change (the one `MmMapIoSpace*` thunk's walk is skipped by design) |
| K8 | X1 0 hex; X2 1,322 of 1,322; X3 four-DLL sets 1,322 of 1,322. HP: buckets move on **ACPI and pci only**; report bytes change on **ACPI, i8042prt, pci, serial, storport**; `mapped_regions` identical on 8 of 8. UIR **0 of 12**, dumps **0 of 16** |

**Independent checks: four.**
- The suites.
- The population report run, which carries K2–K6 and K8's X figures.
- The census harness.
- The snapshot.

**Honest limits, stated before:** K4's "+11 exactly" and K5's "exactly 165"
assume each thunk function is currently unclassified: a function consisting
of a `jmp` has no call edges. A thunk function whose range also absorbed
other code with classified calls would break that assumption. Where it
breaks, it will be read from the bytes, not smoothed.
