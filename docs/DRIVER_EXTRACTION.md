# Bare-Metal Forth Driver Extraction System

## Overview

This system extracts hardware manipulation code from Windows drivers (`.sys` files) and generates portable Forth modules that can run on Bare-Metal Forth bare metal.

## The Key Insight

Windows drivers contain two distinct types of code:

```
┌─────────────────────────────────────────────────────────────┐
│                    DRIVER.SYS                               │
├─────────────────────────────────────────────────────────────┤
│  WINDOWS SCAFFOLDING (filtered out)                         │
│  ├─ DriverEntry, AddDevice                                  │
│  ├─ IRP handlers (IRP_MJ_READ, IRP_MJ_WRITE, etc.)         │
│  ├─ Power management (PoSetPowerState, etc.)               │
│  ├─ Plug and Play (IoRegisterDeviceInterface, etc.)        │
│  ├─ Registry access (ZwOpenKey, ZwQueryValueKey)           │
│  └─ Synchronization (KeAcquireSpinLock, etc.)              │
├─────────────────────────────────────────────────────────────┤
│  HARDWARE PROTOCOL (extracted)                              │
│  ├─ Port I/O (READ_PORT_UCHAR, WRITE_PORT_UCHAR)           │
│  ├─ Memory-mapped I/O (READ_REGISTER_ULONG, MmMapIoSpace)  │
│  ├─ Timing (KeStallExecutionProcessor)                      │
│  ├─ DMA setup (IoAllocateMdl, MmGetPhysicalAddress)        │
│  └─ PCI configuration (HalGetBusData)                       │
└─────────────────────────────────────────────────────────────┘
```

The hardware doesn't know it's talking to Windows. It just sees register reads/writes and timing. **Those are universal.**

## System Architecture

```
                    ┌──────────────┐
                    │  driver.sys  │
                    └──────┬───────┘
                           │
                           ▼
              ┌────────────────────────┐
              │  PE Loader (pe_loader.h)│
              └────────────┬───────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │  x86 Decoder           │
              │  (x86_decoder.h)       │
              │  99.95% instruction    │
              │  coverage              │
              └────────────┬───────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │  Driver Extractor      │
              │  (driver_extract.h)    │
              │  - API categorization  │
              │  - Pattern recognition │
              │  - Sequence filtering  │
              └────────────┬───────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │  UIR (Universal IR)    │
              │  (uir.h)               │
              │  Platform-independent  │
              │  representation        │
              └────────────┬───────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │  Forth Code Generator  │
              │  Generates .fth module │
              └────────────┬───────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │  module.fth  │
                    │  Installable │
                    │  driver      │
                    └──────────────┘
```

## Dictionary System

Bare-Metal Forth uses a dictionary-based module system:

```forth
\ Load base hardware primitives
USING HARDWARE

\ Load a driver module
USING RTL8139

\ Load multiple drivers
USING AHCI
USING USB-EHCI
USING VGA

\ The dictionaries chain together
\ Each can use words from previously loaded dictionaries
```

### Available Dictionaries

| Dictionary | Description | Depends On |
|------------|-------------|------------|
| `FORTH` | Base Forth-83 words | (built-in) |
| `HARDWARE` | Port I/O, MMIO, PCI, timing | FORTH |
| `RTL8139` | RealTek NIC driver | HARDWARE |
| `AHCI` | SATA controller | HARDWARE |
| `VGA` | VGA text/graphics | HARDWARE |
| `USB-EHCI` | USB 2.0 host | HARDWARE |
| `ATA` | IDE/PATA disk | HARDWARE |

## Hardware Primitives

The `HARDWARE` dictionary provides these foundational words:

### Port I/O
```forth
C@-PORT  ( port -- byte )       \ Read byte from I/O port
C!-PORT  ( byte port -- )       \ Write byte to I/O port
W@-PORT  ( port -- word )       \ Read 16-bit word
W!-PORT  ( word port -- )       \ Write 16-bit word
@-PORT   ( port -- dword )      \ Read 32-bit dword
!-PORT   ( dword port -- )      \ Write 32-bit dword
```

### Timing
```forth
US-DELAY ( us -- )              \ Busy-wait microseconds
MS-DELAY ( ms -- )              \ Busy-wait milliseconds
RDTSC@   ( -- low high )        \ Read CPU timestamp counter
```

### PCI Configuration
```forth
PCI-READ  ( bus dev func reg -- value )
PCI-WRITE ( value bus dev func reg -- )
PCI-SCAN  ( -- )                \ List all PCI devices
```

### Memory-Mapped I/O
```forth
C@-MMIO  ( addr -- byte )       \ Read MMIO byte
C!-MMIO  ( byte addr -- )       \ Write MMIO byte
@-MMIO   ( addr -- dword )      \ Read MMIO dword
!-MMIO   ( dword addr -- )      \ Write MMIO dword
```

## Example: Extracted RTL8139 Driver

```forth
\ File: rtl8139.fth
\ Extracted from Windows rtl8139.sys

USING HARDWARE

MARKER --RTL8139--

\ Register offsets (from Windows driver)
$00 CONSTANT RTL-IDR0       \ MAC address
$37 CONSTANT RTL-CMD        \ Command register
$3C CONSTANT RTL-IMR        \ Interrupt mask
$3E CONSTANT RTL-ISR        \ Interrupt status

\ Command bits
$10 CONSTANT CMD-RESET
$04 CONSTANT CMD-TE         \ TX enable
$08 CONSTANT CMD-RE         \ RX enable

VARIABLE RTL-BASE

: RTL-C@  ( offset -- byte )  RTL-BASE @ + C@-PORT ;
: RTL-C!  ( byte offset -- )  RTL-BASE @ + C!-PORT ;

\ Reset sequence (extracted from Windows driver)
: RTL-RESET  ( -- )
    CMD-RESET RTL-CMD RTL-C!
    1000 0 DO
        RTL-CMD RTL-C@ CMD-RESET AND 0= IF
            UNLOOP EXIT
        THEN
        1 US-DELAY
    LOOP
    ." Reset timeout!" CR
;

: RTL-INIT  ( base-port -- )
    RTL-BASE !
    RTL-RESET
    \ ... rest of initialization
;
```

## API Categorization

The driver extractor recognizes 60+ Windows driver APIs:

### Hardware Access (EXTRACTED)
| Windows API | Forth Equivalent | Category |
|-------------|------------------|----------|
| `READ_PORT_UCHAR` | `C@-PORT` | PORT-IO |
| `WRITE_PORT_UCHAR` | `C!-PORT` | PORT-IO |
| `READ_REGISTER_ULONG` | `@-MMIO` | MMIO |
| `MmMapIoSpace` | `MAP-PHYS` | MMIO |
| `KeStallExecutionProcessor` | `US-DELAY` | TIMING |
| `HalGetBusData` | `PCI-READ` | PCI |

### Windows Scaffolding (FILTERED OUT)
| Windows API | Category | Why Filtered |
|-------------|----------|--------------|
| `IoCompleteRequest` | IRP | Windows I/O model |
| `PoSetPowerState` | POWER | Windows power manager |
| `IoRegisterDeviceInterface` | PNP | Windows PnP |
| `KeAcquireSpinLock` | SYNC | Windows sync primitives |

## Module Installation

```forth
\ Boot Bare-Metal Forth
Bare-Metal Forth v0.1 - The Ship Builder's OS
ok

\ Load hardware primitives
USING HARDWARE
CPU: GenuineIntel
Calibrated: 1847 loops/us
HARDWARE dictionary loaded
ok

\ Scan for devices
PCI-SCAN
Bus Dev Fun  Vendor:Device
  0   0   0  8086:1237      \ Host bridge
  0   1   0  8086:7000      \ ISA bridge  
  0   2   0  10EC:8139      \ <-- RTL8139!
  0   3   0  8086:7010      \ IDE controller
ok

\ Load the driver
USING RTL8139
RTL8139 driver module loaded
ok

\ Initialize it
$C000 $200000 RTL-INIT
RTL8139 initializing at port $C000
MAC: 52:54:00:12:34:56
Link: UP at 100 Mbps
RTL8139 ready
ok
```

## Files in This Package

```
driver_extract.h        - Driver extraction API header
driver_extract.c        - Implementation with API recognition table
dict_system.fth         - USING word and dictionary infrastructure
dict/hardware.fth       - Low-level hardware primitives dictionary
examples/rtl8139.fth    - Complete RTL8139 driver example
```

## Building the Extractor

```bash
# Compile the driver extraction tool
gcc -DDRIVER_EXTRACT_MAIN \
    -o drv-extract \
    driver_extract.c \
    x86_decoder.c \
    pe_loader.c \
    uir.c \
    semantic.c

# Extract a driver
./drv-extract realtek.sys rtl8139.fth

# Output:
# Bare-Metal Forth Driver Extraction Tool v0.1
# ====================================
# 
# Input: realtek.sys
# Found 47 functions
# Hardware access functions: 12
# Filtered (Windows scaffolding): 35
# 
# Generated: rtl8139.fth
```

## What Gets Extracted vs. Filtered

### Extracted (Hardware Protocol)
- Direct `IN`/`OUT` instructions
- Calls to `READ_PORT_*` / `WRITE_PORT_*`
- Calls to `READ_REGISTER_*` / `WRITE_REGISTER_*`
- Timing loops with `KeStallExecutionProcessor`
- PCI configuration access
- DMA buffer setup

### Filtered (Windows Scaffolding)
- IRP handling code
- Power management callbacks
- Plug and Play state machines
- Registry access
- Unicode string manipulation
- Object manager calls
- Thread/synchronization primitives

## Limitations

1. **Complex State Machines**: Some drivers have elaborate state machines for error recovery that may not translate cleanly.

2. **Interrupt Handling**: The ISR logic is extracted, but wiring it to your IDT is manual.

3. **DMA Descriptors**: The descriptor ring setup is extracted, but you need to allocate physically contiguous memory yourself.

4. **Firmware Blobs**: Some drivers load firmware to the device. We can extract the upload sequence but not recreate proprietary firmware.

5. **GPU Drivers**: Modern GPU drivers are extremely complex (millions of lines). Basic SVGA/VBE works; full 3D acceleration is a massive undertaking.

## The Philosophy

> "The hardware doesn't care what OS is running. It just sees register writes and timing."

This system extracts the *conversation with the hardware* and throws away the *conversation with Windows*. Your Bare-Metal Forth speaks the same language to the hardware that Windows does—just without the middleman.
