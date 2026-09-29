# FINDING — the kernel `FIND` word's stack comment is a lie (2026-09-29)

A substrate defect, recorded before its workarounds become load-bearing.
Two workarounds already exist in one session (this one, and WT-ALLOC —
its own finding, owed). Read-only audit; nothing changed by this doc.

## The defect

`forth.asm:1405`:
```
DEFCODE "FIND", FIND, 0     ; ( c-addr -- c-addr 0 | xt 1 | xt -1 )
    ; Simplified: just returns xt or 0
    call find_
    push eax
    NEXT
```
The comment promises the ANS contract — two cells out, an immediacy flag
(`xt 1` immediate, `xt -1` normal, `c-addr 0` not found). The body
consumes `c-addr` and pushes **one** cell: `xt` (found) or `0` (not).
The real contract is `( c-addr -- xt|0 )`.

`find_` (`forth.asm:4861`) also takes **no stack input** — it reads the
name from `word_buffer`, not from `c-addr`. So `FIND` ignores the address
it was handed and answers about whatever `word_buffer` last held.

## Why it is dangerous, not just wrong

A word whose comment says one thing and whose body does another does not
return a *wrong* answer — it returns a **confident answer about a
different word**. `find_` returns `0`/`xt` correctly for the token in
`word_buffer`, so a caller's found/not-found boolean often *looks* right,
which is exactly what keeps the bug alive: it passes by accident until
the address actually matters.

Presence gates are where it bites. "Is this vocabulary/word present?"
built as `<string> FIND` returns the lookup for the interpreter's
last-parsed token, not for `<string>` — and a gate that says "present"
to everything is how an install gate (G-BOOT/G-DISK/G-SPACE class) opens
on a machine that cannot boot the result.

## Callers and workarounds

- **Shipped, latent:** `install.fth:101` `BIND-WRITER` and `:125`
  `BIND-READER`, both `WORD FIND NIP  DUP IF …! ELSE DROP THEN`.
  `WORD` leaves `c-addr`; the simplified `FIND` replaces it with `xt|0`
  (one cell); `NIP` then keeps `xt|0` but **pops one cell from beneath**
  (a one-cell data-stack underflow per call). They work as bind-if-found
  only because `find_` returns `0`/`xt`, and only because `WORD` and
  `FIND` run back-to-back in a colon definition (no interpreter
  token-fetch between them — `lesson_word_find_interactive`). They depend
  entirely on the lying two-cell comment. Benign today (clean call
  stack), fragile forever.
- **Interactive:** `WORD X FIND` at the prompt always looks up `FIND`,
  never `X` (the interpreter re-fills `word_buffer`). Known since
  2026-08-04.
- **Compiled, constructed string (live bug, worked around):** the
  FIRSTBOOT wizard built a name and asked `<cs> FIND NIP`; it reported
  every vocabulary as loaded (it answered for the wizard's own last
  token), and a G-DISK-class gate passed by accident. Worked around with
  `WZ-LOADED?` (walk the dictionary chain from `VAR_FORTH_LATEST` and
  `STR=`-compare) in the FIRSTBOOT tree, pinned by that suite. **The
  kernel word is still unfixed; the wizard routes around it.**

## Severity

- **No shipped vocabulary builds a constructed string and calls kernel
  `FIND`** — grep of `forth/dict/` finds only `install.fth`'s two
  `WORD FIND NIP` sites (token-parsed, not constructed) and the
  metacompiler's `S" FIND"` *name emissions* into target images (not
  calls). So this is **latent** in shipped code, not a live
  false-positive gate there.
- The **live** false-positive was the wizard, now guarded. The hazard is
  that the next author writes `<string> FIND` trusting the comment.

## The owed fix (not done here — tee'd up)

Two options; both make the next misuse impossible to write by accident:

1. **Rename + correct the comment.** Rename the primitive to
   `(FIND-LAST)` (or similar) with a truthful `( c-addr -- xt|0 )`
   comment noting it reads `word_buffer`, not `c-addr`. Update the two
   `install.fth` callers. Cheapest; removes the ANS-shaped trap. Note:
   the metacompiler emits the *name* `FIND` into target images
   (`target-*.fth` `S" FIND"`) — that is target-side and independent of
   the host primitive's name, but confirm before renaming.
2. **Restore the real ANS contract.** Make `FIND` push `xt flag` /
   `c-addr 0` and read `c-addr`. Correct, but changes behavior and must
   fix both `install.fth` callers (their `NIP` assumes the two-cell
   shape) — and it is a wider blast radius.

**Recommendation:** option 1 now (rename + truthful comment + fix the two
callers), red-first; option 2 only if a genuine ANS `FIND` is wanted
later. Either way it is a scoped substrate change, not a drive-by, and it
should land before more callers copy the pattern.

## Related

- `lesson_word_find_interactive` (updated 2026-09-29 with the compiled
  case; index line sharpened by the FIRSTBOOT terminal).
- WT-ALLOC — the session's other locally-worked-around substrate defect;
  its finding doc is **owed** and needs the FIRSTBOOT terminal's context
  (the workaround site is not in this tree).
