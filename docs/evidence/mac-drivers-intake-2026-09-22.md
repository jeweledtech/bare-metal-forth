# Mac drivers: intake and first measurements (2026-09-22)

**Machine:** `apple_macbookpro15-1`, a slug read from `sysctl hw.model` =
`MacBookPro15,1`. The set is `/System/Library/Extensions` and
`/System/Library/DriverExtensions`, taken from that Mac as `mac-drivers.tgz`
(sha256 `edad02a6cf1a5678711b44ff784b06fbe08e256dfe917f27c17efc752246e23a`,
332,521,118 bytes).

## Intake

- **The archive arrived inside the public repo**, at `corpus/`. The
  second-line ignore rule held: `git check-ignore -v` names
  `.gitignore:165:/corpus/`, `git status` showed nothing, and no commit had
  ever touched `corpus/`. It was moved out by rename (hash identical before
  and after) to `~/corpus/apple_macbookpro15-1/`, where
  `git rev-parse` exits 128. The empty public `corpus/` was removed.
- **The listing was checked before extraction:** 11,560 entries; no absolute
  path and no `..` component; all 2,208 symlinks and 1,451 hard links have
  targets inside `Extensions/` or `DriverExtensions/`.
- **Extracted and counted:** 5,267 files (3,816 regular plus 1,451 hard
  links), 4,085 directories and 2,208 symlinks, each equal to the listing.
  Manifest: 5,267 sha256 lines, 933,233,985 bytes, manifest hash
  `ee07a274c92d2594141bdcaa2ef781f7477baa0cd6d02017a4de57eb6dc9474d`.
  It verifies.
- **Proof afterwards:** 0 tracked changes in either repo; no PE or Mach-O in
  the public tree except the ignored test controls; no Mach-O in the private
  tree.

## 1. How many kexts and dexts carry x86-64 code

| | bundles | with an x86-64 Mach-O |
|---|---|---|
| `.kext` (top level) | 660 | **0 kext executables**: 650 declare `CFBundleExecutable` in `Info.plist`, and **none of the 650 is present** |
| `.dext` | 17 | **17** (all `MH_EXECUTE`) |

The Mach-O files that are in `Extensions/` (93 across all bundle kinds) are
userland helpers: dylibs, bundles, plugins, and nine helper executables
inside kexts. **None has the kext file type.** On this macOS the kext code is
not in `/System/Library/Extensions`. **Reasoned, not yet seen:** it is
prelinked into kernel collections under `/System/Library/KernelCollections`,
and the kernel itself is under `/System/Library/Kernels`. So the kext
measurements need those files, not this directory.

## 2. How they bind, read from the load commands

**Dexts** (17 of 17): `MH_EXECUTE`, with `LC_LOAD_DYLINKER`, so they are
loaded by dyld. They bind through `LC_DYLD_CHAINED_FIXUPS` with `__stubs` and
`__got`, against DriverKit's frameworks: `DriverKit` and `libc++` (17 each),
`SerialDriverKit` and `USBDriverKit` (8 each), `NetworkingDriverKit` and
`PCIDriverKit` (6 each). **For dexts, the analogue of the PE import table is
the chained-fixup and stub binding.** Kexts could not be read, because no
kext binary is in the set.

## 3. The decoder on driver code (dexts only)

The same harness and definitions as the Windows and Mac-userland figures
(`park-census-cross-vendor-2026-09-22.md` §5): each binary's x86_64 `__text`,
swept linearly, with `int3` padding separated.

| set | files | instructions | `int3` padding | UNKNOWN excl. padding | pooled | median |
|---|---|---|---|---|---|---|
| **dexts** | 17 | 759,907 | 3 | 13,343 | **1.76%** | **1.00%** |
| Mac userland (for reference) | 621 | 21,231,893 | 219 | 732,798 | 3.45% | 2.56% |
| Windows, HP | 8 | 381,739 | 45,032 | 7,041 | 2.09% | 2.03% |

**The system family in the dexts:** **0 two-byte system instructions**
(no CR, DR, MSR, CPUID or descriptor-table form). The one-byte hits (`CLI`
93, `OUT` 90, `STI` 57, `IN` 52 …) are in userspace code, so they are the data
misread shown in `system-family-census-2026-09-22.md` §3, and they are not
counted.

**What that means for the product.** *Observed:* 17 dexts, no register
instruction. *Reasoned, from DriverKit's design:* the model reaches
hardware through framework calls, not register instructions, so a dext
carries no direct register access to read. In a
dext, the driver's device protocol lives in the arguments to DriverKit
calls, as it does in the HAL imports of a Windows driver. The kernel
collections will say whether kexts differ.

---

# The kernel collections (2026-09-22, second archive)

**Intake.** `mac-kernel.tgz` (sha256
`bdc8a5975bb5553235c01a922aae2861f0415b81686b5a31775534e2079636b5`) holds
`/System/Library/KernelCollections` and `/System/Library/Kernels/kernel` from
`apple_macbookpro15-1`. **It arrived at the public repo's root, untracked
and NOT ignored** (`git check-ignore` exited 1), one `git add -A` from
publication, and it had never been committed. It was moved by rename, hash
identical, to `~/corpus/apple_macbookpro15-1/kernel/` (rev-parse exits
128). Ignore rules for `*.tgz`, `*.tar`, `*.tar.gz`, `*.kc` and `*.elides`
were added to both repos as a second line and proven with `check-ignore -v`
(public `97608f9`, private `7e6616f`). The listing was checked before
extraction: 6 entries, no absolute path, no `..`, no links. Extracted files: 5, 457,590,284
bytes, equal to the listing; manifest hash `da784792…`, and it verifies.
Both repos were clean afterwards.

## Q1. Can individual kext boundaries be recovered? **Yes**, from the bytes

| file | filetype | per-member structure |
|---|---|---|
| `BootKernelExtensions.kc` | `MH_FILESET` (12), x86_64 | **211 `LC_FILESET_ENTRY`**: `com.apple.kernel` (`MH_EXECUTE`) and 210 kexts (`MH_KEXT_BUNDLE`) |
| `SystemKernelExtensions.kc` | `MH_FILESET`, x86_64 | **189 `LC_FILESET_ENTRY`**, all `MH_KEXT_BUNDLE` |
| `kernel` | `MH_EXECUTE`, x86_64 | not a collection |

Every entry names its bundle ID and points at a valid x86_64 Mach-O header,
with its own segments. The code of each is `__TEXT,__text` (on this Intel
build there is no `__TEXT_EXEC` segment), and each kext carries its own
`__DATA,__got`. **399 kexts are individually addressable, so per-driver
figures have a macOS counterpart.** The collection itself carries
`LC_DYLD_CHAINED_FIXUPS`. *Reasoned, not traced:* a kext reaches kernel
symbols through its GOT, bound by the collection's chained fixups. Tracing
one binding from the bytes is owed before a loader is designed around it.

## Q2. Do kexts carry direct register access? **Yes, and rarely**

The two-byte family is counted exactly as in
`system-family-census-2026-09-22.md`: same list, fixed beforehand, and every
hit confirmed by objdump at the same offset (4 unconfirmed hits dropped).
One-byte forms are excluded, since the control failure applies to kernel
code too.

| | two-byte system instructions | UNKNOWN | distinct forms | members containing one | with a CR/DR move |
|---|---|---|---|---|---|
| **399 kexts** | 356 | **356 (100%)** | 37 | **11 of 399** | 1 |
| **kernel** | 810 | **810 (100%)** | 46 | — | — |

- **The kernel:** RDMSR 201, WRMSR 152, RDTSC 70, CR0/CR3/CR4 moves 223 in
  total, CPUID 36, CLTS 16, WBINVD 12, descriptor tables 24, SWAPGS 7, VMX 12.
- **The kexts:** 297 of the 356 are one kext, `com.apple.driver.AppleHV`,
  the hypervisor: VMWRITE 95, VMREAD 81, CR/DR moves 40 and RDMSR 35. The
  rest is MSR, CPUID and RDRAND in `AppleIntelMCEReporter` (21),
  `AppleFIVRDriver` (11), `AppleIntelKBLGraphics` (8),
  `AppleIntelICLGraphics` (7), `OSvKernDSPLib` (4), `pmtelemetry` (3),
  `corecrypto` (2) and `ACPI_SMC_PlatformPlugin` (1).
- **Two hits are suspect:** one `SLDT` each in `AppleHDA` and `AppleGFXHDA`.
  A descriptor-table instruction in an audio driver is what the shared
  linear-sweep failure mode would produce, and no third source was run.
  They are flagged, not counted as confirmed.

**Against Windows:** there, a CR move sits in most drivers of a Windows 10
build, because the IRQL read is inlined. On macOS, register access
concentrates in the kernel and in a handful of platform kexts; **388 of
399 kexts carry none**. The decoder names none of it on either platform.

## Q3. The decode rate, on the same definitions

| set | files | instructions | `int3` | UNKNOWN excl. padding | pooled | median |
|---|---|---|---|---|---|---|
| **macOS kexts** | 399 | 19,709,772 | 515 | 454,486 | **2.31%** | **0.81%** |
| **macOS kernel** | 1 | 2,190,960 | 30 | 58,218 | **2.66%** | — |
| dexts | 17 | 759,907 | 3 | 13,343 | 1.76% | 1.00% |
| Mac userland | 621 | 21,231,893 | 219 | 732,798 | 3.45% | 2.56% |
| Windows HP (19041) | 8 | 381,739 | 45,032 | 7,041 | 2.09% | 2.03% |
| Windows Dell (26100) | 446 | 14,606,833 | 1,803,194 | 372,742 | 2.91% | 3.30% |
| Windows ASUS older (19041) | 455 | 14,742,938 | 1,521,635 | 387,525 | 2.93% | 2.90% |
| Windows ASUS newer (22621) | 505 | 18,628,796 | 2,043,687 | 481,101 | 2.90% | 3.40% |

**The decoder's pooled gap on macOS kernel code is in the Windows range; the
median is lower.** As with every row here, a pooled and a median figure
that disagree are both kept.

**No Mach-O loader is started on the strength of this.** The measurements
say one is buildable (per-kext boundaries exist) and that the park walk
would have little to read in most kexts (388 of 399 carry no register
access). Whether to build it is a separate ruling.

---

# The IOKit mapping-call census (2026-09-22)

**The owner's correction, recorded first:** the system-instruction census
(Q2) and the park walk measure different things. The park pattern is a
mapping call returning a pointer, the pointer filed in a structure slot,
and ordinary `mov` dereferences later. No privileged instruction is
involved. So Q2's "388 of 399 carry no system instruction" says nothing
about MMIO, and neither did the earlier "dexts have nothing to read". The
measurement that decides the loader is a count of mapping calls.

## The list, fixed before counting

It comes from the headers of the **exact kernel build**: the kernel's
version string reads `xnu-11417.140.69`, and the headers were fetched at that
tag from `apple-oss-distributions/xnu` (`IOMemoryDescriptor.h` `501df452`,
`IOService.h` `6e9a7915`, `machine_routines.h` `ba832723`).

| entry point | kind | declared at |
|---|---|---|
| `IOService::mapDeviceMemoryWithIndex` | **virtual** | IOService.h:1350 |
| `IOMemoryDescriptor::map` | **virtual** | IOMemoryDescriptor.h:771, 785 |
| `IOMemoryDescriptor::createMappingInTask` | non-virtual | IOMemoryDescriptor.h:763 |
| `IOMemoryDescriptor::setMapping` | **virtual** | IOMemoryDescriptor.h:796 |
| `IOMemoryDescriptor::makeMapping` | **virtual** | IOMemoryDescriptor.h:835 |
| `ml_io_map`, `ml_io_map_wcomb`, `ml_io_map_unmappable` | C | machine_routines.h:185–193 |
| `IOMemoryMap::getVirtualAddress`, `getAddress` (where the address comes out) | **virtual** | IOMemoryDescriptor.h:913, 1010 |

## How a kext refers to a kernel function, read from the bytes

- **Not by name at binding time.** Both collections' chained-fixup headers
  have `imports_count = 0`. Each member does carry its own symbol table,
  whose undefined externals name what it references. But for a *virtual*
  method that name comes from subclassing: **351 of 399** members name
  `mapDeviceMemoryWithIndex`, which is roughly every `IOService`
  subclass. **Name presence counts subclassing, not calls**, and is not
  used as the count.
- **Boot collection:** code calls kernel functions **directly**. The
  kernel member's 23,429 symbols all lie inside its own segments in
  collection address space (same UUID as the standalone `kernel`, loaded
  `0xe8000` higher). GOT slots hold chained pointers whose low 30 bits are
  an offset from the collection base, with **level 0 = Boot**: 5,466 of
  5,466 resolve to a defined symbol.
- **System collection:** code cannot reach the kernel with a rel32 call.
  It calls into **`__BRANCH_STUBS`**, where each stub is `jmp *slot(%rip)`
  into **`__BRANCH_GOTS`**, and each slot is a level-0 chained pointer:
  1,678 of 1,678 stubs resolve to a kernel symbol. Level-1 pointers (into
  System itself) do not land on symbol starts from either candidate base.
  They stay unresolved, and no fixed entry point is defined in System.

## Three detector defects, each caught by a control before any number was read

1. **`c++filt -_` strips the leading underscore only from names it
   demangles**, so every C symbol (`_IOLog`, `_ml_io_map`) kept it and
   matched nothing. The control (`IOLog`, `IODelay` absent from the kernel
   definitions) exposed it. Fixed by stripping exactly one underscore
   before demangling.
2. **`objdump --adjust-vma` prints 16-digit addresses with no leading
   space**, and the line pattern required one, so no line parsed, and
   "zero sites" meant zero lines read. The control (`IOLog` 0 sites)
   exposed it.
3. **The System collection was blind** until its branch stubs were
   resolved. The control per collection (`IOLog` in Boot kexts only)
   exposed it.

Defects 1 and 2 are the tenth and eleventh instances in this arc of
matching text where a value was meant.

## The result

**Controls first** (the same detector, common non-virtual kernel functions):
`IOLog` 28,312 sites in 245 members (128 Boot, 117 System); `IOSleep`
1,725 in 149; `IODelay` 636 in 69. Resolved: 20,035 direct and 12,522
through branch stubs. **And a negative control: `OSObject::release`**,
virtual and called by essentially every kext, reads **0**.

| entry point | code sites | members with ≥1 |
|---|---|---|
| `IOMemoryDescriptor::createMappingInTask` | **104** | **38** |
| `ml_io_map` | **1** | 1 (`IOPCIFamily`) |
| `ml_io_map_wcomb`, `ml_io_map_unmappable` | 0 | 0 |
| `mapDeviceMemoryWithIndex`, `map`, `setMapping`, `makeMapping`, `getVirtualAddress`, `getAddress` | **not measurable** (virtual) | — |
| **total visible** | **105** | **39 of 399** (Boot 15, System 24) |

**The limit, stated at the weight of the number:** 105 is a **lower
bound**, and **it omits the primary MMIO call.** The closest analogue of
`MmMapIoSpaceEx`, `IOService::mapDeviceMemoryWithIndex`, is virtual. A
kext calls it through the provider object's vtable (`call *OFF(%reg)`),
which carries no name and no fixed address, as the `OSObject::release` zero
shows. Counting it needs a vtable-slot census: the slot offset is fixed by
the kext ABI, but a bare offset matches any class's method at that slot.
That is a new instrument, **named and not built**.

The 39 members are largely graphics (`IOAcceleratorFamily2`, `IOGPUFamily`,
Intel KBL/ICL, 15 AMD Radeon kexts), networking (`AppleBCMWLANCoreMac`,
`IOSkywalkFamily`, `IO80211Family`, `AppleEthernetAquantiaAqtion`), storage
(`IONVMeFamily`, `AppleDiskImages2`), USB and `AppleHV`.
`createMappingInTask` maps a memory descriptor, which may be device memory
or ordinary RAM. **Which of the 104 are MMIO is not known without a walk.**

**Comparability with Windows:** the Windows figure (12 HP; 172 / 171 / 184
on the other machines) counts direct calls to the one mapping API. This
figure counts the non-virtual half of IOKit's mapping surface. **They are
not the same measurement**, and 105 / 39 is not to be set beside 172 as a
like-for-like count.

**So the loader decision rests on a lower bound:** at least 39 of 399 kexts
make at least 105 mapping calls a walk could start from. That is enough to
say there is a pattern to find, and not enough to size it until the virtual
half is counted.

## Provenance, licensing and scope (owner ruling 2026-09-22)

- **The pinned source:** `xnu-11417.140.69`, read from the kernel binary's
  own version string (`Darwin Kernel Version 24.6.0 … xnu-11417.140.69.712.69~10/RELEASE_X86_64`)
  and matched to the tag of the same name on `apple-oss-distributions/xnu`.
  It is kept here the way the Ghidra snap revision is kept for the oracle.
- **The licensing boundary:** xnu source is Apple's. The five headers
  fetched live in scratch only; `find` confirms that neither repository
  contains or tracks any of them. The **derived symbol list** above is a
  list of published API names, facts about an interface and not Apple's
  code, so it publishes, with the tag beside it, like sha256 and per-file
  measurements. Apple's binaries never leave `~/corpus/`
  (`/home/bbrown/corpus/`).
- **Every macOS figure here is single-build: Darwin 24.6.0, one machine
  (`apple_macbookpro15-1`), one OS version.** The Windows corpus needed four
  machines to discover that vendor and build were confounded
  (`park-census-cross-vendor-2026-09-22.md`, *Build as an explicit
  axis*). These figures cannot distinguish "how macOS does this" from "how
  this build does this". That applies to the per-kext boundaries, the
  11-of-399 register-access count, the 2.31% / 0.81% decode rate, the
  `__BRANCH_STUBS` binding, and the 105-site lower bound. **No macOS number
  is to be read as a property of macOS until a second build is measured.**

## The negative control, as its own item

**A census needs a probe whose answer cannot be zero, so that a zero
indicts the instrument.** Here that probe was `OSObject::release`,
virtual and called by essentially every kext, and it read **0**. That
proved the method blind to virtual dispatch, not that virtual dispatch is
absent. The one-byte system-family census lacked such a probe, and would
have caught its failure a step earlier with one (`system-family-census`
§3). The positive controls (`IOLog` 28,312 sites) are the other half: a
count that must be large.

## Before the walk: what the source says the walk would measure (2026-09-22)

The owner's ruling was to run the existing walk on the 105 visible sites.
Four things were read first, from the pinned headers and the bytes:

1. **The return convention.** `createMappingInTask` is declared
   `OSPtr<IOMemoryMap>` (IOMemoryDescriptor.h:763). `OSPtr<T>` is `T *`
   unless the translation unit defines `IOKIT_ENABLE_SHARED_PTR`
   (`OSPtr.h` `bf990938`, lines 69–107), which is a per-file compile
   choice. **The bytes decide:** at the IOSurface and IONVMeFamily sites,
   RDI carries the descriptor and **RAX returns the `IOMemoryMap *`** (no
   hidden return pointer).
2. **The return is the map object, not the device address.** Every site
   read continues `mov (%rax),%rcx` / `call *0x118(%rcx)`. **Slot `0x118`
   of `__ZTV11IOMemoryMap` is `IOMemoryMap::getVirtualAddress()`**, read
   from the kernel's own vtable. **IOKit maps in two steps:** the mapping
   call yields an object, and the base comes out of a *virtual* call on it.
   The walk as it stands, seeded at the mapping call's RAX, would follow
   the object and would treat the second call as clobbering RAX. It would
   report where the *map object* is filed, not where the device base is
   parked. That is a different claim, and it is not the Windows pattern.
3. **The release analogue.** No non-virtual release exists for either
   path. The pinned x86 headers declare no `ml_io_unmap`. The map is
   released through its own vtable at fixed slots: `release()` `+0x28`,
   `taggedRelease` `+0x50`, `free()` `+0x90`, `unmap()` `+0x148` (read from
   the vtable). **So a release kill is keyable, but only by a walk that
   follows the map object**, the same capability item 2 needs.
4. **The ABI.** System V AMD64 psABI, register-usage table (fetched from
   the `x86-psABIs` master branch, sha256 `2d42f2ab`; there is no release tag to
   pin): **preserved RBX, RSP, RBP, R12–R15; not preserved RAX, RCX, RDX,
   RSI, RDI, R8–R11.** Unlike Windows x64, RSI and RDI are volatile.

**And the plumbing:** the existing walk runs only from the PE pipeline and
starts only at a call through an import slot. Kext calls are direct
(Boot) or through branch stubs (System). **The walk cannot be pointed at
these sites without new plumbing**, which is loader-adjacent and reserved
to a ruling.

**`ml_io_map` is the one site with the Windows shape:** it returns a
`vm_offset_t`, the address itself (machine_routines.h:185). There is one
site, in IOPCIFamily.

---

# (d): the 104 `createMappingInTask` sites, read by hand (2026-09-22)

**Owner ruling: build nothing; read the sites.** Every call site of
`IOMemoryDescriptor::createMappingInTask` was traced from the call onward in
address order, within its function (bounded by the member's own symbols),
using System V volatility. The trace follows the returned `IOMemoryMap *`
and, after a slot-`0x118` call on it, the address. Every trace was read, and
three were checked against the bytes. **The count reconciles with the census:
104** (101 calls, plus 3 tail jumps that hand the map straight back to the
caller).

**Classes, fixed before classifying:** *stored*, meaning the map is written
to a field reached through a register before any `0x118` call (a frame spill
counts as local); *immediate*, meaning the `0x118` call comes first; *neither*,
everything else, each case named. A store to offset `0x0` of a pointer
followed by the function returning is **not** counted as *stored*: that is
writing through a caller's out-parameter.

| class | sites |
|---|---|
| **stored**, with the fetch in the same function | **38** |
| **stored**, with no fetch in this function | **24** |
| **immediate** | **15** |
| neither: out-parameter (`*out = map`) | 8 |
| neither: map passed to another function | 7 |
| neither: released (slot `0x28`) before any fetch | 5 |
| neither: nothing followed before the trace stopped | 4 |
| neither: tail jump, map returned to caller | 3 |

**Stored dominates: 62 of 104.** Duplicated code, stated so it is not read as
breadth: **11 of the 62 are one function copied across the AMD `HWLibs`
kexts** (`X5000`–`X6810`), and the three AMD out-parameter sites are likewise
one function. Collapsing each copied family to one gives **52 distinct
*stored* sites.**

**The ends:** `IOAcceleratorFamily2` (11 stored, 0 immediate),
`AppleBCMWLANCoreMac` (6 / 0), `IOAVBStreamingPlugin` (5 / 0) against
`IOSkywalkFamily` (2 / 4), `AppleUSBUserHCI` (1 / 3), `IOUSBHostFamily`
(0 / 2) and `IONVMeFamily` (0 / 1).

**Where the address goes after the slot-`0x118` call** (the IOKit analogue of
the Windows base; 53 sites fetch in the traced function):

| after the fetch | from *stored* sites | from *immediate* sites |
|---|---|---|
| **address stored to a field** | **28** | 4 |
| address passed to a call | 5 | 6 |
| address stored to the frame | 0 | 1 |
| address returned | 1 | 0 |
| not followed (the trace stopped) | 4 | 4 |

**The address itself is filed into an object field at 32 of the 53 fetching
sites.** That, not the map object, is what a macOS park would mean.

**Fetch and store in the same function:** of the 62 *stored* sites, **38
fetch the address in the same function** and 24 do not. On Windows the
reload was usually elsewhere, which is why the join was needed. **Here the
majority fetch locally**, so a macOS walk over those 38 needs no
cross-function join.

**Checked against the bytes:**
- `AppleBCMWLANCoreMac` `…6d6f7c`: map to `0x90(%rcx)` (a field of
  `this->0x10`), `mov (%rax),%rcx` / `call *0x118(%rcx)`, address to
  `(%r14)`. Stored, same function.
- `IOSkywalkFamily` `…98d93f`: map held in R12, an unrelated vcall on
  another object, then `mov (%r12),%rax` for the fetch. Immediate.
- `AMDRadeonX4000` `0x32473d`: `mov %rax,(%rbx)` then `setne %al` and
  return. An out-parameter. **The trace had labelled it "map returned",
  which is wrong:** the function returns a success flag, and the tracer did
  not see `setne %al` replace RAX, the same byte-write blindness the lifter
  had before `(as)`. The class stands; the label is corrected here, and it
  applies to all eight out-parameter sites.

**Limits:** the trace is linear in address order (the branch-following
limit), and 8 fetching sites were not followed to a destination.

**Decision (owner's rule): *stored* dominates, so (b) is justified, and it
would count** a map object filed into a field and then its
`getVirtualAddress()` result filed into a field, 38 of the 62 in the same
function.

**A pre-registration constraint for (b), written now while it is
hypothetical (owner ruling):** slot `0x118` is a fact about **Darwin 24.6.0**,
not about IOKit; vtable layouts move between builds. An instrument keyed on a
slot number is single-build **by construction**. **If (b) is built, the
slots (`getVirtualAddress`, `release`, `taggedRelease`, `free`, `unmap`) are
resolved from each collection's own `__ZTV11IOMemoryMap` at analysis time,
never compiled in**, the way this doc resolved them.

## Standing procedure: an incoming archive is located by search, never by its stated path (owner, 2026-09-23)

**The ignore rules cannot cover this case, and it happened.**
`dell-system32.zip` (about 1 GB of Microsoft binaries) was said to be in
`/home/bbrown/corpus/`. It was actually in
`~/projects/RuView/firmware/esp32-csi-node/test/corpus/`, **inside a
third-party repository (`ruvnet/RuView`)**. It was untracked and not
ignored, because our ignore rules do not reach another project's tree, so
one `git add .` there would have published it in someone else's project.
It was the third archive this week to land somewhere other than where it
was asked to go. It was caught only because the file was located by a
filesystem search instead of the stated path being trusted.

**The procedure, from now on:**
1. **Any incoming archive is located by a filesystem search before it is
   read**, and **the search result is what gets used**, never the path it
   was said to be at:
   `find /home/bbrown -name '<archive-name>' -o -name '*.tgz' -newermt '-1 hour' 2>/dev/null`
2. If it is found anywhere other than `/home/bbrown/corpus/`, run
   `git rev-parse` there and `git status` for the file. **Move it with a
   sha256 check across the move**, then show that tree clean.
3. Only then does intake begin: the listing is checked before
   extraction, and the manifest and count come before anything reads it.
