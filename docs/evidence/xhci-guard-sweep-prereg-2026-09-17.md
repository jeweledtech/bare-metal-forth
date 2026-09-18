# Pre-registration: page-pointer cell guard sweep (2026-09-17)

Written BEFORE the red run. Outcome appended below the line.

## Why (owner filing, 2026-09-16)

Second physical-0 write in eight days, same shape: a word dereferencing
a page-pointer VARIABLE without checking it is bound. 3D (2026-09-13):
`BUILD-ICTX` with XICTX unbound zeroed page 0. 2026-09-16 (probe 1,
`xhci-4-diag55-2026-09-15.log`): `ENABLE-SLOT` → `CMD-ENQ` with XCRING
unbound wrote its command TRB at physical 0 (0x2400 landed at 0xC, the
IVT). The 09-11 guard sweep covered five words for `XHCI-BASE @ 0=`
only; it never covered the page cells. Two incidents is a class.

## Audit (code read 2026-09-17, forth/dict/xhci.fth; script output banked in the session record)

Words that dereference a page cell AND write through it, with NO entry
guard on that cell:

| word | cell(s) | what it writes | reachable from a card? |
|---|---|---|---|
| `CMD-ENQ` ( plo phi sts ctl -- ) | XCRING | 16-byte TRB + link TRB | via every command word |
| `CMD-RUN` ( plo phi sts ctl -- cc slot ) | XCRING (via CMD-ENQ), then DOORBELL0 + EV-WAIT on XERING | TRB, doorbell, ERDP | ENABLE-SLOT / DISABLE-SLOT / CONFIGURE-EP / STOP-EP / EVAL-MPS: all card words |
| `TRB-NOP!` ( -- ) | XCRING | NOP TRB | NOP1 / NOP-TEST (card) |
| `BUILD-ICTX` ( port# speed -- ) | XICTX | PG0 + context dwords | 3D contamination |
| `EVAL-MPS` ( mps -- cc ) | XICTX | PG0 + dwords, then a command | card localization |
| `EP0-ENQ` ( plo phi sts ctl -- ) | XEP0R | TRB | via GET-DESC / SET-CONFIG / GET-CONFIG / SET-PROTOCOL |
| `GET-DESC`, `SET-CONFIG`, `SET-PROTOCOL` ( .. -- cc ) | XEP0R (via EP0-ENQ) | TRBs, doorbell | card 8.1 by hand |
| `BUILD-EPCTX` ( -- ) | XICTX (reads XODC, XEP1R) | PG0 + dwords | internal, but pasteable |
| `CONFIGURE-EP` ( -- cc ) | XICTX (pointer handed to the controller) | a Configure with input ctx 0: the controller READS phys 0 (hazard 1) | card 8.1 / 10.2 by hand |
| `STOP-EP` ( dci -- cc ) | XCRING via CMD-RUN | TRB | card 10 |
| `EP1-ENQ` ( plo phi sts ctl -- ) | XEP1R | TRB | via HID-POLL (guarded) |

Read-only dereferences (`SLOT-STATE`, `CR-TRB`, `EV-TRB`) and the
release paths (`SLOT-FREE`, `HID-REL`, `XUP-FAIL`, `XHCI-DOWN`, which
test each cell inline) are out of scope. Already guarded at entry:
`XHCI-UP`, `ENUM-ADDRESS`, `SLOT-DOWN`, `ENUM-CONFIGURE`, `CFG-STATE`,
`HID-POLL`, `ENUM-HID`, `HID-DOWN`.

## Refusal conventions (pass states, one per word)

Each word refuses when its cell reads 0, consuming its arguments and
returning its "nothing happened" value, and touches no memory:
`CMD-ENQ`/`EP0-ENQ`/`EP1-ENQ` drop 4; `CMD-RUN` → 0 0 (the existing
timeout convention) WITHOUT ringing the doorbell or polling the event
ring; `TRB-NOP!`/`BUILD-EPCTX` return; `BUILD-ICTX` drops 2;
`EVAL-MPS`/`GET-DESC`/`SET-CONFIG`/`SET-PROTOCOL`/`CONFIGURE-EP`/
`STOP-EP` → 0. A refusal at CMD-RUN's entry (not only CMD-ENQ's) is
required: otherwise the doorbell write and the event poll on an unbound
XERING still happen.

## The check (suite phase 13, after phase 12's teardown)

After phase 12 every page cell is 0 by the words' own teardown
(XHCI-DOWN / SLOT-DOWN / HID-DOWN): the natural hazard state, the
same one probe 1 reproduced. A suite word `PSUM` sums the 16 dwords at
physical 0..0x3C. For each word above: PSUM before, call the word with
harmless arguments, PSUM after; the check passes iff the return value
is the refusal value AND PSUM is unchanged. One check per word (13),
plus one DEPTH-unchanged control across the whole phase: **14 new**,
predicted **305 → 319**, read from the log's line count.

Predicted red on HEAD: 13 red (each word writes physical 0 today, so
PSUM moves; several also return garbage instead of the refusal value),
the DEPTH control green on red (the words consume what they are given
today too). BASE tripwire stays last.

Named alternative: a word whose PSUM does NOT move on HEAD is either
already guarded (the audit missed it) or writes somewhere other than
physical 0 (worse: find where). Either way, stop and read the word.

## Fix (green, after the red is banked)

One entry-guard line per word in `forth/dict/xhci.fth`, no other
change; the suite's existing 305 must not move. Green predicted
319/319.

## Red run 1: prediction MISSED, instrument corrected (before the outcome)

`xhci-guard-red-2026-09-17.log` (renamed `…-run1-narrow-window.log`):
**315/319**, 4 red not 13. Reasoned cause (from the code, NOT yet
observed): the nine "passing" words write outside the 64-byte window.
`CMD-ENQ` writes at `XCRING @ XENQ @ 10 * +`, and `XENQ` is not reset
by `XHCI-DOWN`, so with the cell at 0 the TRB would land at `XENQ*16`
inside page 0 (probe 1 saw offset 0xC because `XENQ` was 0 on a fresh
boot); `EP0-ENQ` likewise via `XEP0ENQ`; every word routed through
them inherits the offset. `EP1-ENQ` was caught only because `HID-DOWN`
resets `XEP1ENQ` to 0. Instrument corrected: `PSUM` covers the whole
4096-byte page 0 (a defect-revealing change: it removes a blind spot
and hides nothing), and the phase prints the three enqueue indices at
entry so the predicted offsets can be checked against the observed
ones. Red run 2 carries the ORIGINAL prediction: 13 red, DEPTH control
green. If any of the nine still passes with the full-page window, the
reasoned cause above is wrong for that word: stop and read it.

---

## Red run 2 (full-page checksum): OUTCOME

`xhci-guard-red-2026-09-17.log`: **306/319**, exactly the original
prediction: 13 red (every word moved the page-0 checksum), the DEPTH
control green on red. Enqueue indices at phase entry `XENQ 5, XEP0ENQ
4, XEP1ENQ 0` (HEX): the command TRBs landed at 0x50 and the EP0 TRBs
at 0x40, just past the 64-byte window of run 1. The reasoned cause is
now observed for all nine words that had slipped through. Every
refusal VALUE was already right on HEAD (0 / 0 0 / no return): the
words return their timeout value while writing physical 0, which is
the "plausible answer from a wrong write" shape. Guards follow.

## Green: OUTCOME

Fourteen one-line entry guards in `forth/dict/xhci.fth` (the thirteen
audited words plus `GET-CONFIG`, the one other `EP0-ENQ` caller, same
class), no other change. `xhci-guard-green-2026-09-17.log`: **319/319**
derived, exit 0; the 305 existing checks unmoved; every refusal now
leaves the page-0 checksum unchanged with the same enqueue indices
(5/4/0) that placed the writes in red run 2. Lines ≤ 64, lint clean.
Still unguarded, named: `EP0-BELL`/`EP-BELL`/`DOORBELL0` write
`DB-BASE + slot*4`, which depends on `XHCI-BASE` (the 09-11 sweep's
cell, not a page cell); with a bound base they are MMIO writes. Out of
this sweep's scope, recorded.
