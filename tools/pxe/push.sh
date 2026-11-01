#!/bin/bash
# Push built ForthOS image to TFTP server for PXE boot
# Usage: bash tools/pxe/push.sh [image-path]
set -e

TFTP_ROOT="${TFTP_ROOT:-/srv/tftp}"
SUDO="${SUDO-sudo}"
IMG="${1:-build/combined.img}"

if [ ! -f "$IMG" ]; then
    echo "ERROR: $IMG not found. Run 'make' first."
    exit 1
fi

LABEL="$(dirname "$0")/label.sh"
SUDO="$SUDO" bash "$LABEL" --check "$TFTP_ROOT"

$SUDO cp "$IMG" "$TFTP_ROOT/forth.img"

SIZE=$(stat -c%s "$IMG")

echo "Pushed $IMG -> $TFTP_ROOT/forth.img"
echo "  Size: $SIZE bytes"
SUDO="$SUDO" bash "$LABEL" "$TFTP_ROOT" "$IMG"
echo ""
echo "HP can now PXE boot to get the new image."
echo "On HP: press F9, select Network Boot (or Realtek PXE)"
