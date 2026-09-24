# (bj) change 2: the values: pre-registration (2026-09-23)

**Written before any code.** Change 1 made the scaffolding set one list,
append only (`fix-bj-scaf-encoding-prereg-2026-09-23.md`). Change 2 adds the
values X3 needs. Its red is `(bj)`'s first. It must fail for a reason change 1
could not have fixed, and the gate names the exact tests. Outcomes go BELOW
the line.

## The change

**Three scaffolding categories, appended to `SEM_SCAF_LIST`** (bits 10, 11,
12; no existing reason moves), mirroring the driver-level families:

| enum | value | report name | drop-reason name | source |
|---|---|---|---|---|
| `SEM_CAT_STORAGE_CLASS` | 0x89 | `STORAGE_CLASS` | `STORAGE-CLASS` | import directory: imported from `classpnp.sys` |
| `SEM_CAT_AUDIO_PORT_CLASS` | 0x8A | `AUDIO_PORT_CLASS` | `AUDIO-PORT-CLASS` | import directory: `portcls.sys` |
| `SEM_CAT_WDF` | 0x8B | `WDF` | `WDF` | import directory: `wdfldr.sys` |

The enum values are free after change 1: the list decides the bit, and the
values sit beside the scaffolding block only for legibility.

**One non-scaffolding, non-hardware category, `SEM_CAT_NO_PUBLIC_REFERENCE`
(0xE0, report name `NO_PUBLIC_REFERENCE`),** for the 17 HAL names. It means
*no page at the four probed patterns, and search returned nothing or
index-only* (`x3-sourcing-prereg` amendment). It is not a finding about what
the call does. It sits outside every range, so it touches neither the mask
nor `is_hardware`, and could have landed alone (owner's check: it does not
need the encoding).

**Where the categories come from: two new declarations, and the frozen
vocabulary is not edited.**
- `SEM_DLL_CATEGORY[]` holds 3 rows `{dll, category}`. An import from one of
  those DLLs takes that category **from the import directory**, whatever its
  name. It is compared case-insensitively.
- `SEM_NO_PUBLIC_REFERENCE[]` holds 17 rows `{"hal.dll", name}`, citing
  `x3-sourcing-prereg-2026-09-23.md`.
- `SEM_API_TABLE` (hash `b48923e8…`) **is not touched.** The owner ruled that
  X3 does not edit the vocabulary.

**The source of every category, printed per import** (owner ruling 6), as a
new `"category_source"` field. Precedence, first match wins:

| value | when |
|---|---|
| `import-directory` | the DLL is in `SEM_DLL_CATEGORY` |
| `pinned-page` | the `(hal.dll, name)` is one of the 4 pinned in `x3-sourcing-prereg` §D. A third declaration, `SEM_PINNED_PAGE[]`, holds 4 rows with their URLs. The **category** still comes from the vocabulary; the page is what checked it (M = 0) |
| `none` | in `SEM_NO_PUBLIC_REFERENCE` (category `NO_PUBLIC_REFERENCE`), or in no table at all (category `UNCLASSIFIED`) |
| `vocabulary-uncited` | any other vocabulary hit: the 142 of `(bi)` |

## The exit, amended with its reason

The exit said *"85 of 85 covered, with the hash re-pinned"*. **Amended:** 85
of 85 print a category other than `UNCLASSIFIED`, and the **vocabulary hash is
unchanged**. The reason is the owner's later ruling that X3 does not edit the
vocabulary. The new names live in the three declarations above, each carrying
its source. This changes where the categories are declared, not the count.

## The reds (`test_semantic.c`, letter (bj))

All three test through `sem_to_json` and the drop reason, and use no new enum
name, so they **compile today and fail on today's values**. Change 1 could not
have fixed them, because it added no value.
- `sem_RED_bj_class_library_categories`: one import each from
  `CLASSPNP.SYS`, `portcls.sys` and `WDFLDR.SYS` prints `STORAGE_CLASS` /
  `AUDIO_PORT_CLASS` / `WDF` with `category_source` `import-directory`. A
  function whose only call is one CLASSPNP import renders the drop reason
  `STORAGE-CLASS`.
- `sem_RED_bj_no_public_reference`: `HalEnableInterrupt` from `hal.dll`
  prints `NO_PUBLIC_REFERENCE`, source `none`, `is_hardware` false.
- `sem_RED_bj_category_source`: `HalGetBusDataByOffset` → `pinned-page`
  (category still `PCI_CONFIG`); `IoCompleteRequest` → `vocabulary-uncited`;
  a name in no table → `UNCLASSIFIED` / `none`.

## Predictions

| # | prediction | instrument |
|---|---|---|
| V1 | the gate fires on **exactly** the three `(bj)` names. Tests 413 → 416; reds 12 → 15 → 12; the domain guard prints **`[accepted=13]`** and stays green | suite |
| V2 | **X3:** over the 1,322, the 85 distinct (DLL, name) pairs from the four DLLs print **85 of 85** a category other than `UNCLASSIFIED`. By `category_source`: **import-directory 64, pinned-page 4, none 17** (all 17 `NO_PUBLIC_REFERENCE`) | report over the population |
| V3 | **`hardware_functions` unchanged on all 1,322**: no new category is hardware | same run, before/after per driver |
| V4 | **function buckets move only on drivers importing CLASSPNP, portcls or WDFLDR** (392). On each, scaffolding rises by exactly the amount unclassified falls (the three buckets are conserved). On the other **930, all three buckets are unchanged**. The magnitude on the 392 is **counted, not predicted**: it depends on the call graph, and I have no independent instrument for it | same run |
| V5 | X1 stays 0 hex; **X2 stays 1,322 of 1,322** | same run |
| V6 | vocabulary hash **`b48923e8…` unchanged**; UIR 0 of 12 and dumps 0 of 16 unchanged | extraction rule; snapshot |

**Independent checks, counted as ruled:** suite state (V1), the population
report (V2–V5 are one instrument, one run), vocabulary extraction plus the
snapshot byte-compare (V6), and discrimination on the guard at its widened
range, re-shown in a throwaway with its log banked. **Four.**

---

## Outcome

*(below this line, from the artefact only)*

**Inputs hashed:** `bin/translator` before `f8e18de77b58bfa7`, after
`343e89fa8fe39611`, built from private `bf426ed` (reds `e8562d5`), mirror
identical. Per-driver readings are
`~/corpus/tools-2026-09-23/bj2-buckets-{pre,post}.tsv` (`0d0d18009f3e…`,
`5be2a0059ceb…`). Neither has an empty output: 0 NOJSON in 1,322 both times.

| # | predicted | observed |
|---|---|---|
| V1 | the gate fires on exactly the three; 416 tests; 12 reds after; guard `[accepted=13]` | **held**: the gate fired on exactly `sem_RED_bj_class_library_categories`, `sem_RED_bj_no_public_reference` and `sem_RED_bj_category_source` (`fix-bj-xpass-gate-2026-09-23.log`). After removal: 416 tests, 12 reds, register union matches. The guard prints `[accepted=13]`, and the frozen-order test (`"IRP+DIAGNOSTIC"`) still passes |
| V2 | 85 of 85 print a category other than UNCLASSIFIED; sources 64 / 4 / 17 | **held exactly**: **85** distinct pairs, **0** UNCLASSIFIED, **0** pairs with more than one value across the population. Sources: import-directory **64**, pinned-page **4**, none **17**. Categories: STORAGE_CLASS 41, AUDIO_PORT_CLASS 15, WDF 8, NO_PUBLIC_REFERENCE 17, TIMING 2, PCI_CONFIG 2 |
| V3 | `hardware_functions` unchanged on all 1,322 | **held**: changed on **0** |
| V4 | buckets move only on the 392 class-DLL importers, conserved; the other 930 unchanged | **held**: buckets moved on **179** drivers, **all 179** class-DLL importers, **0** others. Conserved (scaffolding rise = unclassified fall) on **179 of 179**. *Counted, not predicted:* **+742** scaffolding functions in total, 1 to 143 per driver. **213** of the 392 importers did not move. **Why is not examined**: a likely reading is that each class-library call sits in a function already classified another way, but that is reasoned, not measured |
| V5 | 0 hex; X2 1,322 of 1,322 | **held**: 0 hex; `import_family` unchanged on **1,322 of 1,322** |
| V6 | vocabulary hash unchanged; UIR 0 of 12; dumps 0 of 16 | **held**: extraction sha256 `b48923e815d3…`; **0 of 12**; **0 of 16** |

**Discrimination at the widened guard,** banked as
`fix-bj-values-throwaway-2026-09-23.log`. With the `STORAGE-CLASS` name
removed in a throwaway, the guard fails ("an accepted category has no name of
its own"). The file was restored identical, the guard passes with
`[accepted=13]`, and the binary hash is again `343e89fa…`.

**Independent checks: four, as pre-registered.** Suite state (V1); the
population report (V2–V5: one instrument, one run); vocabulary extraction plus
the UIR and dump comparison (V6); and discrimination.

**The import sort's exit is met, three of three.**
- **X1:** 0 of 128,142 imports print a hex category.
- **X2:** `import_family` agrees with the independent scanner on 1,322 of
  1,322.
- **X3:** 85 of 85 print a value; 68 of 85 are sourced (64 import directory,
  4 pinned page); 17 print `NO_PUBLIC_REFERENCE`.

X3's result is the three-way split printed per import in `category_source`.
