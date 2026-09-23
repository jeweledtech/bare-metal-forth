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
