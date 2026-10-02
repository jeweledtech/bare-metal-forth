# Finding: WT-ALLOC never clears a widget slot; a digit key can run a stale XT

**Date:** 2026-09-29
**Found by:** code reading while building the first-boot wizard
(`forth/dict/firstboot.fth`), not by a failure
**Substrate:** `forth/dict/ui-core.fth` (`WT-ALLOC`, `ADD-LABEL` and the other
`ADD-*` words), `forth/dict/ui-events.fth` (`BUTTON-ACTIVATE`)
**Status:** OPEN. Not fixed. Worked around locally in FIRSTBOOT only.

---

## 1. What the code says (reasoned)

`WT-ALLOC` (ui-core.fth) bumps `WT-COUNT` and points `W-ADDR` at the next
64-byte slot. It does not clear the slot:

```forth
: WT-ALLOC ( -- flag )
  WT-COUNT @ WT-MAX < IF
    WT-COUNT @ WT-ESIZE *
    WT-BASE + W-ADDR !
    1 WT-COUNT +!  TRUE
  ELSE  FALSE  THEN ;
```

`WT-RESET` zeroes the counters and leaves the table memory at `WT-BASE`
(0x200000) untouched. Of the `ADD-*` words, only `ADD-BUTTON` writes the XT
field (`WTO-XT`, offset 12). `ADD-LABEL`, `ADD-DIVIDER`, `ADD-INPUT`,
`ADD-DROPBOX`, `ADD-CARD-BG`/`-ED` and `ADD-MENU-BTN` leave offset 12 holding
whatever the previous form stored there.

`BUTTON-ACTIVATE` (ui-events.fth) maps digit key *n* to the *n*-th visible,
enabled button. `BA-IDX` starts at 0 and is set only on a match. When *n* is
larger than the number of buttons, nothing matches, and the word executes the
XT of **widget 0**, whatever type widget 0 is:

```forth
  BA-IDX @ WT-ESIZE *
  WT-BASE + WTO-XT + @
  DUP IF EXECUTE ELSE DROP THEN ;
```

Put together: if widget 0 of the current form is not a button (every form in
the tree starts with a title label), and slot 0 last held a button in an
earlier form, then pressing a digit past the last button runs that earlier
form's button action. The `DUP IF` guard makes it safe only when the stale
cell happens to be 0.

## 2. Pre-registered experiment (written before the run)

Image: `build/bmforth.img` from main (bmforth 848971e1), booted from floppy
with `snapshot=on`. Serial on port 4777. UI-CORE and UI-EVENTS are embedded.

Setup: `VARIABLE HIT  : SETHIT 1 HIT ! ;`. Form A puts a button whose XT is
`SETHIT` at index 0. `WT-RESET`, then form B puts a label at index 0 and a
button with XT 0 at index 1. Form B is the shape of every real form.

| # | Action on form B | Prediction | Why |
|---|---|---|---|
| P1 | `57 BUTTON-ACTIVATE` (digit 9, one button) | `HIT` = 1 | no match, runs widget 0's stale `SETHIT` |
| P2 | `50 BUTTON-ACTIVATE` (digit 2, one button) | `HIT` = 1 | same path, smallest overshoot |
| C1 | `49 BUTTON-ACTIVATE` (digit 1) | `HIT` = 0 | matches button B, XT 0, guarded |
| C2 | zero slot 0's XT, then `57 BUTTON-ACTIVATE` | `HIT` = 0 | the guard holds when the cell is 0 |

P1 and P2 turning out 0 would falsify §1. C1 or C2 turning out 1 would mean
the instrument is wrong, not the code.

## 3. Outcome

(Filled in below after the run. Nothing above this line was edited after it.)

Run 2026-09-29 on main's `build/bmforth.img`, sha256 prefix 848971e1,
`snapshot=on`, serial 4777. Before the probes: `WT-COUNT` = 2, widget 0 type
= 1 (`WT-LABEL`), widget 0's XT cell = 375804, and `' SETHIT` = 375804. So the
label at index 0 carries form A's button XT, byte for byte.

| # | Prediction | Observed |
|---|---|---|
| P1 | 1 | **1** |
| P2 | 1 | **1** |
| C1 | 0 | 0 |
| C2 | 0 | 0 |

The interpreter was alive afterwards (`7 6 *` = 42). **§1 is confirmed as
observed.** A digit key past the last button runs whatever XT the previous
form left in slot 0. Here that was a harmless flag setter. In a real session
it is some earlier panel's button action (a notepad Save, a hello-app Hide),
run on the wrong form.

## 4. Reach

- Every form built with `FORM-LOAD`/`FORM-WIRE` or the `ADD-*` words, run
  under `FORM-RUN`, is exposed: `HANDLE-KEY` sends keys `1`-`9` to
  `BUTTON-ACTIVATE` whenever the focused widget is not an INPUT.
- It is reachable from one keypress. It needs no unusual state beyond having
  run a different form earlier in the session, which is the normal case.
- Any stale non-zero cell can be executed, including one that is not an XT at
  all (a table built over memory last used by something else). That path is
  reasoned, not observed: the run above only showed a real XT being reused.

## 5. Proposed fix (substrate, not applied)

Two independent defects. Fix both, because either alone leaves a hole:

1. **Clear the slot on allocation.** `WT-ALLOC` zeroes the 64-byte slot
   (`W-ADDR @ WT-ESIZE 0 FILL`) before returning TRUE. Every `ADD-*` word then
   starts from a known slot, and a label's XT is 0.
2. **No match means no action.** `BUTTON-ACTIVATE` starts `BA-IDX` at -1 and
   returns without executing when it is still -1. Falling through to widget 0
   is the root of the dispatch error. Clearing slots only makes it harmless.

Red first: the §2 setup as a UI-EVENTS suite check. P1 must read 0 after the
fix, with C1 (digit 1 still activates button 1) as the should-not-move
control.

## 6. Local workaround in FIRSTBOOT

`WZ-LBL` writes `0 W-XT!` after every `ADD-LABEL`, so the wizard's widget 0
(always its title label) holds XT 0 and the fall-through is a no-op. That
covers the wizard only. It does not fix the substrate, and a form whose
widget 0 is created by another `ADD-*` word would still be exposed.
