# (bl) the hardware criterion: the drivers it empties, read before the edit (2026-09-24)

**Status: read, not edited.** The owner's ruling was premised on 3 drivers.
The ruled change empties **133**, so this comes back before the vocabulary is
touched.

## The criterion (a standard created 2026-09-24, not recovered)

**"Hardware" means the function *issues* a hardware access:** it reads or
writes a port, MMIO, a device register, or a structure the device itself
reads. **Participation is not access.** The reason is what the label is for.
When ForthOS prints "hardware" it tells someone porting a driver: *this is a
place you must reimplement against the real machine.* Nobody knows the
original author's rule; this one is ours, and it is labelled as created.

**Ruled application:** `MmBuildMdlForNonPagedPool`, `IoAllocateMdl` and
`IoFreeMdl` leave the hardware block. They go to their own scaffolding value
for buffer/descriptor setup, **not** to unclassified.

## The premise moved: 3 → 133

"The three drivers that lose every hardware function" came from the
**single-name** counterfactual (MmBuildMdlForNonPagedPool alone). The ruled
change moves **all three names**. Its counterfactual is a scratch build on the
fixed discovery, **3 lines** from the shipped source, with MEMORY_MGR standing
in for the new scaffolding value (any scaffolding value gives the same
buckets). Binary `5e99e7af…`, run over the 1,322 with 0 empty outputs:

| | |
|---|---|
| drivers whose buckets change | **433** |
| hardware functions leaving the block | **3,998** of 14,738 (**27%**) |
| scaffolding / unclassified | +4,732 / −734 |
| **drivers emptied of every hardware function** | **133** |

**Included: the HP eight's `disk.sys` (hardware 3 → 0).** So the HP "320
hardware functions" figure would become 317.

## The 133, read

The owner's test: if they genuinely issue no hardware access, the criterion
is working. If any does, that is a different defect with its own letter, and
not a reason to widen the criterion.

**Instrument** (`bl_read_emptied.py`), for each driver:
- every `in`/`out`/`ins`/`outs` instruction in the binary (objdump);
- every import in a hardware category other than the three moved names;
- every code reference to such an import's IAT slot.

**Control, positive, run first:** HP `serial.sys` (137 I/O instructions, 8
hardware imports referenced), `i8042prt.sys` (2 and 8), `ACPI.sys` (23 and
10). The instrument sees hardware where it exists.

**Result on the 133: 0 with any I/O instruction, 0 importing any other
hardware-category name, 0 referencing one.**

| kind (a reading of the names) | examples |
|---|---|
| storage class and volume drivers | disk, volsnap, volmgr, uaspstor, sbp2port, EhStorClass, vmstorfl |
| filesystems and file-level filters | cdfs, npfs, cimfs, filecrypt, p9rdr |
| network protocol and miniport-over-USB | netbios, rasl2tp, raspptp, nwifi, RNDISMP, rndismp6, usb8023, bthpan |
| HID over another transport | mouhid, hidbth, hidir, hidinterrupt, VMBusHID, vhf |
| virtual, remote and framework | vmbusproxy, dmvsc, rdpdr, TsUsbGD, Ucx01000, SpbCx, ksthunk |

**Under the criterion, the label is working.** Each of these hands buffers to
a lower driver and touches no device itself. The MDL calls were the only
thing that made them print as hardware.

**What the read cannot see, stated:** an access through a pointer the driver
received from elsewhere, and a hardware import reached by a path the analysis
misses (as `(bk)` shows can happen). The instrument reads code references to
IAT slots anywhere in the binary, not only attributed calls. So `(bk)`-style
blindness would not hide a *referenced* import from it. It found none.

## What has to happen before the edit, and why it is not done yet

1. **The owner ruled on 3 and the change empties 133,** including an HP-eight
   driver. The principle does not depend on the count. But a change that
   moves 27% of the hardware block and edits a figure from the HP work
   (320 → 317) is not what was priced. It comes back for confirmation.
2. **The vocabulary hash `b48923e8…` changes.** Assertions of it, per rule
   24: **0** in tests and scripts. One header comment
   (`semantic.h`, the precedence note) and **6** evidence documents cite it
   as the frozen hash. Those cite a historical freeze, which stays true of
   its date. The header comment changes with the edit.
3. **The new value.** `SEM_CAT_BUFFER_SETUP` (report name `BUFFER_SETUP`,
   drop reason `BUFFER-SETUP`), **appended** to `SEM_SCAF_LIST`, since the
   order is frozen. The name is proposed, not yet used.
4. **Pre-registration:** the must-not-move and should-move sets, from this
   counterfactual. The should-move is 433 drivers, −3,998 hardware and 133
   emptied, as the prediction the real edit must reproduce. Because it would
   be copied from a run of the same edit, it is **a replication check, not
   an independent prediction**, and it will be scored that way.
