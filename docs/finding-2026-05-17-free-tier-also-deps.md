# Finding: Free-Tier Build Hangs Due to ALSO Paid-Vocab Dependencies

**Date:** 2026-05-17  
**Status:** ~~Open~~ RESOLVED 2026-05-17 — Option C with FILE-EDITOR split  
**Context:** Attempted `make free` build with all 14 public-tracked vocabs

## Root Cause

When a vocab file contains `ALSO <paid-vocab>` and the paid vocab is absent:

1. `ALSO` executes fine (duplicates top of search order stack)
2. The vocab name (e.g., `NTFS`) is undefined — goes to `.undefined`
3. `.undefined` prints `? NTFS` and **resets STATE to 0** (aborts compilation)
4. Subsequent tokens in the colon definition are now *interpreted* instead of compiled
5. `;` is IMMEDIATE — executes in interpret mode, unhides the broken half-definition
6. The corrupted word becomes callable; downstream words that call it crash or loop

The cascading corruption across dozens of colon definitions causes the kernel to
hang during boot-time vocab evaluation. This is not a single-word failure — it's
a systemic corruption of the dictionary.

## Affected Files (5 of 14 public-tracked vocabs)

| File | Paid ALSO Dependencies |
|------|----------------------|
| file-editor.fth | NTFS, AHCI |
| notepad.fth | UI-CORE, UI-EVENTS, UI-PARSER, GUI-HARVEST |
| hello-app.fth | UI-CORE, UI-EVENTS, UI-PARSER, GUI-HARVEST |
| file-stream.fth | NTFS, AHCI, RTL8168 |
| file-browser.fth | UI-CORE, UI-EVENTS, UI-PARSER, GUI-HARVEST, NTFS |

## Safe Vocabs (9 of 14 — no paid dependencies)

hardware, port-mapper, echoport, pci-enum, catalog-resolver, ps2-keyboard,
notepad-form, hello-form, file-browser-form

## Design Options

### (A) Shrink EMBED_VOCABS_FREE to 9 safe vocabs

Remove the 5 problematic files from the free list. The free build becomes a
kernel + infrastructure demo (PCI enumeration, port mapping, keyboard) without
any GUI apps. Simple, no .fth changes needed.

**Pro:** Immediate fix, zero risk.  
**Con:** Free tier has nothing visual to show; the form widgets (notepad-form,
hello-form, file-browser-form) exist but no app wires them up.

### (B) Add ALSO-safe guards to the 5 app vocabs

Wrap each `ALSO <paid-vocab>` in a conditional that checks whether the vocab
word exists before calling ALSO. This requires adding a `[DEFINED]` or
`FIND`-based guard to the .fth files.

**Pro:** All 14 vocabs in free build, apps load but degrade gracefully.  
**Con:** Modifies .fth files (adds conditional compilation); every colon def
that uses a paid word still needs individual protection or the same corruption
pattern recurs inside the definitions.

### (C) Promote UI-CORE/UI-EVENTS/UI-PARSER/GUI-HARVEST to free tier

Move 4 paid vocabs to public-tracked. The only remaining paid deps would be
NTFS, AHCI, RTL8168 (hardware drivers). file-editor and file-stream still
can't be free without those.

**Pro:** NOTEPAD, HELLO-APP, FILE-BROWSER work in free tier (minus disk I/O).  
**Con:** Reduces paid tier value; doesn't fix file-editor or file-stream.

## Resolution

**Option C with FILE-EDITOR core/disk split executed (2026-05-17).**

1. UI substrate promoted to free tier: ui-core, ui-parser, ui-events,
   gui-harvest moved from gitignored (paid) to public-tracked (free).

2. file-editor.fth split into:
   - file-editor-core.fth (PUBLIC): buffer, cursor, display, keymap,
     dispatch. FE-SAVE/FE-OPEN use vectored execution (FE-SAVE-XT/
     FE-OPEN-XT variables + EXECUTE) so FE-DISPATCH's compiled
     reference resolves at runtime, not compile time.
   - file-editor-disk.fth (PRIVATE): FE-OPEN-IMPL/FE-SAVE-IMPL with
     real NTFS/AHCI I/O, wires vectors via `' word XT !`.

3. Free build (make free) includes 16 vocabs:
   hardware, port-mapper, echoport, pci-enum, catalog-resolver,
   ps2-keyboard, ui-core, ui-parser, ui-events, gui-harvest,
   file-editor-core, notepad-form, notepad, hello-form, hello-app,
   file-browser-form.

4. Still excluded from free: file-editor-disk (NTFS/AHCI),
   file-stream (NTFS/AHCI/RTL8168), file-browser (NTFS).

5. NOTEPAD and HELLO-APP load and run in free build. NOTEPAD
   operates RAM-only; Ctrl+S is a no-op (vector unwired).
   Full build wires disk vectors, restoring full functionality.
