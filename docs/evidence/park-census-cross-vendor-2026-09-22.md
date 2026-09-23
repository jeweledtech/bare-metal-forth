# Cross-vendor park census, and the Mac decode rate (2026-09-22)

**Instrument:** the shipped translator's own report (`-t report -S`), which is not a
new instrument, run over every x86-64 PE file in each machine's set. Run
after the corpus-absent repair (`80225ab`) and the park-walk fix
(`c08d6e4`), so every site is a park, a named stop, or "none".

**Inputs hashed:** `bin/translator` `9a46c0e921bc5b8b`, `x86_decoder.c`
`838d1581c9b4b109`. Corpus manifests: hp_i3 `bc16288de4219182`, Dell
`5fee2210e7c92d0c`, Older ASUS `6e27020f9b883f06`, Newer ASUS `6fcf822e5eaa21d2`,
Mac `94202b2d5f9bb4df`. The aggregation scripts are kept outside every repository,
beside the corpus, in `~/corpus/tools-2026-09-22/`: `park_census.py`
`f57c5449`, `park_agg.py` `5d1ce8b5`, `extract_text.py` `b0ca38f6`,
`decode_rate2.c` `20f5a027`.

**Population, stated both ways:** four machines, three vendors. HP n=1,
ASUS n=2, Dell n=1. Machine models are not yet known (no binary names
one), so the directory names stand in until the slugs are settled. The Mac is
not in the park census: its set is `/usr/bin` userland with no kernel
extensions.

## 1. Denominators, per machine, never pooled

| machine | files | x86-64 PE | analysed | not analysed | import a mapping API | …no call site found | drivers with a site | sites |
|---|---|---|---|---|---|---|---|---|
| HP | 8 | 8 | 8 | 0 | 7 | 0 | 7 | **12** |
| Dell | 622 | 446 | 446 | 0 | 78 | 0 | 78 | **172** |
| ASUS (older) | 578 | 455 | 455 | 0 | 76 | **1** | 75 | **171** |
| ASUS (newer) | 720 | 505 | 505 | 0 | 79 | 0 | 79 | **184** |

The files that aren't x86-64 PE are 32-bit x86 PE, **all** of them (108 / 109 / 116,
measured from each file's machine field; none is ARM64), and non-PE files (68 / 14 / 99). Every x86-64 PE
was analysed; there were no failures and no timeouts. One ASUS driver
imports a mapping API with no call site the pass recognises; it's counted
as its own category and is not a zero.

## 2. Outcomes, per machine, with "couldn't tell" beside every park number

| machine | **structure slot** | frame spill | indexed element | **couldn't tell** | none | structure share |
|---|---|---|---|---|---|---|
| HP | **6** | 2 | 1 | **2** | 1 | 6/12 = 50% |
| Dell | **88** | 17 | 8 | **17** | 42 | 88/172 = 51% |
| ASUS (older) | **78** | 21 | 7 | **14** | 51 | 78/171 = 46% |
| ASUS (newer) | **93** | 18 | 8 | **14** | 51 | 93/184 = 51% |

**The HP row is the control:** it reproduces the twelve sites reported by
today's fix exactly.

**Both ways, from now on (owner ruling 2026-09-22): never one share alone.**

| machine | structure / all sites | structure / resolved sites | none | couldn't tell |
|---|---|---|---|---|
| HP | 6/12 = 50% | 6/9 = **67%** | 1 (8%) | 2 |
| Dell | 88/172 = 51% | 88/113 = **78%** | 42 (24%) | 17 |
| ASUS (older) | 78/171 = 46% | 78/106 = **74%** | 51 (30%) | 14 |
| ASUS (newer) | 93/184 = 51% | 93/119 = **78%** | 51 (28%) | 14 |

"Resolved" means a park of any kind, with `none` and `couldn't tell` both
excluded. **HP is the weakest of the four on resolved share**, and `none` is
8% on HP against 24–30% on the other three. The two ways of counting differ
entirely inside the `none` column, which §4 names as the weakest. So 46–51%
is a floor, and the resolved share is not a finding until `none` is
verified.

## 3. Does the device-extension park pattern hold at n=4, or was it HP-shaped?

**It holds on all four machines, including both ASUS machines, at 46–51%
of sites.** It also holds across authors. Of the drivers with a site, on the three
non-HP machines 47–53 are Microsoft's and 25–28 are other vendors' (HP: 7 and 0) (Intel, AMD,
Realtek, Mellanox, QLogic, Chelsio, NVIDIA, and Dell's own
`DCSDDriver.sys` and `DellInstrumentation.sys`). Both groups park into
structure slots.

**What n=4 cannot tell apart, stated plainly:** most drivers on every
machine come from the operating system, not from the machine's vendor:
Microsoft's inbox drivers, plus third-party drivers that appear under the
same name on every machine (**reasoned** to be driver-store inbox from that
recurrence; not measured). The drivers with a site that are specific to one vendor's
machine are few:

- **Dell:** `DCSDDriver.sys` and `DellInstrumentation.sys`.
- **Older ASUS:** `IntcAudioBus`, `Netwtw08`, `RTKVHD64`, `dptf_acpi`,
  `dptf_cpu` and `iaStorAC`.
- **Newer ASUS:** `RTKVHD64`, `TbtBusDrv`, `VBoxSup` and `iaStorVD`.

So the finding is **that the pattern belongs to the Windows driver model**
(a mapped base filed into the device extension). It is **not HP-shaped**, and
**not shown to be vendor-specific in either direction**: the vendor signal
sits in a dozen drivers.

**These are not re-counts of the same bytes.** 210 distinct driver
binaries (by sha256) have a site. 194 of them appear on only one machine, 3
on two and 13 on three: same-named drivers differ by Windows build.

## 4. What "couldn't tell" contains, and what "none" means

**47 stops across the four machines, by the instruction that stopped the walk:**

| instruction | stops | what it is |
|---|---|---|
| `int3` | 15 | **reasoned: the walk left the function.** MSVC pads between functions with `CC`, and the linear walk does not stop at RET; that none of the 15 sits inside a function body is not checked |
| `setne` | 9 | a flag-set; the lifter drops its operand |
| `bt` | 6 | **flag-only**, so the base was not overwritten; undetermined because the decoder doesn't name BT |
| `rep` | 6 | a string instruction (RDI/RSI/RCX) |
| `btr` / `bts` / `cmove` / `movslq` | 11 | real writers the UIR can't show |

**"none" means:** no store of a register holding the base before the next
CALL in *address order*. The walk doesn't follow branches and doesn't stop
at RET; the 15 `int3` stops are consistent with it crossing function ends. So "none" is
the walk's own statement and is not independently checked on the new
machines. It is the category most likely to hide a miss.

## 5. The Mac decoder-only measure

**No prior Windows "unknown-mnemonic rate" existed to reuse.** The only
unknown ratio the project had was the shipped-binary smoke check, and it
was retired in (s) as a proxy. So one measure is defined here and applied
identically to both platforms. Each binary's code section is extracted
(PE `.text` by virtual size, Mach-O `__TEXT,__text` from the x86_64 slice)
and swept linearly by the shipped decoder in 64-bit mode, through the same
harness for both.

- **Extractor cross-checks:** the PE `.text` size equals `objdump -h`
  (`0x4f69`). The binutils `objdump` here has **no Mach-O support**, so the
  Mac slice was checked by disassembling the extracted bytes as raw x86-64,
  which gives a canonical clang prologue (`push %rbp; mov %rsp,%rbp; push %r15 …`).

| set | files | instructions | `int3` padding | UNKNOWN excl. padding | rate | INVALID | per-file median |
|---|---|---|---|---|---|---|---|
| HP | 8 | 381,739 | 45,032 | 7,041 | **2.09%** | 0 | 2.03% |
| Dell | 446 | 14,606,833 | 1,803,194 | 372,742 | **2.91%** | 14,772 | 3.30% |
| ASUS (older) | 455 | 14,742,938 | 1,521,635 | 387,525 | **2.93%** | 20,187 | 2.90% |
| ASUS (newer) | 505 | 18,628,796 | 2,043,687 | 481,101 | **2.90%** | 34,771 | 3.40% |
| **Mac** | 621 | 21,231,893 | 219 | 732,798 | **3.45%** | 5,853 | **2.56%** |

**The padding has to be separated, or the comparison is about padding.** The
decoder doesn't name `CC`, and 86.5% of HP's UNKNOWNs are `int3`. That
figure comes from a mnemonic tally against objdump at the same offsets,
which found 45,032, equal to the harness's `CC` count. Raw, HP is 13.6% and
the Mac 3.5%, a difference in how the two compilers pad, not in decoding.

**Excluding padding, the Mac is not clearly worse.** It is 3.45% pooled,
above the Windows 2.1–2.9%, but its per-file median is 2.56%, below the
Windows medians. Pooled and median disagree, so the pooled figure is
carried by some larger files; which ones is **not measured**.
The composition differs: on the Mac the leading UNKNOWNs are `movups` 24.5%,
`movaps` 11.0%, `(bad)` 8.4% (data or desync), `cmove` 6.8% and `movslq`
5.1%; on HP, after `int3`, they are `movups`, `xorps`, `cmove` and `bt`. On
the Mac, 26,434 UNKNOWNs fell where objdump saw no instruction boundary,
which is a desync signal and is left uncharacterised.

**Not pre-registered:** no Mac prediction was written before this ran, so
these are observations, not a confirmed finding.

**Composition is uncontrolled beyond padding.** The Windows sets are kernel
drivers and the Mac set is userland, so the two differ in more than the
compiler. **The only claim this data supports is that the decoder's
unknown share is similar in magnitude on both** (2–3.5% once padding is
separated), not that it does better on either. Pooled and median disagree
on the Mac (3.45% against 2.56%), and both figures are kept: a single number
there would be a choice, not a measurement.

**Correction of record:** before this ran, the owner attributed the raw
Mac-vs-Windows gap to kernel against userland. The measured cause was
`int3` padding, and with padding removed the direction reverses.

**Noted, not acted on:** 623 of the 624 Mach-O files carry an arm64e slice,
listed in `~/corpus/Mac/MANIFEST.arm64e`. These are the first real ARM64
inputs this project has held, and `uir_lift_arm64_function()` has no caller.

---

# The census after the ABI stop, the release kill and park provenance (2026-09-22)

Binary `baad7b886c867d3a`, census scripts v2 (see
`fix-release-kill-provenance-prereg-2026-09-22.md`). **Reported both ways,
with `none` beside them, and parks split by route.** Intervals are Wilson
95%.

| machine | sites | none | none 95% CI | structure / resolved | 95% CI | **path-verified** structure / resolved | address-order parks | after release |
|---|---|---|---|---|---|---|---|---|
| HP | 12 | 1 (8.3%) | 1.5–35.4 | 6/9 = 66.7% | 35.4–87.9 | 6/9 = 66.7% | 1 | 0 |
| Dell | 172 | 33 (19.2%) | 14.0–25.7 | 89/114 = 78.1% | 69.6–84.7 | 85/114 = **74.6%** | 5 | 1 |
| ASUS (older) | 171 | 37 (21.6%) | 16.1–28.4 | 79/108 = 73.1% | 64.1–80.6 | 76/108 = **70.4%** | 5 | 1 |
| ASUS (newer) | 184 | 41 (22.3%) | 16.9–28.8 | 94/120 = 78.3% | 70.1–84.8 | 89/120 = **74.2%** | 6 | 1 |

"Resolved" means a park of any route; after-release, `none` and
couldn't-tell are excluded. **The path-verified column is the number that
can be defended**: its parks were reached on a real execution path. The
all-routes column adds the address-order parks, which are right only if
nothing on the jumped-over stretch lied.

## The finding: the walk was tuned on the least representative machine, and the evidence for that is the mechanism, not the rates

**Two rates point the same way.** HP has the lowest `none` (8% against
19–22%) and the lowest resolved structure share (67% against 73–78%). The
walk was developed against HP. A walk tuned on a machine gives up least
on it, and a machine whose parks are less often structure slots is not
where the pattern is typical.

**Neither rate difference is established by HP's own numbers.** HP has 12
sites and 9 resolved parks, so one site moves a share by 8–11 points. Both
of HP's intervals contain the other three machines' values: `none` is
1.5–35.4%, resolved share 35.4–87.9%. A reader who takes "HP 67% against 78%"
as a measured gap is taking noise as signal.

**What is established, with a named mechanism, is class B.** In 27–33% of
`none` walks on the other three machines (49 walks), the walk quit at a call
with the base still live in a callee-saved register. **On HP that class was
0 of 1.** That is a defect of the walk that HP's twelve sites did not
exercise and four machines did, found by bytes and repaired by the ABI
stop. **So HP is the least representative machine in the corpus in the
sense that matters: it is too small to exercise the walk's defects**, and
the walk looked better there than it is. Every further walk repair is
validated against all four machines, never against HP alone.

---

# Build as an explicit axis (2026-09-22)

The four machines are **three Windows builds** (read from file-version
resources; `system-family-census-2026-09-22.md` §2): 19041 = HP and ASUS
(older); 22621 = ASUS (newer); 26100 = Dell. So vendor and build are
confounded. Below, the current census (binary `d6df45353907fda4`) is
regrouped without a new run. Intervals are Wilson 95%; *p* is a
two-proportion test.

| grouping | structure / resolved | 95% CI | none |
|---|---|---|---|
| **19041**: HP + ASUS (older) | 89/121 = 73.6% | 65.1–80.6 | 38/183 = 20.8% |
| **22621**: ASUS (newer) | 96/122 = 78.7% | 70.6–85.0 | 41/184 = 22.3% |
| **26100**: Dell | 91/116 = 78.4% | 70.1–85.0 | 34/172 = 19.8% |
| by machine: HP | 8/11 = 72.7% | **43.4–90.3** | 1/12 |
| by machine: ASUS (older) | 81/110 = 73.6% | 64.7–81.0 | 37/171 |

**Every pairwise gap is within noise** (largest: HP against ASUS (newer),
6.0 points, *p* = 0.65; the two ASUS machines 5.1 points, *p* = 0.37;
Windows 10 against Windows 11 is 73.6% against 78.6%, *p* = 0.29).

## What "the pattern holds across vendors" rests on

**The only vendor comparison with build held constant is one pair: HP
against ASUS (older).** Their resolved shares agree to 0.9 points (*p* =
0.95), which reads as "vendor barely matters". **The interval swallows
it.** HP's is 47 points wide at 11 parks, so the pair cannot detect a
vendor effect smaller than roughly 25 points. **The honest statement is
that this corpus cannot separate vendor from build on any park rate:** the
controlled pair is too small, and every other contrast is confounded.

**Build is shown to matter, but at instruction scale, not at park-rate
scale, and it is shown twice:**
- on the Windows 10 build the IRQL read compiles inline as `mov %cr8`, in
  165 same-named drivers whose Windows 11 namesakes import a routine instead;
- serial.sys on 22621 files its base through `mov %rax,(%r15)` where the
  19041 and 26100 builds use `0xf0(%rdi)`, which is why S3 missed.

**The same driver name is not the same code across builds.**

**And one mechanism is not build-shaped:** class B, the walk quitting on a
chain still live in a callee-saved register, was 18 walks on ASUS (older),
the *same build* as HP, where it was 0. HP's zero reflects its eight-driver
sample, not its build.
