# FINDING — the kernel `FIND` word's name and stack comment are a lie (2026-09-29)

A substrate defect, recorded before its workarounds become load-bearing.
Two workarounds already exist from one session (the FIRSTBOOT wizard's
`WZ-LOADED?`, and WT-ALLOC — its own finding). Read-only audit; nothing
is changed by this doc.

**Status:** OPEN. No live bug in shipped code (census, below). Rename
proposed; **HELD** (owner, 2026-09-30) until a natural kernel-image
boundary — after UEFI-5, or riding another change that re-pins the UEFI-2
image hashes anyway. Do not re-pin images during a live hardware arc for
this alone.

> Reconciles two independently-written drafts (one in the main tree, one
> in the firstboot worktree). The contract reading itself is the finding in
> miniature: the worktree draft read it correctly from the body on the first
> pass; the main draft first said `FIND` "pops `c-addr` and pushes one cell"
> (`( c-addr -- xt|0 )`) and inferred a caller underflow — **wrong**, the
> same confident-wrong-reading this finding is *about*. A QEMU measurement
> on the current image settled it (below). Lesson banked: don't trust a
> reading of a word this misleading — measure it.

## The defect

`forth.asm:1405`:
```
DEFCODE "FIND", FIND, 0     ; ( c-addr -- c-addr 0 | xt 1 | xt -1 )
    ; Simplified: just returns xt or 0
    call find_
    push eax
    NEXT
```
`find_` (`forth.asm:4861`) takes **no stack input**: it measures and
compares the NUL-terminated name in `word_buffer` (:5814), the buffer
`word_` fills — both when the outer interpreter fetches a token and when
the Forth word `WORD` runs. `FIND` pops nothing and pushes one cell: the
`xt`, or `0`.

So the real effect is: push `xt|0` for **the name `WORD`/the interpreter
parsed last**, ignoring the stack. Measured net on the current image
(QEMU, 2026-09-30): after `WORD FIND` the stack is `c-addr xt` — two
cells — so stated as a transformation it is `( c-addr -- c-addr xt|0 )`,
and `WORD FIND NIP` leaves exactly `xt` with **no underflow**.

Cell **count** is not the lie — comment and body both leave two cells.
The lie is two-fold:
1. **What the top cell means.** The comment promises an immediacy flag
   (`xt 1` immediate / `xt -1` normal / `c-addr 0` not found). The body
   keeps `c-addr` and makes the top cell the raw `xt|0`. Not-found agrees
   (`c-addr 0`); found does not (`c-addr xt` vs the promised `xt ±1`). The
   shapes agree exactly where it misleads most — a miss looks standard.
2. **Which name is looked up.** The address handed in is ignored; the
   answer is about `word_buffer`, i.e. the last parsed token. The body's
   own "just returns xt or 0" comment is accurate but stops short of the
   fact that bites.

`WORD FIND NIP` works *by accident of adjacency*: `WORD` fills
`word_buffer` and leaves its `c-addr`, `FIND` pushes `xt` above it, `NIP`
drops the `c-addr`. It reads like ANS usage and is correct for a different
reason than it appears.

## Why it is dangerous, not just wrong

A word whose comment says one thing and whose body does another does not
return a *wrong* answer — it returns a **confident answer about a
different word**. `find_` returns `0`/`xt` correctly for the token in
`word_buffer`, so a caller's found/not-found boolean often *looks* right,
which is what keeps the bug alive: it passes by accident until the address
actually matters. Presence gates are where it bites — a "is X present?"
built as `<X> FIND` answers for the interpreter's last-parsed token, and a
gate that says "present" to everything is how an install gate
(G-BOOT/G-DISK/G-SPACE class) opens on a machine that cannot boot the
result.

## The two times the name misled

Neither was a coding slip; each author wrote code correct under the
*stated* contract.

| # | Date | Where | What went wrong | Evidence |
|---|---|---|---|---|
| 1 | 2026-08-04 | interactive `WORD X FIND` at the prompt | the interpreter's fetch of the token `FIND` overwrote `word_buffer`, so every probe looked up "FIND" and gave the same answer for real and invented names | observed; `lesson_word_find_interactive` |
| 2 | 2026-09-29 | `WZ-LOADED?` in `forth/dict/firstboot.fth` (then uncommitted), compiled: build a counted string, `FIND NIP` | answered for the last-parsed token (`WZ-DRAW`), so every vocabulary read as "loaded"; the wizard's G-DISK gate passed on the lan fixture by accident (would also pass on a build without AHCI) | `tests/test_firstboot.py` check 21 (`rtl8139.fth loaded`) and check 37 red: `S" ZZZ-NEVER-DEFINED" WZ-LOADED?` gave -1 |

Occurrence 2 was worked around in the wizard by walking the FORTH chain
from `VAR_FORTH_LATEST` (0x28048) and `STR=`-comparing, instead of calling
`FIND`; check 37 turned green (37/37 both fixtures). **The kernel word is
still unfixed; the wizard routes around it.**

## Census — is anything shipped doing this? (2026-09-29)

Searched `forth/dict/*.fth` (public + paid on disk),
`~/projects/forthos-vocabularies/forth/dict/*.fth` (37 files),
`src/kernel/forth.asm`, `tests/*.py`, `tools/`.

| Caller | Form | Safe? |
|---|---|---|
| `install.fth:101` `BIND-WRITER`, `:125` `BIND-READER` | `WORD FIND NIP`, compiled | yes — `WORD` runs immediately before; `NIP` drops the retained `c-addr`, leaving `xt|0`. Correct code. |
| kernel `'` :1313, `[']` :1685, `POSTPONE` :1701, `SEE` :2115, `USING` :3409 | `call word_` then `call find_` | yes |
| kernel `INTERPRET` :1501 | `word_`, a dictionary-bounds compare, then `find_` | yes — the compare does not touch `word_buffer` |
| `test_pci_typing.py`, `test_pci_bar.py`, `test_install.py`, `test_firstboot.py` | `: DEF? WORD FIND NIP ;` | yes — compiled, per the 2026-08-04 lesson |
| private repo | no `FIND` callers | n/a |

The metacompiler targets define their own *target* `FIND` with a
different contract (`( a l -- xt flg T | a l F )`) — a different word in a
different image, not a caller of this one.

**No shipped vocabulary passes a constructed string to `FIND`.** The only
such caller was `WZ-LOADED?`, never committed. This is a latent trap, not
a live bug: the two `install.fth` callers are correct; the false comment
is dormant in shipped code. The hazard is forward — the next author who
writes `<string> FIND` trusting the comment (expecting `±1`, or `c-addr`
replaced by `xt`, or building a name rather than parsing one) gets a
confident-wrong answer.

## The owed fix (not done here — tee'd up)

**Recommendation: rename + correct the comment**, red-first.
```nasm
DEFCODE "(FIND-LAST)", FIND_LAST, 0  ; ( -- xt | 0 )
    ; Look up the name WORD (or the interpreter) parsed last, i.e.
    ; word_buffer. Reads NOTHING from the stack, returns no immediacy
    ; flag. To look up a string you hold, walk the vocabulary chain;
    ; this word cannot do it.
    call find_
    push eax
    NEXT
```
- **Name `(FIND-LAST)`** — parentheses mark a non-standard factor nobody
  should mistake for ANS `FIND`; `LAST` names the input (the last parsed
  word). Owner's suggestion; reads well as `WORD DROP (FIND-LAST)`.
- **No `FIND` alias.** Keeping the old name keeps the trap. With `FIND`
  undefined, ANS-habit code fails loudly (`FIND ?`) instead of answering
  about the wrong word.
- **Migrate:** `install.fth:101,125` and the four test `DEF?` definitions,
  mechanically `WORD FIND NIP` → `WORD DROP (FIND-LAST)` (drops the
  `c-addr` on purpose instead of relying on `NIP`).

**Metacompiler dependency — CHECKED 2026-09-30, rename is safe.** The
worry was `test_meta_compile.py:245`, which looks up `FIND` in the
metacompiled symbol table (`T-FIND-SYM`). Two "FIND" things exist and
neither is tied to the host word's name: the *target* symbol is a literal
`S" FIND" TX-CODE` (`target-x86.fth:847`), and `ADDR-FIND` is
`DEFCONST "ADDR-FIND", ADDR_FIND_FN, find_` (`forth.asm:3607`), bound to
the asm label `find_`, not the DEFCODE word. No `' FIND` tick or
`T-ALIAS … FIND` exists. So renaming `DEFCODE "FIND"` breaks neither the
meta test nor the metacompiler — the only remaining constraint is
sequencing.

**Alternative (wider blast radius):** restore the real ANS contract —
make `FIND` read `c-addr` and push `xt flag` / `c-addr 0`. Correct, but it
changes the top cell from the raw `xt` to a `±1` flag, so both
`install.fth` callers (whose `NIP` keeps that cell expecting the `xt`)
must change. Only if a genuine ANS `FIND` is wanted later.

### Blast radius to clear before landing
- Kernel image bytes change (the name grows ~7 bytes + alignment), so
  every pinned image hash moves — sequence after the HP trip, same
  constraint as the wizard branch (now merged).
- Docs that mention `FIND` as if it were ANS: grep `docs/` and correct in
  the same change. Word count (`CLAUDE.md` "222 dictionary words") is
  unchanged by a rename; `make check-kernel-size` moves by bytes.

### Red first
On the unchanged kernel, pre-register an XFAIL: `DEF? (FIND-LAST)` ≠ 0 and
`DEF? FIND` = 0 (`DEF?` compiled from whichever name exists). Add a
contract check that a counted string held on the stack is **not** what
gets looked up — the word answers for the last parsed token whatever is on
the stack. That pins the corrected comment, so a future "fix" of the body
shows up as a change rather than slipping in.

## Related

- `lesson_word_find_interactive` (updated 2026-09-29 with the compiled
  case).
- `docs/evidence/finding-wt-alloc-stale-slot-2026-09-29.md` — the
  session's other locally-worked-around substrate defect.
