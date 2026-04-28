# UBT LLM Fixtures

## Ground-truth fixtures (from HP 15-bs0xx NTFS partition)

The `.sys` files in `tests/hp_i3/` are the only ground-truth fixtures.
They were obtained via a one-off manual copy — most likely by mounting
the HP's internal drive directly (USB adapter or direct SATA access),
not through the Forth net console.  The exact method was not recorded.

| File | Size | Source |
|------|------|--------|
| tests/hp_i3/ACPI.sys | 809,288 | HP Win10 NTFS, manual copy |
| tests/hp_i3/disk.sys | 98,624 | HP Win10 NTFS, manual copy |
| tests/hp_i3/HDAudBus.sys | 139,776 | HP Win10 NTFS, manual copy |
| tests/hp_i3/i8042prt.sys | 118,272 | HP Win10 NTFS, manual copy |
| tests/hp_i3/pci.sys | 474,928 | HP Win10 NTFS, manual copy |
| tests/hp_i3/serial.sys | 90,624 | HP Win10 NTFS, manual copy |
| tests/hp_i3/storport.sys | 714,576 | HP Win10 NTFS, manual copy |
| tests/hp_i3/usbxhci.sys | 608,568 | HP Win10 NTFS, manual copy |

These are all PE32+ kernel-mode drivers from the HP's Windows 10
installation.  The `sys_driver` prompt class and prefilter have been
validated against `i8042prt.sys`.

## Supplementary binaries (NOT from the HP partition)

The following binaries exist on the dev machine and could serve as
initial smoke-test fixtures for the format router and prompt expansion
tasks.  They are **not** from the HP NTFS partition and are **not**
ground-truth for the UBT pipeline.  They would need to be replaced
with HP-sourced equivalents before corpus fanout.

### zlib1.dll — native user-mode DLL

- **Path:** `/home/bbrown/Documents/Desktop/Desktop/Tor Browser/Browser/TorBrowser/Tor/zlib1.dll`
- **SHA256:** `3fd961cfb23f60352072e8347c5d10e9f6cfb3cca76054f15e1f85090806f2e5`
- **Size:** 135,680 bytes
- **Type:** PE32+ executable (DLL) (console) x86-64 (stripped to external PDB), for MS Windows, 12 sections
- **Source:** Tor Browser bundle (mingw-compiled zlib)
- **Prompt class:** `user_dll`
- **Caveat:** mingw-compiled, not MSVC.  Export surface and calling
  conventions may differ from typical Windows system DLLs.

### System.DirectoryServices.dll — .NET assembly

- **Path:** `tests/fixtures/System.DirectoryServices.dll` (copied from LDAPmonitor NuGet cache)
- **SHA256:** `dbdac85280f6736c4720ec7f0aaeaa12bf3382bd5f4d43a24e0acb17a514a8b3`
- **Size:** 126,344 bytes
- **Type:** PE32 executable (DLL) (console) Intel 80386 Mono/.Net assembly, for MS Windows, 3 sections
- **Source:** NuGet package (System.DirectoryServices 5.0.0)
- **Prompt class:** `dotnet` (COR20 directory present)
- **Dual purpose:**
  - Router: validates COR20 format detection (alongside `test_dotnet.dll` synthetic stub)
  - Metadata extractor: validates real .NET metadata parsing (assembly identity,
    141 public types, 5 assembly refs, escape-surface detection via TypeRef)
- **Verified metadata (2026-04-28):** Assembly `System.DirectoryServices` v4.0.0.0,
  strong-named (token `b03f5f7f11d50a3a`), targets netstandard 2.0.0.0.
  No P/Invoke surface (reference assembly strips ImplMap table). TypeRef to
  `System.Runtime.InteropServices.COMException` triggers escape-surface flag.
- **Previous caveat corrected:** The reference assembly does NOT have P/Invoke
  surface (ImplMap table absent). The implementation assembly (from GAC) would.

### kernel.com — DOS COM executable

- **Path:** `/home/bbrown/projects/F-PC/fpc/kernel.com`
- **SHA256:** `0a3c09c494b68e4ebaecf9e25610326d49063ccfce477a6785ac9fac5b17f78a`
- **Size:** 35,964 bytes
- **Type:** DOS executable (COM), start instruction 0xe9bf2ce9 b72c5250
- **Source:** F-PC (Forth for PC) distribution
- **Prompt class:** `com_dos`
- **Caveat:** Forth kernel, not a typical DOS utility.  Interesting for
  the project specifically because it's a Forth system binary, but not
  representative of the general DOS .com corpus.

## Fixtures still needed (from HP NTFS partition)

The following file classes have no fixtures yet.  All exist on the HP
Win10 NTFS partition (confirmed via disk-survey.txt MFT scan) but
have not been extracted.

| Class | Target file | Notes |
|-------|------------|-------|
| DLL (native) | crypt32.dll or similar small system DLL | Multiple copies in MFT scan |
| EXE | notepad.exe | Multiple copies in MFT scan |
| MUI | i8042prt.sys.mui | Would pair with existing i8042prt.sys fixture |
| INF | RTL8168 driver INF (netrtle.inf or similar) | rt640x64.sys found in MFT scan |
| .NET | System.Net.Http.dll | Multiple copies in MFT scan |

## Open question: HP binary extraction method

The original `.sys` fixtures were copied manually (likely USB/direct
drive mount).  The Forth net console (`nc -u -l 6666`) can receive
text output but has no established protocol for transferring binary
files:

- `FILE-DUMP` hex-dumps only the first 256 bytes
- `FILE-READ` reads up to 8 sectors (4KB) into `SEC-BUF`
- No flow control on the UDP link — large transfers will drop packets
- No checksum/retry mechanism

Possible approaches for future extraction (not attempted, not scoped):

1. **Direct drive mount** — boot HP from USB Linux, mount NTFS, scp
   files over.  Most reliable.  Requires physical access and a Linux
   USB stick.
2. **Forth net-console transfer protocol** — write a Forth word that
   reads a file in chunks, hex-encodes each chunk with a sequence
   number, and sends over UDP.  Receiver reassembles and verifies
   checksums.  Requires new Forth code.
3. **USB stick via ForthOS** — write file data to a FAT32 USB stick
   from Forth, then read on the dev machine.  Requires FAT32 write
   support (partially implemented).

This is future work, not a current task.
