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
