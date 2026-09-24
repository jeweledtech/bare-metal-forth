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

**One binary (`dbInstaller.exe`), one build (26100.9444), n = 1.**

**Instrument:** `closure.py` `efea75bb7f0a5ec4`; root sha256 `b0d8bf58e312a08c…`.
It was run only after five controls with known answers:
- `kernel32!HeapAlloc` forwards to `ntdll!RtlAllocateHeap`, and the walk
  loads `ntdll`;
- `api-ms-win-core-file-l1-1-0!CreateFileW` resolves to `kernelbase.dll`;
- a hostless api-set is named unresolvable;
- `NtClose` and `ZwClose` are one syscall (number 15);
- `RtlAllocateHeap` is not a stub.

### The three numbers, each with its distinct count

| | static imports (the load-time closure) | static + delay-load |
|---|---|---|
| **DLLs reached** (distinct files) | **18** (depth 1: 8, depth 2: 8, depth 3: 2) | **379** (depth 2: 103, depth 3: 132, 4: 77, 5: 28, 6: 17, 7: 11, 8: 3) |
| **distinct exported functions bound** (module, function, after forwarding) | **4,800** | **17,734** |
| **distinct syscalls bound** (by number) | **1,281**: `ntdll` **259 of 488**, `win32u` **1,022 of 1,499** | **1,555**: `ntdll` 330, `win32u` 1,225 |

**The static closure, by depth:**
- **1:** advapi32, combase, kernel32, ntdll, ole32, shell32, shlwapi,
  version;
- **2:** gdi32, kernelbase, msvcp_win, msvcrt, rpcrt4, sechost, ucrtbase,
  user32;
- **3:** gdi32full, win32u.

**Where the 4,800 bindings sit:** kernelbase 1,333, ntdll 1,060, win32u
1,027, user32 333, kernel32 238, gdi32 211, ucrtbase 185, rpcrt4 126, and
the rest below 100. The application itself imports **150** functions from
6 DLLs (depth 1).

### Against the predictions

| # | predicted | observed |
|---|---|---|
| A1 | DLLs (static) 20–80 | **missed, low: 18.** Neither alternative (under 10, or over 200) either |
| A2 | functions bound 1,000–6,000 | **held: 4,800** |
| A3 | syscalls 100–500 | **missed, high: 1,281.** `ntdll` alone is 259, inside the range. `win32u` is the miss: user32, gdi32 and gdi32full bind **1,022 of its 1,499** stubs, almost the whole graphics and window service table, the moment any of them is loaded |
| A4 | the delay layer grows DLLs by more than 50% | **held, by far: 18 → 379 (21×)** |
| A5 | a `GetProcAddress`/`LoadLibrary` importer in the closure; open at runtime | **held: 16 of the 18 DLLs, and the application itself**, import one of them (the two that do not are `ntdll` and `win32u`, the bottom of the graph). The closure is open at runtime almost everywhere |
| A6 | at least one hostless `ext-ms-*` edge | **held in the delay layer only**: 0 unresolved edges in the static layer. The delay layer has 131 distinct hostless api-set edges (both `api-` and `ext-`) |

**A correction to my pre-registration, stated rather than absorbed:** A3's
alternative said *"about 976 of ntdll's alone"*. 976 counts `Nt*`/`Zw*`
**names**, which come in pairs. Counted by syscall number, as the same
pre-registration defined it, `ntdll` has **488**.

### The floors, named

1. **Delay loads** turn 18 DLLs into 379 and 4,800 functions into 17,734.
   The static figures are what the loader binds at start. The delay figures
   are what the same binaries *can* bind if every delayed call is taken.
2. **Dynamic loading:** 16 of the 18 DLLs in the static closure, and the
   application, import `GetProcAddress`/`LoadLibrary*`; only `ntdll` and `win32u` do not. **No static figure is an upper
   bound on what runs.**
3. **Unresolved edges, all in the delay layer:** 317 edges, **236
   distinct**:
   - **131** api-sets with no host on this build (for example
     `api-ms-win-coreui-secruntime-l1-1-0`, `ext-ms-mf-pal-l2-1-0`);
   - **100** imports from DLLs not in top-level System32 (the copy was top
     level only, for example `AzureAttestManager.dll`);
   - **5** `comctl32` exports not found (`TaskDialogIndirect`,
     `HIMAGELIST_QueryInterface`, ordinals 344/345/381). That is the
     side-by-side case: System32 holds comctl32 v5, and a manifest selects
     v6 from WinSxS, which the static walk does not model.
4. **Intra-DLL calls:** the syscall figures count stubs **bound by an
   import**. `ntdll`'s own `Rtl*` and loader code reaches syscalls by
   direct call, which no import shows. The kernel figure is a floor.

### The finding is the decomposition, not the totals

**Over half of the 4,800 bindings sit in three modules every Win32
application loads** (kernelbase 1,333, ntdll 1,060, win32u 1,027). **And
1,022 of the 1,281 syscalls are `win32u`, bound by user32/gdi32 rather than
chosen by the application.** Both are measured, not inferred. Rooted by
itself with the same instrument:
- **The console base.** `kernel32.dll` reaches **2 DLLs (KernelBase,
  ntdll), 1,740 functions and 215 syscalls, all `ntdll`, 0 `win32u`**.
- **The GUI libraries.** `user32.dll` or `gdi32.dll` alone reaches 9 DLLs,
  3,264 functions and **1,242 syscalls, of which 1,022 are `win32u`**.
- **The path by which the installer acquired the GUI surface**, read from
  the import tables:
  - none of kernelbase, kernel32, ntdll, advapi32, sechost, rpcrt4,
    ucrtbase or combase imports `win32u`, `user32` or `gdi32`;
  - **`shell32` imports user32 and gdi32**;
  - so the chain is `dbInstaller.exe → shell32 → user32/gdi32 → win32u`.
    The installer never imports user32 or gdi32 itself.

**That splits the vocabulary question in two, and it bears on what
ForthOS should target first:**
- **A console or service application** reaches the ntdll + kernelbase
  base: a couple of hundred syscalls and a couple of thousand definitions,
  paid once and shared by every such application. **A finite job, with a
  measured size.**
- **A GUI application** adds a display server's kernel surface **as one
  block**: about 1,000 `win32u` entry points arrive the moment user32 or
  gdi32 loads, whatever the application does with them. For that class,
  the graphics surface *is* the problem, and the per-application
  vocabulary is small beside it.

That is a product decision. The numbers now support it instead of a
guess. (One binary and its roots, one build: n = 1.)

**A3, kept prominent.** Predicting 100–500 syscalls and measuring 1,281
is the most informative result in the run, **because the miss has a named
cause**: `win32u` bound wholesale by the GUI libraries that shell32 pulls
in. A prediction that misses for a reason that can be stated is worth
more than one that holds.

### What the number is, for the vocabulary question

**The answer to "dozens or thousands" is thousands.** One small installer
that imports 150 functions pulls in **4,800 distinct function bindings
across 18 system DLLs at load**, and 17,734 across 379 if its delay loads
are followed. **It is not a roadmap by itself; it is the subset
conversation.**

The shape says where that conversation starts:
- **Over half the 4,800** sit in three modules: kernelbase, ntdll and
  win32u.
- **Most of the kernel surface is `win32u`**: the window and graphics
  service table is bound wholesale by user32/gdi32. It is not something
  this application chose.

One binary, one build, n = 1; the figure is how large the problem is, not
a law about applications.
