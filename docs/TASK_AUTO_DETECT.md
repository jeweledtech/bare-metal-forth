# Claude Code Task: AUTO-DETECT Vocabulary

## Vision

ForthOS should boot on ANY x86 machine and automatically identify
all hardware, load appropriate vocabularies, initialize devices,
and bring up the network console — zero manual configuration.

Plug in USB or PXE boot → ForthOS boots → hardware detected →
network console up → ready to explore from dev machine terminal.

## Repository

Location: `~/projects/forthos`
New file: `forth/dict/auto-detect.fth`
Add to embedded vocabs in Makefile.

---

## Task: Implement AUTO-DETECT vocabulary

### Device registry

Build a device registry table mapping PCI vendor:device IDs to
initialization words. Each entry:
- Vendor ID (16-bit)
- Device ID (16-bit)
- Device name string
- Init word to call (execution token)

Known devices to include:

```
\ Network controllers
10EC:8168  "RTL8168 GbE"      RTL8168-INIT
10EC:8139  "RTL8139 100M"     (future)
8086:10EA  "Intel I217"       (future)
8086:15A3  "Intel I219"       (future)
14E4:1682  "Broadcom BCM57xx" (future)

\ Storage controllers  
8086:9D03  "Intel AHCI"       AHCI-INIT
8086:2922  "Intel ICH9 AHCI"  AHCI-INIT
8086:3A22  "Intel ICH10 AHCI" AHCI-INIT
1022:7901  "AMD AHCI"         AHCI-INIT

\ USB controllers (for future USB vocab)
8086:9D2F  "Intel xHCI"       (log only for now)

\ Display (log only)
8086:5916  "Intel HD 620"     (log only)
8086:3EA0  "Intel UHD 620"    (log only)
```

### Words to implement

```forth
AUTODET-INIT ( -- )
```
Initialize the detection system. Called once at boot.

```forth
DEVICE-KNOWN? ( vendor device -- flag )
```
Check if vendor:device ID is in the registry.

```forth
DEVICE-INIT ( vendor device -- )
```
Find device in registry and call its init word if present.
Print: `Found: [name] at [bus]:[dev]:[func]`
Print: `Init: [name]... OK` or `Init: [name]... FAILED`

```forth
AUTO-DETECT ( -- )
```
Main word. Runs the full detection sequence:
1. Print header: `=== ForthOS Auto-Detection ===`
2. Run `PCI-SCAN` to populate device list
3. For each device found, check registry and init if known
4. Report summary: `N devices found, N initialized`
5. If a NIC was initialized, bring up network console:
   `NET-CONSOLE-ON` automatically
6. If AHCI was initialized, scan partitions:
   `GPT.` or `MBR.` automatically
7. Print final status

```forth
AUTO-DETECT-REPORT ( -- )
```
Print a formatted report of all detected and initialized hardware.

```forth
BOOT-BANNER ( -- )
```
Print enhanced boot banner showing detected hardware summary.
Called from AUTO-DETECT at the end.

### Boot integration

Add AUTO-DETECT to the kernel boot sequence in embed-vocabs.py.
After loading all vocabularies, the kernel should auto-run:

```forth
AUTO-DETECT
```

This means every PXE or USB boot automatically detects hardware
and brings up the network console if a supported NIC is present.

Add AUTO-DETECT to STRIP_INIT_CALLS — it should NOT auto-run
during QEMU testing (QEMU doesn't have RTL8168 or AHCI).

Actually: add a QEMU-detection heuristic:
- If PCI vendor 1234:1111 is present (QEMU VGA) → skip auto-init
- If PCI vendor 1234:1111 is absent → real hardware → run AUTO-DETECT

```forth
QEMU? ( -- flag )
```
Returns true if running in QEMU (checks for QEMU VGA 1234:1111).

### Run make test — all tests must pass.
### Then commit and make pxe-push.
