# (bq) a BIOS interrupt no path reaches is not hardware: pre-registration (2026-09-24)

**Written before the fix.** Owner ruling: (bq) is small and takes the same
shape as (bo). It is folded in as a small commit and does not wait on the
extent work. Outcomes go BELOW the line.

**The change.** `semantic.c`'s BIOS-interrupt scan (`int` 0x10/0x13/0x14/0x15/
0x16/0x1A → BIOS_INT, hardware) considers only blocks reachable from the
function's entry over the UIR's fall-through and branch edges: the same rule
as (bn) and (bo), in the one place it was missing. `INT 21h` (DOS_API
scaffolding) goes through the same loop and follows the same rule.

**Reach, from the input** (`bq_reach.py`, build `e343fdb9…`): hardware
functions whose only remaining hardware evidence is such an interrupt, with
every one unreachable. **4 functions on 4 drivers.** These are the 4 that
(bo)'s v4 recount excluded.

| # | prediction |
|---|---|
| Q1 | the gate fires on exactly `sem_RED_bq_unreachable_bios_int_not_hardware`; `bios_int10h_classified_hardware` (a reachable INT) stays green; 423 tests; reds 13 → 12 |
| Q2 | hardware **−4 exactly**; buckets move on **exactly those 4** drivers |
| Q3 | report bytes change on **at least** those 4. A reachable-only DOS `int 21h` scan could also move a DOS_API function, which is not counted here, and any such driver will be named |
| Q4 | nothing else moves: X1–X3, `iat_edges` and census 0 of 539; HP unchanged at 265; UIR 0 of 12 (this is an analyzer change); dumps 0 of 16 |

---

## Outcome

*(below this line, from the artefact only)*

Build `adcbf3c1a22f1233` from private `aedec6f` (red `d2fdd6c`); before
`e343fdb9…`. Reading `bq-reports-post.tsv` (in `SHA256SUMS`); 0 empty
outputs.

| # | observed |
|---|---|
| Q1 | **held**: the gate fired on exactly the (bq) red (`fix-bq-xpass-gate-2026-09-24.log`); `bios_int10h_classified_hardware` and `dos_int21h_classified_scaffolding` green; 423 tests, 12 reds |
| Q2 | **held exactly**: hardware **−4**, moved set **equals** the 4 drivers (ClipSp ×3, iaStorVD on newer ASUS) |
| Q3 | **held**: bytes changed on those 4 only. No DOS-path mover appeared |
| Q4 | **held**: X1 0; X2 and X3 1,322 of 1,322; `iat_edges` 1,322 of 1,322; census 0 of 539; HP 265; UIR 0 of 12; dumps 0 of 16 |

**The reachability rule now covers all three writers of the hardware label
from instruction evidence:** port values (bn), the port flag (bo) and the
interrupt scan (bq). Hardware functions: **9,921**.
