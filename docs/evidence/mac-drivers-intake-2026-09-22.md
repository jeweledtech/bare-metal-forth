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
