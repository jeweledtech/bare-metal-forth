# FINDING — `(` typed over serial wedges the interpreter until a later `)` arrives (2026-10-06)

Recorded during 4b step 0 (TASK_BOUNDED_READS_4B §3a), on master
`127baa3` + the 4b plan doc (`0bad084`), QEMU 8.2.2, combined image,
serial `tcp:127.0.0.1`. Not fixed here; queued as a kernel item.

A prior record exists only outside the repo (a 2026-07-26 working note
that gave the same mechanism). This is the first record in the repo, with
the mechanism re-checked against the current source and a discriminating
run.

## Observed

Each case on its own fresh QEMU boot, every byte recorded for 3s after
each send.

| Case | Sent | Got back |
|---|---|---|
| A | `( c ) 9 .\r` | `( c ) 9 .\r\n` (echo only; no `9`, no `ok`) |
| A, next | `1 2 + .\r` | nothing at all, not even the echo |
| B (second fresh boot) | `( c ) 9 .\r`, then `1 2 + .\r` | the same as A: reproduces |
| C | `( c )\r` (alone, nothing after it) | `( c )\r\n` (echo only) |
| C, next | `1 2 + .\r` | nothing: `( c )` alone also wedges |
| D (control) | `1 2 + .\r` twice | `1 2 + .\r\n3 ok ` both times |

## Mechanism

`src/kernel/forth.asm:2655`, `DEFCODE "(", PAREN, F_IMMEDIATE`: in block
mode (`BLK` non-zero) it scans the block buffer for `)`. In interactive
mode it calls `read_key` until it reads a `)`. A typed line is already
whole in the TIB, so `read_key` waits for **new** input; everything sent
afterwards is consumed as comment text, without echo, until a `)` arrives.

Discriminating run (prediction written before it ran: the `)` ends the
comment, the rest of the original line is then interpreted, then the rest
of the new line):

| Case E (fresh boot) | Got back |
|---|---|
| `( c ) 9 .\r` | `( c ) 9 .\r\n` |
| `1 2 + .\r` | nothing (consumed by `read_key`, never executed) |
| `) 4 .\r` | `C ? \r\n) ? \r\n9 ok  4 .\r\n4 ok ` |
| `5 6 + .\r` | `5 6 + .\r\n11 ok ` (recovered) |

So the original line's leftover tokens ` c ) 9 .` run after the `)`
(`c` upper-cased: `C ?`; `) ?`; `9`), and any command sent while wedged is
**silently lost**.

## Does any test send `(` over serial?

Scanned every string constant in the 51 recipe-run scripts (Python `ast`)
for a bare `(` token (`(` with whitespace or line end on both sides; so
`.(` and `(BUF)` are not hits). The detector found 3 of 3 planted
positives and 0 of 3 negatives first.

- 79 hits, none sent to the guest in interpret mode: check labels such as
  `f'{name} ({expr} = {want})'`, progress prints such as `Loading X86-ASM (`,
  docstrings, and error text. test_install.py:901's first argument is a
  check name; the command it sends is `f'{lba} GPT-PERMIT?'`.
- tests/test_block_reload.py:115-122 put `( BUG34 BLOCK A )` and similar
  into **blocks** that are loaded with `LOAD`: block mode, which scans the
  buffer. test-block-reload passes 12/12 (B1, 2026-10-06), which is
  consistent: block-loaded `(` works.

No recipe-run script sends `(` in interpret mode over serial, so no passing
test contradicts this finding.

## Queued (kernel item)

Interactive `(` should end at the `)` in the TIB (or at the end of the TIB
line) instead of reading keys. The fix needs its own red (case A as a test)
and a check that the block-mode path is unchanged. Owner places it in the
queue.
