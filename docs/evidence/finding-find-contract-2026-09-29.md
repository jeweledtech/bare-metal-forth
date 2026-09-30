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
The comment promises the ANS contract — an immediacy flag (`xt 1`
immediate, `xt -1` normal, `c-addr 0` not found). The body does **not**
pop `c-addr` (`find_` reads `word_buffer`, not the stack); it just pushes
`eax` on top. So the real contract is `( c-addr -- c-addr xt|0 )`: the
input address is retained and `xt` (found) or `0` (not) is pushed above
it.

> **Reading corrected by measurement, 2026-09-30.** An earlier draft of
> this finding said the body "consumes `c-addr` and pushes one cell"
> (`( c-addr -- xt|0 )`) and inferred a stack underflow in the callers.
> That was wrong — the same confident-wrong-reading failure this finding
> is *about*. The FIRSTBOOT session measured `FIND` in QEMU on the current
> image: after `WORD FIND` the stack is `c-addr xt` (two cells), so
> `WORD FIND NIP` leaves exactly `xt` with no underflow. The correction is
> folded in below. The conclusion is unchanged: the comment is false and
> the rename is the right fix.

Cell **count** is not the lie — both the comment and the body leave two
cells. The lie is what the second cell *means*: the comment says an
immediacy flag `±1` (and that `c-addr` is replaced by `xt` on a hit);
the body always keeps `c-addr` and makes the top cell the raw `xt|0`.
Not-found agrees (`c-addr 0`); found does not (`c-addr xt` vs the
promised `xt 1`/`xt -1`).

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

- **Shipped, and correct:** `install.fth:101` `BIND-WRITER` and `:125`
  `BIND-READER`, both `WORD FIND NIP  DUP IF …! ELSE DROP THEN`.
  `WORD` leaves `c-addr`; `FIND` pushes `xt|0` **on top** (leaving
  `c-addr xt|0`); `NIP` drops the `c-addr` and keeps `xt|0`. **No
  underflow — these are correct code**, and they work as bind-if-found
  because `find_` returns `0`/`xt`. (They do still depend on `WORD` and
  `FIND` running back-to-back in a colon definition so `word_buffer`
  survives — `lesson_word_find_interactive`.) The finding is *not* that
  these callers are broken; it is that the comment they were written
  against is false, so the next caller that trusts it will not be.
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
  calls). The two `install.fth` callers use `FIND` correctly, so the
  false comment is **dormant** in shipped code — it misleads no shipped
  caller today.
- The **live** false-positive was the wizard, now guarded. The hazard is
  purely forward: the next author who writes `<string> FIND` trusting the
  comment (expecting `±1`, or expecting `c-addr` to be replaced by `xt`,
  or building a name rather than parsing one) gets a confident-wrong
  answer.

## The owed fix (not done here — tee'd up)

Two options; both make the next misuse impossible to write by accident:

1. **Rename + correct the comment.** Rename the primitive to
   `(FIND-LAST)` (or similar) with a truthful `( c-addr -- xt|0 )`
   comment noting it reads `word_buffer`, not `c-addr`. Update the two
   `install.fth` callers. Cheapest; removes the ANS-shaped trap.

   **Metacompiler dependency — CHECKED 2026-09-30, rename is safe.** The
   worry was `test_meta_compile.py`, which looks up `FIND` in the
   metacompiled symbol table (`comp_words` includes `'FIND'`, via
   `T-FIND-SYM`). Two "FIND" things exist in the metacompiler and
   **neither is tied to the host Forth word's name**:
   - the *target* symbol `FIND` is a literal `S" FIND" TX-CODE`
     (`target-x86.fth:847`) — renaming the host word does not change it,
     so `T-FIND-SYM` still finds it;
   - `ADDR-FIND` (the host address the target's FIND calls) is
     `DEFCONST "ADDR-FIND", ADDR_FIND_FN, find_` (`forth.asm:3607`),
     bound to the **asm label `find_`**, not the DEFCODE word.
   No `' FIND` tick or `T-ALIAS ... FIND` exists (grep of `forth/dict/`).
   So renaming `DEFCODE "FIND"` → `DEFCODE "(FIND-LAST)"` breaks neither
   the meta test nor the metacompiler. **The blocker is cleared; the
   only remaining question is sequencing — whether to stack this kernel
   change before the pending HP trip (UEFI-2 + CARRIER-0b are already
   unpushed). Owner's call.**
2. **Restore the real ANS contract.** Make `FIND` push `xt flag` /
   `c-addr 0` and read `c-addr` from the stack. Correct, but it changes
   the top cell's meaning from the raw `xt` to a `±1` flag, so both
   `install.fth` callers (whose `NIP` keeps that top cell and expects it
   to be the `xt`) must change — a wider blast radius.

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
