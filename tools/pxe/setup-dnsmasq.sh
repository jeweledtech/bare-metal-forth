#!/bin/bash
# Setup PXE boot via NetworkManager's dnsmasq on enp77s0
#
# NetworkManager already runs its own dnsmasq instance on shared
# connections (enp77s0 10.42.0.1/24). We can't run a second dnsmasq —
# NM's instance already binds the address. Instead, we add PXE config
# to NM's dnsmasq-shared.d directory and restart the connection.
#
# Run once on the dev machine (requires sudo)
set -e

ETH_IF="enp77s0"
DEV_IP="10.42.0.1"
NM_SHARED_DIR="/etc/NetworkManager/dnsmasq-shared.d"

echo "=== Setting up PXE boot via NetworkManager dnsmasq ==="
echo "  Interface: $ETH_IF"
echo "  TFTP server: $DEV_IP"

# Disable the systemd dnsmasq service — NM runs its own
if systemctl is-enabled dnsmasq.service > /dev/null 2>&1; then
    echo "Disabling systemd dnsmasq (NM runs its own)..."
    sudo systemctl stop dnsmasq.service 2>/dev/null || true
    sudo systemctl disable dnsmasq.service 2>/dev/null || true
fi

# Remove our old /etc/dnsmasq.d configs (they conflict with NM)
sudo rm -f /etc/dnsmasq.d/pxe.conf /etc/dnsmasq.d/no-dns.conf

# Write PXE config into NM's dnsmasq shared config dir
sudo mkdir -p "$NM_SHARED_DIR"
sudo tee "$NM_SHARED_DIR/pxe.conf" > /dev/null <<EOF
# ForthOS PXE boot — added to NetworkManager's dnsmasq
# NM already handles DHCP (10.42.0.10-254); we just add PXE + TFTP

# PXE: tell DHCP clients where to find the boot file
# Format: filename, servername, server-address
dhcp-boot=pxelinux.0,,$DEV_IP

# TFTP: serve boot files from /srv/tftp
enable-tftp
tftp-root=/srv/tftp

# Log DHCP for debugging
log-dhcp
EOF

echo "PXE config written to $NM_SHARED_DIR/pxe.conf"

# Find the NM connection name for enp77s0
NM_CON=$(nmcli -t -f NAME,DEVICE con show --active | grep "$ETH_IF" | cut -d: -f1)
if [ -z "$NM_CON" ]; then
    echo "WARNING: No active NM connection on $ETH_IF"
    echo "  Trying to restart NetworkManager instead..."
    sudo systemctl restart NetworkManager
else
    echo "Restarting NM connection '$NM_CON' to reload dnsmasq config..."
    sudo nmcli con down "$NM_CON" 2>/dev/null || true
    sleep 2
    sudo nmcli con up "$NM_CON"
fi

# Wait for dnsmasq to start
sleep 3

# Verify NM's dnsmasq is running with our config
NM_PID=$(pgrep -f "dnsmasq.*$ETH_IF" || true)
if [ -n "$NM_PID" ]; then
    echo ""
    echo "NM dnsmasq running (pid $NM_PID) on $ETH_IF"
    # Check if our TFTP config was picked up
    if cat /proc/$NM_PID/cmdline 2>/dev/null | tr '\0' ' ' | grep -q "dnsmasq-shared"; then
        echo "  Config dir: $NM_SHARED_DIR (loaded)"
    fi
    echo "  PXE boot file: pxelinux.0"
    echo "  TFTP root: /srv/tftp"
    echo ""
    echo "Test: HP should now get PXE boot option in DHCP offers"
else
    echo ""
    echo "WARNING: NM dnsmasq not found on $ETH_IF"
    echo "  Check: nmcli con show --active"
    echo "  Check: journalctl -u NetworkManager --since '1 minute ago'"
fi
