#!/bin/bash
# Setup TFTP server for PXE boot of ForthOS
# Run once on the dev machine (requires sudo)
set -e

echo "=== Setting up TFTP server for PXE boot ==="

# Install packages
sudo apt-get install -y tftpd-hpa syslinux-common pxelinux

# TFTP root directory
TFTP_ROOT=/srv/tftp
sudo mkdir -p "$TFTP_ROOT/pxelinux.cfg"

# Copy pxelinux bootloader and memdisk
sudo cp /usr/lib/PXELINUX/pxelinux.0 "$TFTP_ROOT/"
sudo cp /usr/lib/syslinux/modules/bios/ldlinux.c32 "$TFTP_ROOT/"
sudo cp /usr/lib/syslinux/modules/bios/memdisk "$TFTP_ROOT/"

# Configure tftpd-hpa
sudo tee /etc/default/tftpd-hpa > /dev/null <<EOF
TFTP_USERNAME="tftp"
TFTP_DIRECTORY="$TFTP_ROOT"
TFTP_ADDRESS=":69"
TFTP_OPTIONS="--secure --create"
EOF

sudo systemctl enable tftpd-hpa
sudo systemctl restart tftpd-hpa

echo ""
echo "TFTP server running at $TFTP_ROOT"
echo "Files installed:"
ls -la "$TFTP_ROOT/"
