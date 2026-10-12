# TASK — HAL slice 1: the binding mechanism and the display contract (2026-10-12)

Owner, 2026-10-12: the adaptive HAL (a "binding layer"; design in the
project notes as ADAPTIVE-HAL.md) starts now, interleaved with the queue.
Slice 1 replaces the one-off screen-target cell: HAL-VECTOR, BIND,
HAL-LIST (an unbound vector aborts with a named message; HAL-LIST feeds
RELOAD-VOCAB's vector checks), and the display contract (FB-BASE and what
the forms need), bound to 0xB8000 on BIOS and to the shadow plus the
framebuffer flush on UEFI, chosen from BOOT-MODE. The contract vocabulary
is embedded; its pad cost is reported. Gates: an OVMF screenshot shows a
form, BIOS screens unchanged, a live rebind at the prompt takes effect on
the next call, direct @ ! PC@ PC! untouched.

## 1. Audit (2026-10-12, read from the tree)

**Kernel words:** no DEFER, no IS. `>BODY` exists (forth.asm:2756).

**Vector-style bindings that exist today:**

| binding | where | how it is set | RELOAD-VOCAB checks it (RL-VECTORS) |
|---|---|---|---|
| block writer, BLK_WRITE_VEC 0x2809C | kernel cell | BLK-WRITER! / BLK-WRITER@ | yes |
| persistent reader, BLK_READ_VEC 0x280A0 | kernel cell | BLK-READER! / BLK-READER@ | yes |
| ABORT-HOOK, 0x280A4 | kernel DEFVAR | `!` (CATALOG-RESOLVER sets CR-ABORT) | yes |
| IRQ hook table, 0x29C00, 16 slots | kernel | `!` per slot | yes (table) |
| the IDT | kernel | gates | yes |
| 'RESOLVE-DEPS | CATALOG-RESOLVER | `!` (mutual recursion) | yes |
| 'FILE-SINK | FILE-STREAM | `!` | yes, by name at run time |
| FE-SAVE-XT, FE-OPEN-XT | FILE-EDITOR-CORE | `!` | yes, by name |
| SEC-WRITE-VEC, SEC-READ-VEC | INSTALL | `!` | yes, by name |
| WZ-SPACE-XT | FIRSTBOOT | `!` | yes, by name |
| 'WZ-S2 | FIRSTBOOT | `!` | no: it points inside FIRSTBOOT itself, so the two are freed together (not a gap) |
| catalog registry, widget registry, widget table | CATALOG-RESOLVER, GUI-HARVEST, UI-CORE | tables | yes (RL-TABLE, RL-WIDGETS) |

**The display today** (from the uncommitted one-off, which slice 1
replaces): the kernel's `vga_base` cell (0xB8000, or the text shadow at
0x80000 on a UEFI boot with a framebuffer), `SCREEN` and `SCREEN-FLUSH`,
the flush in the key wait and in RAW-SCAN, and the VGA palette. Its gate
(OVMF: the form and the editor on the framebuffer, all 2,000 cells, with
inverse video; SeaBIOS: the same text at 0xB8000) passed in four runs.

## 2. Design note

**Checked against forth.asm first (as ADAPTIVE-HAL asks):** CREATE, `'`,
`[']`, >BODY, ABORT, EXECUTE, TYPE, CELLS exist; **DOES> does not** (nor
COUNT, a known gap), so the sketch's `CREATE ... DOES> @ EXECUTE` can't be
built in Forth on this kernel. `'` parses its name from the input (the
old lodsd tick, bug #21, is gone), so `: BIND ' >BODY ! ;` works as
sketched.

- **The mechanism, in the kernel (smallest substrate change):**
  `HAL-VECTOR ( "name" -- )` lays down a word whose code field is a new
  runtime, DOVEC: it fetches the bound XT from the word's first body cell
  and enters it exactly as NEXT would (one fetch, one jump: the cost the
  design names). Body: [bound xt | header | next vector]. Unbound (xt 0):
  `<name>: HAL vector not bound`, then the same abort path an undefined
  word takes (definition rollback, input discarded, ABORT-HOOK, so a
  block-load in progress rolls back). `HAL-HEAD ( -- addr )` is the head
  of the chain of every vector, newest first. General DOES> is a bigger
  compile-time change and isn't needed for slice 1.
- **The contract vocabulary, HAL (hal.fth), embedded first after
  HARDWARE, free tier:** `BIND ( xt "name" -- )`, `HAL-SET ( xt vxt -- )`,
  `HAL-GET ( vxt -- xt )`, `HAL-NAME ( vxt -- addr len )`, `HAL-LIST`
  (every vector, its name and what it is bound to). The binding table is
  the chain behind these accessors; nothing else reads its layout.
- **The display contract:** `FB-BASE ( -- addr )` (the text screen
  memory) and `FB-FLUSH ( -- )` (make the screen show it). Bound at boot
  from BOOT-MODE: UEFI with the framebuffer console on -> the kernel's text
  shadow (SCREEN) and SCREEN-FLUSH; otherwise -> 0xB8000 and a no-op. (A
  UEFI boot whose framebuffer didn't come up keeps print_char on 0xB8000,
  so the forms follow it there.)
- **The consumers call the contract each time:** UI-CORE's and the
  block editor's VGA-BASE and FILE-EDITOR-CORE's FE-VGA become colon words
  calling FB-BASE (not constants taken at load), so a rebind takes effect
  on the next draw; RAW-SCAN's wait calls FB-FLUSH. The kernel's own
  console (print_char, the key-wait flush) stays below the contract.
- **RELOAD-VOCAB:** RL-VECTORS walks the vector chain and refuses a reload
  that would free code any vector is bound to, naming the vector.
- **Direct access untouched:** @ ! C@ C! W@ W! and the port words INB
  INW INL OUTB OUTW OUTL (the design's PC@ / PC!) keep their bodies; a
  host check asserts they call nothing.
- **K4 (test-pad-move)** measured "the pre-move list against today's
  list"; adding hal.fth to today's list would read as the move shrinking.
  It now builds the pre-move side as today's list plus the six moved
  files, so it measures the move alone, whatever is added later.

**Gates:** a new test-hal (BIOS image): HAL-LIST shows both display
vectors bound; FB-BASE = 0xB8000; an unbound vector aborts the line with
its name, DEPTH 0; a live rebind at the prompt changes FB-BASE and
UI-CORE's VGA-BASE on the next call, and binding back restores them;
RELOAD-VOCAB refuses to free code FB-FLUSH is bound to, naming it; the
host check on @ ! C@ C! W@ W! INB INW INL OUTB OUTW OUTL. test-uefi-boot
keeps the screen gates
(OVMF: form and editor on the framebuffer, all cells; SeaBIOS unchanged)
and reads FB-BASE from the contract. Pad cost reported.

## 3. Results

Evidence: ~/forthos-evidence/2026-10-12-hal-display/ (predictions written
before each run, logs, the replaced one-off as one-off-screen-cell.diff).

**Red** (the one-off screen cell, green in a 36-minute make -k; test-hal
new): run 1 had two faults in my test, not in the tree: D1 named PC@ and
PC!, which this kernel doesn't have (its port words are INB INW INL OUTB
OUTW OUTL), and Q6 used HELLO-APP, whose reload is refused anyway for its
widget registrations (a MIRROR probe reloads cleanly, so it became the
control, Q6a). Run 2, every result as predicted: D1, Q4b, Q6a, Q7 PASS;
Q1-Q5 and Q6b FAIL (`HAL ?`, `HAL-VECTOR ?`, `BIND ?`).

**Green**, two more faults of my own on the way, both in Q6b: MIRROR's
load ends with ONLY FORTH DEFINITIONS, so BIND wasn't found and nothing was
bound (a binding that fails now stops the run as INSTRUMENT FAIL); then my
saved-binding constant, compiled after MIRROR, blocked the reload for that
reason alone (it's saved before MIRROR loads now). Then 10/10, three runs,
8.6 s each; T_HAL 20:

| check | result |
|---|---|
| D1 @ ! C@ C! W@ W! INB INW INL OUTB OUTW OUTL call nothing | PASS |
| Q1 HAL embedded, there at boot | PASS |
| Q2 HAL-LIST: `FB-FLUSH -> 318D0`, `FB-BASE -> 318AC` | PASS |
| Q3 FB-BASE = B8000 on BIOS | PASS |
| Q4 `HAL-VECTOR XQ-TEST  XQ-TEST 1 2 + .` -> `XQ-TEST: HAL vector not bound`, no `3`; Q4b DEPTH 0 | PASS |
| Q5 live rebind: FB-BASE and UI-CORE's VGA-BASE both 12345 on the next call; bound back, both B8000 | PASS |
| Q6a MIRROR reloads with nothing bound into it (control) | PASS |
| Q6b with FB-FLUSH bound to MIRROR-BLK: `MIRROR: RELOAD-VOCAB refused, FB-FLUSH points into it` | PASS |
| Q7 DEPTH 0 | PASS |

test-uefi-boot with the forms on the contract: all its gates pass, U5/L5
now reading FB-BASE (OVMF 80000, SeaBIOS B8000), S1/S2 0 of 2,000 cells
differ (50.6 s). test-gui 14/14 (the forms on BIOS), test-pad-move 19/19
(K4 now measures the six moved files alone: shrank 14,372 B, the same as
before hal.fth was embedded).

**Pad cost:** 1,045 B (12,309 -> 11,264 B free): hal.fth's 702 B in the
boot stream, the kernel's DOVEC, HAL-VECTOR and HAL-HEAD, and the
consumers' call-through words and RL-HAL.

**Owner's to decide (not done here):** the DECISIONS.md amendment, and
amending ADAPTIVE-SHELL.md and ARCHITECTURE-BUSES.md ("no HAL") to the
binding-layer language. The code says "binding layer"; the vocabulary and
its words keep the design's HAL names.
