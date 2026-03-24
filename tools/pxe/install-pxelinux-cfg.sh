#!/bin/bash
# Install pxelinux boot menu config
# Tells pxelinux to chain-load memdisk with ForthOS image
set -e

TFTP_ROOT=/srv/tftp
CFG_DIR="$TFTP_ROOT/pxelinux.cfg"

sudo mkdir -p "$CFG_DIR"

sudo tee "$CFG_DIR/default" > /dev/null <<'EOF'
DEFAULT forthos
PROMPT 0
TIMEOUT 30

LABEL forthos
  MENU LABEL ForthOS - Bare Metal Forth
  KERNEL memdisk
  APPEND initrd=forth.img harddisk
  IPAPPEND 2
EOF

echo "PXE menu config installed at $CFG_DIR/default"
echo ""
echo "Boot chain: PXE ROM -> pxelinux.0 -> memdisk -> forth.img"
echo "  TIMEOUT 30 = 3 second auto-boot (10ths of a second)"
echo "  harddisk = memdisk emulates image as hard disk"
