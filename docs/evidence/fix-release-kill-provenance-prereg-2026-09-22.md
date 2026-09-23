# The release-API kill and park provenance: pre-registration (2026-09-22)

**Written before either exists.** Owner's order: the release kill first, then
provenance, then the lifter repair. Outcomes go BELOW the line, from the
artefact only.

## Two corrections to the ruling, from the source (rule 31)

**1. "No park is lost; if one is, the byte-read that cleared it was
wrong."** The walk goes in *address order*, not by path. The three `scsiport`
parks were read against the bytes and are real **on their real path**, which
never unmaps. But the walk's address-order route crosses
`MmUnmapIoSpace(RDI)` in the failure block. A kill keyed on the call fires on
that route whatever the real path does. **By the source, exactly those three
parks are lost, one per machine**, and the byte-read stands. Measured with
the diagnostic walk (scratch only, outcome-matched to the census): the walks
that reach `MmUnmapIoSpace` **with the base in RCX** number 0 / 19 / 21 / 22.
Of those, exactly one per machine is a park today (`scsiport`), and the
rest are `none` (12 / 13 / 14) or couldn't-tell (6 / 7 / 7).

**So the two items are coupled, and taking them in order would publish a
false strong claim.** A kill alone would report `scsiport`'s real park as "a
store of a freed pointer". That is only honest if the report also says the
route to it was not a real path. **The release stop is therefore built to
carry provenance** (below), and the two land in one fix.

**2. "The decoder names `mov %cr8`; the lifter drops the operand."** Read
from a probe at `2a12927`: `44 0F 20 C3` decodes as **`X86_INS_UNKNOWN`** (id
0, with both operands decoded) and lifts to `unknown`. `0F 95 C1` decodes as
`X86_INS_SETCC` and lifts to `unmodelled`. **The CR move is a decoder gap and
the `setne` is a lifter gap; one repair does not discharge both.** The
lifter repair covers `setne` (9 stops) and serial's two parks. The 12
`mov %cr8` stops need the decoder to name `MOV CR`, which is registered
separately when the lifter repair is pre-registered.

## The design

**Release kill.** At a CALL whose target is the `MmUnmapIoSpace` import
**and whose first argument (RCX) holds the base**, that is, a release of
*this* region, every register holding the base moves to a **released** set,
whatever its register class, and stops holding it. The walk continues. A
later STORE of a released register ends the walk as
**`park_after_release_at`**: a store of the region's base after the region
was released, which is not a park. Copies and writes apply to the released
set as they do to the held set. When neither set holds anything, the walk
ends as `none`. An unmap whose RCX does not hold the base releases some
other region and kills nothing. Only `MmUnmapIoSpace` is keyed, because it
is the pair of the tracked mapping APIs (`MmMapIoSpace`, `MmMapIoSpaceEx`).

**Provenance.** The walk's route is a real execution path **as long as it
has crossed no unconditional JMP**. It falls through conditional branches
(the not-taken edge is real) and stops at RET, but the instruction after a
JMP in address order is not reached from the JMP. Every park and every
after-release stop carries **`park_route`: `"path"`** or
**`"address_order"`**. Not detected, and stated as a limit: a CALL that does
not return, which would also make the continuation unreal (none was crossed
in the ABI stop's census).

## Predictions

| # | prediction |
|---|---|
| K1 | HP: all twelve outcomes unchanged (no HP walk reaches an unmap with the base in RCX) |
| K2 | **parks lost: exactly 1 / 1 / 1 off HP, `scsiport`**, each becoming `park_after_release_at` with `park_route: "address_order"` |
| K3 | new `park_after_release_at` per machine: **at least 1, at most 19 / 21 / 22** |
| K4 | no couldn't-tell or `none` becomes a park (the kill only removes holders); couldn't-tell can fall only by becoming `park_after_release_at` |
| P1 | HP: **8 parks `path`, 1 `address_order`**: pci `1C0068DCB` (`-0x20` frame), whose window crosses `jmp 0x1c0068e9b` at `1c0068de4` before its park (read from the bytes) |
| P2 | the seven parks created by the ABI stop: `fvevol` ×3 `path`; `scsiport` ×3 and `Netwtw08` `address_order` (from last round's byte reads; `scsiport`'s now carried by its after-release stop) |
| P3 | *a guess, marked as one:* **10–25%** of parks off HP are `address_order` |

---

## Outcome

*(below this line, from the artefact only)*

**Inputs hashed:** `bin/translator` `baad7b886c867d3a` (the pre-fix run was
`4852c9c516ec295c`). The census scripts are **v2**: `park_census_v2.py`
`ceff89c7`, `park_agg_v2.py` `6de292c5`. v1 would have filed
`park_after_release_at` as `none` without saying so, because its classifier
knows no such key. v2 adds that category and the route suffix and nothing else.
**Control:** with the route and after-release labels collapsed back to v1's
categories, v2 reproduces the pre-fix run site for site, except the three
sites below.

**(aq)/(ar):** exactly two XPASS, the two names. All three guards held:
plain park, volatile dies at a call, release of another region kills
nothing. 393 tests across 27 suites, 14 reds, the union matching.

| # | predicted | observed |
|---|---|---|
| K1 | HP outcomes unchanged | **byte-identical** once the new `park_route` key is stripped |
| K2 | exactly 1 / 1 / 1 parks lost, `scsiport`, as after-release by address order | **exactly those three**: `scsiport` `0x140003172` / `0x1C00030D8` / `0x1C0003192`, now `after_release`, route `address_order` |
| K3 | after-release: at least 1, at most 19 / 21 / 22 | **1 / 1 / 1.** The other 18 / 20 / 21 walks that reach an unmap of this region never store the base afterwards |
| K4 | nothing else becomes or stops being a park | **held**: 0 other outcome changes on any machine |
| P1 | HP: 8 `path`, 1 `address_order` (pci `1C0068DCB`) | **exactly that** |
| P2 | `fvevol` ×3 `path`; `scsiport` ×3 and `Netwtw08` `address_order` | **held** |
| P3 | *guess:* 10–25% of parks off HP are `address_order` | **wrong: 5 / 5 / 6 of 114 / 108 / 120, about 5%**. HP's 1 of 9 (11%) is the *highest* |

**Every address-order outcome, named** (the list is short enough to print
whole): Dell has `UcmUcsiAcpiClient`, `acpi`, `netvsc`, `winhvr`
(structure), `pci` (frame) and `scsiport` (after release). ASUS older has
`UcmUcsiAcpiClient`, `netvsc`, `vpci` (structure), `Netwtw08` and `pci`
(frame), and `scsiport`. ASUS newer has `UcmUcsiAcpiClient`, `acpi`,
`netvsc`, `tpm`, `vpci` (structure), `pci` (frame) and `scsiport`. None of
these has been read against the bytes, apart from the four read last round.

**A caution this fix puts in the report:** `scsiport`'s after-release
statement is **address order**, and the bytes show its real path doesn't
unmap. So the dangling-pointer reading is false for all three. The route
field is what keeps that from being published as a finding, and it is why
the two items landed together.
