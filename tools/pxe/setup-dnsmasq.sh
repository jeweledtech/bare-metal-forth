#!/bin/bash
# Setup dnsmasq as full DHCP + TFTP server for PXE boot
# Direct cable: dev machine (enp77s0, 10.42.0.1) → HP laptop
# Run once on the dev machine (requires sudo)
set -e

ETH_IF="enp77s0"
DEV_IP="10.42.0.1"
DHCP_START="10.42.0.100"
DHCP_END="10.42.0.200"
DHCP_LEASE="12h"

echo "=== Setting up dnsmasq DHCP + PXE server ==="
echo "  Interface: $ETH_IF"
echo "  Dev IP:    $DEV_IP"
echo "  DHCP pool: $DHCP_START - $DHCP_END"

sudo apt-get install -y dnsmasq

# Verify interface exists and has the expected IP
if ! ip link show "$ETH_IF" > /dev/null 2>&1; then
    echo "ERROR: Interface $ETH_IF not found"
    echo "Available interfaces:"
    ip -o link show | awk -F': ' '{print "  " $2}'
    exit 1
fi

ACTUAL_IP=$(ip -o -4 addr show "$ETH_IF" 2>/dev/null | awk '{print $4}' | cut -d/ -f1)
if [ "$ACTUAL_IP" != "$DEV_IP" ]; then
    echo "WARNING: $ETH_IF has IP $ACTUAL_IP (expected $DEV_IP)"
    echo "  Continuing anyway — verify your network config"
fi

# Write DHCP + PXE + TFTP config (full server, not proxy)
sudo tee /etc/dnsmasq.d/pxe.conf > /dev/null <<EOF
# ForthOS PXE boot server — full DHCP on direct cable to HP
# bind-interfaces is CRITICAL: prevents conflict with systemd-resolved
interface=$ETH_IF
bind-interfaces

# DHCP: serve 10.42.0.100-200 on the direct cable
dhcp-range=$DHCP_START,$DHCP_END,$DHCP_LEASE

# PXE: tell clients to boot pxelinux.0 from our TFTP
dhcp-boot=pxelinux.0

# TFTP server (built-in)
enable-tftp
tftp-root=/srv/tftp

# Disable DNS (port=0) — we only serve DHCP + TFTP
# no-resolv prevents reading /etc/resolv.conf
port=0
no-resolv

# Logging
log-dhcp
EOF

# Remove old no-dns.conf if present (now merged into pxe.conf)
sudo rm -f /etc/dnsmasq.d/no-dns.conf

sudo systemctl enable dnsmasq
sudo systemctl restart dnsmasq

echo ""
echo "dnsmasq running on $ETH_IF ($DEV_IP)"
echo "  DHCP: $DHCP_START - $DHCP_END (lease $DHCP_LEASE)"
echo "  PXE boot file: pxelinux.0"
echo "  TFTP root: /srv/tftp"
echo "  DNS: disabled (port=0, bind-interfaces)"
