# FINDING: DICT-SYSTEM (forth/dict/dict_system.fth) cannot load on this kernel, and its load hangs (2026-10-11)

Owner ruling 2026-10-11: write DICT-SYSTEM up as its own finding (queued
from the interpreter-correctness census).

## What was seen

The census was run on combined.img `38671d92…`
(docs/TASK_INTERPRETER_CORRECTNESS.md §1). In a fresh boot,
`S" DICT-SYSTEM" LOAD-VOCAB`:

- printed `PLACE ?`, `PLACE ?`, `?DO ?`, `COUNT ?`, `COMPARE ?`;
- never returned to the prompt within the 90 s budget (observed).

## Why

dict_system.fth is the "USING <dictionary>" design sketch from the
initial consolidation (`08eb2dc`; last touched by `f9c582b` for line
lengths). It is 450 lines, written for a fuller Forth than this kernel.
It uses words the kernel doesn't define (`PLACE`, `?DO`, `COUNT`,
`COMPARE`; the kernel's known gaps include `?DO` and `COUNT`).

Its mechanism also overlaps what the system has since built differently:
- USING is the kernel's ALSO plus execute;
- loading is catalog-resolver's LOAD-VOCAB;
- dependencies are `REQUIRES:` lines.

The hang is reasoned, not traced. An undefined word inside a definition
resets STATE, so the rest of that definition's body runs at load time.
Here that includes loop words with garbage operands
(finding-undefined-word-continues-2026-10-11.md). After the
interpreter-correctness fix, the load stops at the first undefined word
instead.

## Resolution (owner ruling 2026-10-11)

Moved to docs/design/dict_system.fth, unchanged, so write-catalog no
longer packs it into the image (it took 29 blocks of dead source, 288-316
in the layout of `38671d92…`). docs/MODULE_MANIFEST.md no longer calls it
implemented.
