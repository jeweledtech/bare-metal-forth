#!/bin/bash
# Push built ForthOS image to TFTP server for PXE boot
# Usage: bash tools/pxe/push.sh [image-path]
set -e

TFTP_ROOT=/srv/tftp
IMG="${1:-build/combined.img}"

if [ ! -f "$IMG" ]; then
    echo "ERROR: $IMG not found. Run 'make' first."
    exit 1
fi

sudo cp "$IMG" "$TFTP_ROOT/forth.img"

SIZE=$(stat -c%s "$IMG")
MD5=$(md5sum "$IMG" | cut -d' ' -f1)

echo "Pushed $IMG -> $TFTP_ROOT/forth.img"
echo "  Size: $SIZE bytes"
echo "  MD5:  $MD5"
echo ""
echo "HP can now PXE boot to get the new image."
echo "On HP: press F9, select Network Boot (or Realtek PXE)"
