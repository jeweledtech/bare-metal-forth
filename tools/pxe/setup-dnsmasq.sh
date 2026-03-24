#!/bin/bash
# Setup dnsmasq as PXE DHCP proxy
# Proxy mode: adds PXE options without replacing existing DHCP server
# Run once on the dev machine (requires sudo)
set -e

echo "=== Setting up dnsmasq PXE proxy ==="

sudo apt-get install -y dnsmasq

# Find the wired ethernet interface (skip lo and wlan)
ETH_IF=$(ip -o link show | grep -v lo | grep -v wlan | grep -v docker | awk -F': ' '{print $2}' | head -1)
if [ -z "$ETH_IF" ]; then
    echo "ERROR: No wired ethernet interface found"
    echo "Available interfaces:"
    ip -o link show | awk -F': ' '{print $2}'
    exit 1
fi
echo "Using interface: $ETH_IF"

# Get dev machine IP on that interface
DEV_IP=$(ip -o -4 addr show "$ETH_IF" | awk '{print $4}' | cut -d/ -f1)
if [ -z "$DEV_IP" ]; then
    echo "ERROR: No IPv4 address on $ETH_IF"
    echo "Is the ethernet cable connected?"
    exit 1
fi
echo "Dev machine IP: $DEV_IP"

# Write PXE proxy config
sudo tee /etc/dnsmasq.d/pxe.conf > /dev/null <<EOF
# PXE proxy mode for ForthOS dev workflow
# Does NOT replace existing DHCP — only adds PXE boot options
interface=$ETH_IF
dhcp-range=$DEV_IP,proxy
dhcp-boot=pxelinux.0
enable-tftp
tftp-root=/srv/tftp
log-dhcp
EOF

# Disable default dnsmasq DNS to avoid conflicts
# (we only want DHCP proxy + TFTP)
sudo tee /etc/dnsmasq.d/no-dns.conf > /dev/null <<EOF
port=0
EOF

sudo systemctl enable dnsmasq
sudo systemctl restart dnsmasq

echo ""
echo "dnsmasq PXE proxy running on $ETH_IF ($DEV_IP)"
echo "PXE boot file: pxelinux.0"
echo "TFTP root: /srv/tftp"
