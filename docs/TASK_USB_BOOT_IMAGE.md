# ForthOS: USB Boot Image for HP Laptop 15-bs0xx Real Hardware
**Date:** 2026-03-21  
**Status:** Ready for the toolchain  
**Commit base:** `93f7142` (234 tests passing)  
**Hardware target:** HP Laptop 15-bs0xx (Intel Core i3-7200U, Kaby Lake, 2017)  
**Serial:** CND74032JF / Product: 1TJ84UA#ABA  

---

## Objective

Boot ForthOS on real bare-metal hardware. The HP 15-bs0xx is an x86 laptop with standard i386+ compatible hardware — the existing ForthOS kernel should run directly. The goal is:

1. Build a USB-bootable ForthOS image (wrapping the existing floppy-format kernel)
2. Disable Secure Boot on the HP BIOS (required — unsigned bootloader)
3. Boot ForthOS from USB alongside Windows (dual-boot via HP boot menu)
4. Optionally: extract Windows drivers from `C:\Windows\System32\drivers\` while still in Windows, run through UBT pipeline, generate Forth vocabularies for the real hardware

---

## Hardware Notes

**CPU:** Intel Core i3-7200U (Kaby Lake) — x86-64, runs 32-bit protected mode fine  
**Storage:** HDD or SSD (ATA PIO should work; AHCI may require legacy mode in BIOS)  
**Boot:** UEFI with Secure Boot — must disable before unsigned bootloader runs  
**USB boot:** HP boot menu via **F9** at startup; BIOS setup via **F10**

---

## Step 0 — Pre-Boot: Extract Windows Drivers (Do This First)

Before touching the boot configuration, extract the actual hardware drivers from the running Windows installation. These are the `.sys` files for the real hardware on this specific laptop.

Run from Windows Command Prompt (as Administrator) or PowerShell:

```powershell
# Copy key hardware drivers to a staging folder
mkdir C:\forth-drivers
copy C:\Windows\System32\drivers\i8042prt.sys C:\forth-drivers\
copy C:\Windows\System32\drivers\usbhid.sys C:\forth-drivers\
copy C:\Windows\System32\drivers\kbdhid.sys C:\forth-drivers\
copy C:\Windows\System32\drivers\ACPI.sys C:\forth-drivers\
copy C:\Windows\System32\drivers\storport.sys C:\forth-drivers\
copy C:\Windows\System32\drivers\disk.sys C:\forth-drivers\
copy C:\Windows\System32\drivers\NVLDDMKM.sys C:\forth-drivers\ 2>nul  # if NVIDIA
copy C:\Windows\System32\drivers\pci.sys C:\forth-drivers\
copy C:\Windows\System32\drivers\serial.sys C:\forth-drivers\
```

Then copy `C:\forth-drivers\` to the development machine via USB drive or network. Run the UBT pipeline against each:

```bash
for f in /path/to/forth-drivers/*.sys; do
    echo "=== $(basename $f) ==="
    tools/translator/bin/translator -t semantic-report "$f" | \
        python3 -c "import sys,json; d=json.load(sys.stdin); \
        s=d['summary']; print(f'HW: {s[\"hardware_functions\"]}, \
        Scaffolding: {s[\"scaffolding_functions\"]}')"
done
```

This gives you the real hardware vocabulary collection for this specific machine before doing anything disruptive to the boot configuration.

---

## Step 1 — Disable Secure Boot

1. Restart the laptop and press **F10** immediately to enter BIOS Setup
2. Navigate to **Security** → **Secure Boot**
3. Set Secure Boot to **Disabled**
4. Save and exit (F10 again)

Without this, the BIOS will refuse to boot any unsigned bootloader including ForthOS.

**Optional — Enable Legacy Boot (if needed):**  
If UEFI-only mode prevents USB boot, also enable:
- **Advanced** → **Boot Options** → check **Legacy Support**
- This gives you a traditional MBR boot path which the ForthOS bootloader uses

---

## Step 2 — Build the USB Boot Image

The current ForthOS image (`build/bmforth.img`) is a 1.44MB floppy-format image. It boots fine in QEMU with `-drive file=...,if=floppy` but a USB drive needs to appear as a bootable hard disk with a proper MBR.

### Option A: Direct dd to USB (simplest, works with legacy BIOS boot)

```bash
# Build the combined image first
make clean && make && make write-catalog

# Write directly to USB drive (REPLACE /dev/sdX with your actual USB device)
# WARNING: double-check the device — this overwrites everything
lsblk  # identify your USB drive
sudo dd if=build/bmforth.img of=/dev/sdX bs=512 conv=sync
sudo sync
```

The ForthOS bootloader is a standard MBR-compatible 512-byte boot sector — `dd` to a USB drive is sufficient for legacy BIOS boot. The USB will appear as a bootable floppy-emulation device on most BIOS/UEFI-with-legacy systems.

### Option B: Hybrid ISO (works with both UEFI and legacy)

If Option A doesn't boot, create a proper hybrid ISO using `isolinux` or `grub-mkrescue`:

```bash
# Install tools if needed
sudo apt-get install grub-pc-bin xorriso

# Create directory structure
mkdir -p /tmp/forthiso/boot/grub
cp build/bmforth.img /tmp/forthiso/forth.img

# Create GRUB config
cat > /tmp/forthiso/boot/grub/grub.cfg << 'EOF'
set timeout=5
set default=0

menuentry "ForthOS" {
    linux16 /forth.img
}

menuentry "ForthOS (memdisk)" {
    insmod memdisk
    set root=(memdisk)
    linux16 /boot/memdisk
    initrd16 /forth.img
}
EOF

# Build the ISO
grub-mkrescue -o /tmp/forthiso.iso /tmp/forthiso

# Write to USB
sudo dd if=/tmp/forthiso.iso of=/dev/sdX bs=4M conv=sync
```

### Option C: SYSLINUX/memdisk (most reliable for floppy images)

```bash
# Install syslinux
sudo apt-get install syslinux syslinux-utils

# Format USB with FAT32
sudo mkfs.vfat /dev/sdX1

# Install syslinux MBR
sudo syslinux --install /dev/sdX1

# Copy memdisk and the ForthOS image
sudo mount /dev/sdX1 /mnt/usb
sudo cp /usr/lib/syslinux/memdisk /mnt/usb/
sudo cp build/bmforth.img /mnt/usb/forth.img

# Create syslinux config
sudo tee /mnt/usb/syslinux.cfg << 'EOF'
DEFAULT forth
LABEL forth
    MENU LABEL ForthOS
    KERNEL memdisk
    APPEND initrd=forth.img floppy
EOF

sudo umount /mnt/usb
```

**Recommended approach:** Try Option A first (2 minutes, no extra tools). If it doesn't boot, use Option C (memdisk is the most reliable way to boot a floppy image from USB on real hardware).

---

## Step 3 — Boot from USB

1. Insert USB drive
2. Restart laptop, press **F9** immediately for HP Boot Menu
3. Select your USB drive (will appear as "USB Hard Drive" or similar)
4. ForthOS should boot to the `ok` prompt

**Expected boot sequence:**
```
ForthOS booting...
Forth-83 kernel ready
ok
```

If the ATA disk is not detected, type:
```forth
\ Check ATA status
1 BLOCK .   \ try to read block 1
```

The ATA PIO driver reads from the first IDE/SATA device in compatibility mode. The laptop's HDD/SSD needs to be in **AHCI mode** (or IDE compatibility mode) — check BIOS → Storage → Controller Mode if blocks don't read.

---

## Step 4 — ATA/SATA Compatibility

The HP 15-bs0xx likely uses AHCI for its SATA controller. The ForthOS ATA PIO driver uses the legacy ATA command interface (ports 0x1F0-0x1F7) which works when the SATA controller is in **AHCI mode** because AHCI includes legacy ATA compatibility.

However, if `BLOCK` fails:
1. Enter BIOS Setup (F10)
2. Go to **Storage** → **SATA Controller Mode**
3. Try switching between AHCI and IDE modes
4. Test with AHCI first (it's the default and usually works)

To verify ATA is responding from ForthOS:
```forth
HEX
1F7 INB .    \ read ATA status register
             \ 0x50 = DRDY (drive ready, no error)
             \ 0x00 = no drive detected
             \ other = check error bits
```

---

## Step 5 — Test and Validate

Once booted:

```forth
\ Basic sanity check
1 2 + .     \ should print 3

\ Block storage test
1 BLOCK C@ .     \ read first byte of block 1
                 \ should print something non-zero if blocks loaded

\ Load vocabularies (after writing blocks.img to a drive)
209 223 THRU     \ load PCI-ENUM
USING PCI-ENUM
PCI-SCAN         \ enumerate real PCI devices on this hardware
```

The PCI scan will show the real hardware: Intel HD Graphics, Intel HDA audio, possibly Intel WiFi, the AHCI controller, USB xHCI host controller. Each of these could eventually become a vocabulary.

---

## Step 6 — Blocks Image on Real Disk (Optional)

The blocks.img file contains all the Forth vocabularies. To load them on real hardware, the blocks image needs to be accessible. Options:

**Option A: Write blocks.img to USB second partition**
```bash
# Partition 1: ForthOS boot image
# Partition 2: Forth blocks data
sudo fdisk /dev/sdX  # create partition 2
sudo mkfs.ext2 /dev/sdX2  # or raw partition
sudo dd if=build/blocks.img of=/dev/sdX2
```

Then in ForthOS, point the block reader at the second partition. This requires modifying the ATA driver to read from a specific LBA offset — add a `BLOCKS-LBA-BASE` variable to `hardware.fth`.

**Option B: Embed blocks.img in the combined image**
```bash
# Combine boot image + blocks into one image
cat build/bmforth.img build/blocks.img > build/combined.img
sudo dd if=build/combined.img of=/dev/sdX bs=512 conv=sync
```

The bootloader loads the kernel from the first 32KB. The blocks start at offset 1024×512 = 512KB. The ATA driver already reads from LBA 0 for block 0 — adjust the `BLOCK` word's LBA calculation to offset by the kernel size.

**Easiest for first boot:** Skip blocks on first test, just verify the kernel boots and ATA is accessible.

---

## Success Criteria

- [ ] ForthOS boots from USB to `ok` prompt on real hardware
- [ ] `1 2 + .` prints `3` (basic interpreter working)
- [ ] `1F7 INB .` returns `0x50` (ATA controller responding)
- [ ] `PCI-SCAN` lists real devices (after loading PCI-ENUM via THRU)
- [ ] Serial output visible on COM1 (if connected) or VGA screen

## Known Constraints

- Secure Boot must be disabled — ForthOS has no signing infrastructure
- UEFI native boot not supported — requires legacy BIOS mode or UEFI-CSM
- AHCI in BIOS compatibility mode required for ATA PIO driver
- No ACPI, no power management, no APIC — runs on basic 8259 PIC
- Screen output uses VGA text mode (port 0xB8000) — works on any x86 with VGA-compatible graphics
