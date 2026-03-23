#!/bin/bash
# make-uefi-usb.sh — Create dual-mode (UEFI + Legacy/CSM) bootable USB for ForthOS
# Usage: sudo bash tools/make-uefi-usb.sh /dev/sdX
#
# Creates a USB that boots ForthOS via syslinux memdisk:
#   - Legacy/CSM mode: GRUB BIOS → linux16 memdisk → ForthOS in real mode
#   - UEFI mode: GRUB EFI → menu explaining CSM is required
#
set -euo pipefail

DEVICE="${1:-}"
IMGPATH="/home/bbrown/projects/forthos/build/bmforth.img"
MEMDISK="/usr/lib/syslinux/memdisk"
MOUNTPOINT="/mnt/forthusb"

if [ -z "$DEVICE" ]; then
    echo "Usage: sudo bash $0 /dev/sdX"
    exit 1
fi

if [ "$(id -u)" -ne 0 ]; then
    echo "Error: must run as root (sudo)"
    exit 1
fi

if [ ! -f "$IMGPATH" ]; then
    echo "Error: $IMGPATH not found. Run 'make' first."
    exit 1
fi

if [ ! -f "$MEMDISK" ]; then
    echo "Error: syslinux memdisk not found at $MEMDISK"
    echo "Install with: sudo apt install syslinux-common"
    exit 1
fi

# Safety: refuse to touch NVMe (system drives)
if [[ "$DEVICE" == *nvme* ]]; then
    echo "Error: refusing to write to NVMe device (system drive)"
    exit 1
fi

DEVSIZE=$(lsblk -bno SIZE "$DEVICE" 2>/dev/null | head -1)
DEVMODEL=$(lsblk -no MODEL "$DEVICE" 2>/dev/null | head -1 | xargs)
echo "=== ForthOS UEFI+Legacy USB Builder ==="
echo "Device:  $DEVICE"
echo "Size:    $(( DEVSIZE / 1048576 )) MB"
echo "Model:   $DEVMODEL"
echo ""
echo "WARNING: This will DESTROY all data on $DEVICE"
echo "Press Enter to continue, Ctrl+C to abort..."
read

# Step 1: Unmount and wipe
echo "[1/8] Unmounting and wiping $DEVICE..."
umount ${DEVICE}* 2>/dev/null || true
wipefs -af "$DEVICE"
dd if=/dev/zero of="$DEVICE" bs=1M count=10 status=none  # zero first 10MB (GPT + partitions)

# Step 2: Create GPT with BIOS boot + ESP
echo "[2/8] Creating GPT partition table..."
sgdisk --zap-all "$DEVICE"
sgdisk -n 1:2048:+1M   -t 1:ef02 -c 1:"BIOS Boot"  "$DEVICE"   # BIOS boot partition
sgdisk -n 2:0:+200M    -t 2:ef00 -c 2:"EFI System"  "$DEVICE"   # EFI System Partition
partprobe "$DEVICE"
sleep 1

# Step 3: Format ESP as FAT32
echo "[3/8] Formatting ESP as FAT32..."
mkfs.vfat -F 32 -n FORTHBOOT "${DEVICE}2"

# Step 4: Mount and create directory structure
echo "[4/8] Mounting and copying files..."
mkdir -p "$MOUNTPOINT"
mount "${DEVICE}2" "$MOUNTPOINT"
mkdir -p "$MOUNTPOINT/boot/grub"
mkdir -p "$MOUNTPOINT/EFI/BOOT"

# Step 5: Copy memdisk and ForthOS image
cp "$MEMDISK"  "$MOUNTPOINT/memdisk"
cp "$IMGPATH"  "$MOUNTPOINT/forth.img"

# Step 6: Write grub.cfg
echo "[5/8] Writing GRUB configuration..."
cat > "$MOUNTPOINT/boot/grub/grub.cfg" << 'GRUBCFG'
set timeout=3
set default=0

if [ "$grub_platform" = "pc" ]; then
    # BIOS/Legacy/CSM mode — this path actually boots ForthOS
    menuentry "ForthOS — Bare Metal Forth" {
        linux16 /memdisk raw
        initrd16 /forth.img
    }
    menuentry "Reboot" {
        reboot
    }
else
    # UEFI mode — cannot boot 16-bit real-mode code directly
    menuentry "ForthOS — Boot via Legacy/CSM (select this USB as non-UEFI)" {
        echo ""
        echo "  ForthOS is a 16-bit real-mode bare-metal kernel."
        echo "  UEFI mode cannot execute real-mode code."
        echo ""
        echo "  To boot ForthOS:"
        echo "    1. Reboot and enter BIOS Setup (F10 on HP)"
        echo "    2. Enable Legacy Support / CSM"
        echo "    3. Boot Menu (F9) -> select this USB WITHOUT 'UEFI:' prefix"
        echo ""
        echo "  Press Enter to reboot to BIOS Setup, or ESC for GRUB shell."
        read
        fwsetup
    }
    menuentry "Reboot to BIOS Setup" {
        fwsetup
    }
    menuentry "GRUB Command Line" {
        commandline
    }
fi
GRUBCFG

# Step 7: Install GRUB for BIOS (i386-pc) — writes to BIOS boot partition
echo "[6/8] Installing GRUB for BIOS/Legacy boot..."
grub-install --target=i386-pc \
    --boot-directory="$MOUNTPOINT/boot" \
    --recheck \
    "$DEVICE"

# Step 8: Build and install GRUB EFI standalone
echo "[7/8] Building GRUB EFI standalone image..."
grub-mkstandalone --format=x86_64-efi \
    --output="$MOUNTPOINT/EFI/BOOT/BOOTX64.EFI" \
    --locales="" \
    --fonts="" \
    --themes="" \
    "boot/grub/grub.cfg=$MOUNTPOINT/boot/grub/grub.cfg"

# Done
echo "[8/8] Syncing and unmounting..."
sync
umount "$MOUNTPOINT"
rmdir "$MOUNTPOINT"

echo ""
echo "=== SUCCESS ==="
echo "USB device $DEVICE is now a dual-mode ForthOS boot drive."
echo ""
echo "On the HP laptop:"
echo "  1. Insert USB, power on, press F9 for Boot Menu"
echo "  2. Select the USB entry WITHOUT 'UEFI:' prefix"
echo "  3. GRUB will load -> 'ForthOS — Bare Metal Forth' boots automatically in 3s"
echo ""
echo "Files on ESP:"
ls -la "$MOUNTPOINT" 2>/dev/null || true
lsblk -o NAME,SIZE,TYPE,FSTYPE,LABEL "$DEVICE"
