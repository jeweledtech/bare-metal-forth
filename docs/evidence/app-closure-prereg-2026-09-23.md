# One application's dependency closure: pre-registration (2026-09-23)

**One binary, one build, n = 1.** `dbInstaller.exe` (the corpus's only
EXE, from ASUS newer, 828,136 bytes, x64), walked against **one** System32:
the Dell's, build **10.0.26100.9444**. Nothing below generalises past that
pair. **Written before the walk.** Outcomes go BELOW the line.

**Why it is measured** (owner, 2026-09-23): *"load apps through translated
vocabularies"* means an app needs a vocabulary for everything it calls,
and for everything those call. The dependency closure is the work, not the
app. The number of distinct exported functions reached bounds the
vocabulary work, meaning how many Forth definitions one application's
graph would demand. **This project has never had that number.**

## The input, intake by the proven route

- **Placement.** `dell-system32.zip` was found in **another project's
  tree** (`~/projects/RuView/firmware/esp32-csi-node/test/corpus/`,
  untracked and *not* ignored, in `ruvnet/RuView`). It was moved to
  `/home/bbrown/corpus/`, with its sha256 `9b2db580…` identical before and
  after, and that tree's status for the directory is clean.
- **Listing, checked before extraction.** 3,945 file entries, flat, no
  unsafe paths, no case-collisions: 3,353 `.dll` and 592 `.exe`.
- **Extracted** to `/home/bbrown/corpus/dell_26100_system32/`: **3,945
  files and 2,198,057,608 bytes, identical to the pre-copy count on the
  machine. No file was skipped as locked.** The manifest is
  `dell_26100_system32.SHA256SUMS`, and the provenance is in `.INTAKE`.
- **Proven by output:** both repos show no `dll`, `zip` or `system32`
  entries, and `git -C ~/corpus rev-parse` exits 128. These are
  Microsoft's bytes, under the same rule as the drivers: only hashes,
  counts and names are published.

## Step 1: how an `api-ms-win-*` import resolves on 26100, read from the bytes

`apisetschema.dll` (10.0.26100.9278) carries a section `.apiset`. Its
header reads **version 6, 984 entries, hash factor 31**.
- The entry layout was tested by decoding: **984 of 984** names read as
  `api-`/`ext-` names, which a wrong layout could not produce.
- Each entry has a name, a **hashed length that excludes the final
  version component** (`…-l1-1-0` hashes 70 of its 74 bytes), and a list
  of (importing-module alias, host) values. The value with an empty alias
  is the default host.

**So an import resolves as follows:**
1. Lower-case it and drop `.dll`.
2. Match it against an entry on the name up to its **last hyphen**.
3. Take the host whose alias equals the importing module's name if there
   is one (6 entries carry such aliases), else the default host.

**The resolution data is a file, and it is in the archive.** Reachability
through api-sets is therefore decidable statically on this build.

**138 entries have no host on this build** (10 `api-`, 128 `ext-`). An
import through one of them is a **genuine terminal: unresolvable, and
named**. So is a name that matches no entry.

## Terminals, read from the code

- **A syscall stub** is an `ntdll` or `win32u` export whose code begins
  `4C 8B D1 B8 imm32` (`mov r10,rcx; mov eax,N`). On 26100, 976 `Nt*`/`Zw*`
  exports of `ntdll` begin that way. **A syscall is counted by its number
  `N`**, so an `Nt*`/`Zw*` alias pair counts once. The 6 `Nt*`-named
  exports that are not stubs (`NtGetTickCount`, `NtQuerySystemTime`,
  `NtdllDefWindowProc_*`, `NtdllDialogWndProc_*`) are not syscalls.
- **An unresolvable name** is a DLL that is not in the archive, an
  api-set with no host, an ordinal or name that the providing DLL does
  not export, or a forwarder that does not resolve.

## What is walked, and the granularity, stated so it is not over-read

**The walk is at the granularity the static loader works at.**
- Starting from `dbInstaller.exe`, every **import** is resolved to its
  providing DLL: through the api-set schema, and through **forwarded
  exports**, where `kernel32!X` forwarding to `NTDLL.Y` is followed to
  `ntdll!Y`, recursively.
- Every DLL reached then has **its own import table** walked, with the
  depth at which each DLL first enters recorded.

**This walk does not follow calls *inside* a DLL.** When `kernel32!X` is
bound, the walk does not know which of kernel32's own imports `X` uses; it
takes all of kernel32's imports, because the loader binds them all. So:
- **"DLLs reached"** is the **load-time closure**, exact for what the
  loader maps.
- **"Distinct exported functions reached"** is the **set of (DLL,
  function) bindings the loader resolves across that closure.** It is an
  upper bound on what one application *uses* through imports, and exact
  for what must *exist* to load it.
- **"Distinct syscalls reached"** counts the syscall stubs **bound by an
  import** somewhere in the closure. **It is a floor:** `ntdll`'s own
  internal functions (`Rtl*`, the loader) reach syscalls by direct calls
  inside `ntdll`, which no import table shows.

## The floors, each named and counted, never absorbed

1. **Delay-loaded imports** are listed statically but loaded on first
   call. They are **walked as a separate layer**: the primary figures are
   static imports only, and the delay layer's additions are reported
   beside them, with every delay edge counted.
2. **`GetProcAddress` and `LoadLibrary`** by string or ordinal are
   invisible to a static walk. Each DLL in the closure that imports either
   is **counted and listed**: the places where the closure can grow at
   runtime.
3. **Unresolvable edges:** hostless api-sets, missing DLLs, missing
   exports and broken forwarders are each **listed by name**.
4. **Intra-DLL calls to syscalls**, as above: the syscall count is a
   floor on the kernel entry points, and is stated as one.

## Predictions (guesses, written down so the outcome can disagree)

| # | prediction | the alternative it rules out |
|---|---|---|
| A1 | **DLLs reached (static): dozens, 20–80** | a handful (under 10) or a large fraction of System32 (over 200) |
| A2 | **distinct exported functions bound: low thousands, 1,000–6,000** | "dozens" (a roadmap by itself) or tens of thousands |
| A3 | **distinct syscalls bound by import: 100–500** | the whole table (about 976 of ntdll's alone) |
| A4 | the delay-load layer **adds DLLs** and grows A1 by more than 50% | delay-loads being negligible |
| A5 | at least one `GetProcAddress` importer sits in the closure (`kernel32`/`KernelBase` itself counts), so **the closure is open at runtime** and every figure is a floor there | a closed static graph |
| A6 | at least one **hostless `ext-ms-*` edge** is met | every api-set import resolving |

**Instrument:** `closure.py`, written after this is committed, in
`~/corpus/tools-2026-09-23/`, outside every repo, with its hash in the
outcome.

---

## Outcome

*(below this line, from the artefact only)*
