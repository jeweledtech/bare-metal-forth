# FINDING: after an undefined word the interpreter runs the rest of the line (and of a loading block); interpret-mode `."` prints nothing and compiles dead code (2026-10-11)

Owner ruling 2026-10-11:
- Write this up as its own finding, with no fix yet.
- Reproduce it with harmless words only.
- Include the block-loaded `."` banner that prints nothing, if related.
- It goes high in the queue, next to the `(` wedge.

## Summary

- **Undefined word.** The kernel prints `<word> ?`, sets STATE to 0
  and carries on parsing the same input.
  - The rest of a typed line runs.
  - The rest of a block being loaded runs, and so do the blocks after
    it.
  - The data stack is kept.
  - Forth-83 aborts instead: it empties the stack and discards the rest
    of the input.
  - So `TYPO 900 MIRROR` would run `900 MIRROR`. Inside a definition it
    is worse: STATE is 0 after the error, so the rest of the body
    executes at definition time, and `;` (IMMEDIATE) still finishes the
    word.
- **Interpret-mode `."`.** This is a different mechanism with the same
  kind of silent divergence. `."` has no interpret branch.
  - Typed or block-loaded at the top level, it prints nothing.
  - It compiles `(S") len string TYPE` at HERE, so the dictionary grows
    by dead code.
  - This is why `." MIRROR vocabulary loaded" CR` never printed.
- **Both were observed** with harmless words, and every case matched a
  prediction written first.

## Code

`src/kernel/forth.asm`:

- **INTERPRET `.undefined`:** prints `word_buffer` and `msg_undefined`,
  then `mov dword [VAR_STATE], 0`, then `NEXT`. That returns to the
  `cold_start` loop, which calls INTERPRET again at the same `>IN`.
  - Nothing resets `>IN`, the data stack, `BLK` or `TIB`.
  - The kernel's `ABORT` does exactly that reset: ESP, EBP, STATE, TIB,
    `>IN`, BLK and the block-loading flag, then re-enters the
    interpreter. `.undefined` does not call it.
- **`DEFCODE '."', DOTQUOTE, F_IMMEDIATE`:** always lays down
  `DOSQUOTE`, the length, the string bytes, alignment and `TYPE` at
  HERE, and advances HERE. There is no `STATE` test.

## Reproduction

Harmless words only: `ZZNOPE` is never defined. The run used floppy +
IDE scratch copies of combined.img `38671d92…`, with two staged blocks
(2550, 2551) on the copies. Predictions were frozen before the run.

| # | input | observed | Forth-83 |
|---|---|---|---|
| U1 | `ZZNOPE 7 .` | `ZZNOPE ?` then `7` | line discarded, no 7 |
| U2 | `1 2 ZZNOPE 3` then `DEPTH .` | `3` | 0 (ABORT empties the stack) |
| U3 | `: UT1 ZZNOPE 5 . ;` then `UT1` | `ZZNOPE ?` then `5` printed at definition time; `UT1` exists afterwards and runs silently (a half definition) | definition abandoned, no UT1 |
| U4 | block `ZZNOPE  6 .` / `8 .`, `2550 LOAD` | `ZZNOPE ?` then `6 8`: the rest of the block ran | load aborted |
| U5 | `HERE @ . ." BANNER-TXT" HERE @ .` | nothing printed; HERE 382964 -> 382988 (+24 = 4+4+10+2+4) | (interpret-mode `."` is an error in Forth-83; many systems print it) |
| U6 | block `." BANNER-TXT" CR`, `2551 LOAD` | nothing printed; HERE +24 | as U5 |
| U7 | `: UT2 ." IN-COLON" ;  UT2` | `IN-COLON` (control: compiled `."` works) | same |

## Prior record

The undefined-word behaviour was known and repeatedly worked around,
but never filed as a kernel defect:

- **The twelfth rule (2026-09-11),** from the 2e iron trip. The card
  line `DEF? XHCI-CLAIM .` ran with `DEF?` undefined, and
  `XHCI-CLAIM`, a write-capable word, executed against base 0. It
  returned 0 only by accident. The response was a card rule (a check
  and its action never share a line) and word-enforced refusals.
- **The gate-fail-open rule:** a test's `'-1' in response` was
  satisfied by underflow junk (`-1900006918`) after an undefined word.
- **`ALSO <undefined>` corrupting the dictionary (2026-05):** STATE is
  reset mid-definition, then `;` unhides the half definition.
- **This session's own instrument fault:** the MIRROR test's first
  MIRROR-BLK probe sent `.` after an undefined word and underflowed the
  stack (TASK_MIRROR_FIX.md §5).

Interpret-mode `."` had no record found. The kernel comments and the
S"-laydown work discuss its compile path only.

## Reach

- **Typed lines:** any typo before a destructive word on the same line
  runs that word. The twelfth rule covers cards, not typing.
- **Block loads:** a vocabulary with an unresolved word keeps loading.
  Every later definition compiles, and words after the error in the
  same definition execute live. This matches the stack junk recorded
  for the 2026-09-05 HP reload (Bug #34's failure signature); that is
  reasoned, not re-observed.
- **Top-level `."` in seven vocabulary files:** auto-detect, disasm,
  mirror, net-dict, pci-bar, rtl8139 and xhci. Each adds dead bytes to
  the dictionary and prints nothing. AUTO-DETECT is embedded, so every
  boot's dictionary carries its `[AD-OK]` laydown.

## Not done here

No fix, by ruling. For the queue, two kernel questions:

- **Should `.undefined` do what ABORT does?** That is: empty the
  stacks, discard the input, end a block load.
  - It changes every test that relies on reading past an error. The
    twelfth rule exists because of the current behaviour, and some
    harness helpers parse around it.
  - It needs its own red: U1-U4 as gates.
- **Should `."` print in interpret mode, or refuse?** The second option
  is a named error, like `string_unterm_`.
