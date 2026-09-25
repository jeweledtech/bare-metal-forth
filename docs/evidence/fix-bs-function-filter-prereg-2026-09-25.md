# (bs) `-f` names one function: pre-registration (2026-09-25)

**Written before the fix.** Owner ruling 2026-09-25: *"-f is a dead flag.
Wire opts.function_name so -f emits only the named function."* Outcomes
go BELOW the line.

**The defect, read from the source.** `-f` stores `argv` into
`opts.function_name` (`translator.c:1236`). The field has three
references: its declaration (`translator.h:65`), its default
(`translator.c:802`) and that store. **Nothing reads it.**
- The output was byte-identical with and without `-f` on HDAudBus
  (`1C0022510`) and on i8042prt (`1C0001260`, in three spellings).

**The design** (proposed here, before building):
1. **`-t forth -f NAME`**: the vocabulary is the no-flag vocabulary with its
   `\ ---- Extracted Functions ----` section cut to the one word for NAME.
   **Every other line is unchanged.** That means the catalog header, strip
   summary, REQUIRES, preamble, register constants, base accessors and
   footer. These are driver-wide, so a port driver keeps its accessors.
   The filter goes in `generate_forth_output`, after the strip summary is
   built.
2. **NAME matches a function** when it equals the function's name
   (`func_1C0022510`, or an export name), or when it parses **whole** as
   hex, with an optional `0x` or `func_` prefix, and equals the function's
   address.
3. **Refused, never ignored.** The run fails and the error says why in
   three cases:
   - NAME matches no function;
   - NAME matches a function that is not kept (the no-flag vocabulary has
     no word for it);
   - `-f` is given with any target other than `forth`.

   An empty or silently whole vocabulary would be a skip that reads like a
   pass. **Named, not taken:** wiring `-f` for the other targets.

**The inputs, counted before the change** (build `adcbf3c1a22f1233`, no-flag
`-t forth -S`):
- **HDAudBus:** 450 lines and 21 words, all in the section. Cut to
  `MMIO-FN-1C0022510`, the prediction is **359 lines, sha256
  `c456d6bdf114d7c3…`**, with 20 words dropped.
- **i8042prt** (`~/corpus/hp_i3`): 367 lines and 31 words in the section,
  plus 3 accessors before it. Cut to `PORT-FN-1C0001260`, the prediction is
  **215 lines, sha256 `4c50ea2297dd1c99…`**, keeping `I8042PRT-REG`,
  `I8042PRT@` and `I8042PRT!`.
- **The must-not-move set:** 1,338 inputs (1,332 corpus `.sys` from
  hp_i3/Dell/Newer ASUS/Older ASUS plus 6 fixtures). No-flag output was
  hashed twice, identical, with 0 empty.

**The red:** `bs_RED_f_emits_only_the_named_function`, in
`test_mmio_consumer.c` (a corpus suite). Before the fix it XFAILs on all
four counts: the vocabulary is not cut, and none of the three refusals
happens.

| # | prediction |
|---|---|
| S1 | the gate fires on **exactly** `bs_RED_f_emits_only_the_named_function`; tests 423 → 424 at the red; reds 12 → 13 at the red and 13 → 12 at the fix |
| S2 | CLI `-f 1C0022510` on HDAudBus: stdout sha256 is **`c456d6bdf114d7c3…`** (359 lines), with **exactly one** colon definition, `MMIO-FN-1C0022510`, **identical** to its no-flag text. `func_1C0022510`, `0x1C0022510` and `1c0022510` give the same bytes |
| S3 | CLI `-f 1C0001260` on i8042prt: stdout sha256 **`4c50ea2297dd1c99…`** (215 lines) |
| S4 | refusals exit 1 with empty stdout: `-f 1C0000000`; `-f func_1C0001010` (dropped, SYNC); `-f 1C0022510 -t uir` |
| S5 | **must not move:** no-flag `-t forth` output byte-identical on **1,338 of 1,338** |
| S6 | nothing else moves: every other test unchanged; the census union matches |

---

## Outcome

*(below this line, from the artefact only)*

**Inputs hashed:** `translator.c` `75065fe76da0f118`,
`forth_codegen.c` `7d99e29ae83018f3`, `forth_codegen.h`
`5fd446bd9eec1ab2`, and build `bin/translator` `57d9b73ebdd13337`. The
build before the fix was `adcbf3c1a22f1233`.

### The first build failed the gate, and the defect was mine

**The first fix build XFAILed on one count only:** the three refusals
held, but the vocabulary was not the cut. A diff against the pre-registered
prediction showed exactly one line:

```
< \ STRIP: 346 total -> 21 kept / 76 scaffolding / 249 unclass
> \ STRIP: 346 total -> 1 kept / 76 scaffolding / 249 unclass
```

- The codegen contract says *"kept count == function_count"*
  (`forth_codegen.h`). The emitter prints `function_count` as "kept". My
  filter narrowed `function_count`, so the summary described the one word
  instead of the driver. That contradicts design point 1, which says the
  strip summary stays unchanged.
- **The fix carries the driver's count** in a new `kept_count` field. It
  defaults to `function_count` when 0, so other callers are unchanged.
- **Neither the prediction nor the red was edited.** The filter itself
  selects one entry of the function list. It never reads or cuts text, and
  it does not use the test's `cut_to_word`, so the check stays independent
  of the code it checks.

### The predictions

| # | predicted | observed |
|---|---|---|
| S1 | the gate fires on exactly the (bs) red; 424 tests; reds 12 → 13 → 12 | **held on the second build:** the gate fired on exactly `bs_RED_f_emits_only_the_named_function` (`fix-bs-xpass-gate-2026-09-25.log`). After retiring it: `test-all` exits 0, 424 tests across 27 suites, 12 reds, and the union matches |
| S2 | HDAudBus `-f 1C0022510`: sha256 `c456d6bdf114d7c3…`, 1 word, the same in all four spellings | **held:** `c456d6bdf114d7c3` for `1C0022510`, `func_1C0022510`, `0x1C0022510` and `1c0022510`. It has one colon definition and is byte-equal to the predicted file |
| S3 | i8042prt `-f 1C0001260`: sha256 `4c50ea2297dd1c99…` | **held:** `4c50ea2297dd1c99`, byte-equal to the predicted file, with its 3 accessors kept |
| S4 | three refusals, exit 1, empty stdout | **held:** each exits 1 with 0 bytes on stdout. stderr says `no function has that name or address`, `function 0x1C0001010 is not kept, so no word is emitted for it`, and `-f is supported only with -t forth` |
| S5 | no-flag byte-identical on 1,338 of 1,338 | **held:** 1,338 same and 0 moved, over the same input set |
| S6 | nothing else moves | **held:** every other suite is green, and the only census change is `test_mmio_consumer.c` at 4 tests |

**(bs) is closed.** `-f` now does what its help line says, for `-t forth`.
For every other target it is refused rather than ignored. **Named, not
taken:** wiring `-f` for the other targets.
