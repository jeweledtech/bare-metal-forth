#!/bin/bash
# Setup standalone dnsmasq for PXE DHCP on enp77s0
#
# Architecture:
#   - NetworkManager: manages enp77s0 link with static IP (manual mode)
#   - tftpd-hpa: serves /srv/tftp on port 69 (TFTP)
#   - forthos-pxe dnsmasq: DHCP-only on enp77s0 (no DNS, no TFTP)
#
# This avoids the port 69 conflict that killed NM's built-in dnsmasq
# when enable-tftp was set alongside tftpd-hpa.
#
# Run once on the dev machine (requires sudo)
set -e

ETH_IF="enp77s0"
DEV_IP="10.42.0.1"
HP_MAC="ac:e2:d3:39:0f:40"
CONF="/etc/forthos-pxe-dnsmasq.conf"
SERVICE="forthos-pxe.service"
NM_CON="ForthOS-PXE"

echo "=== Setting up PXE DHCP server (standalone dnsmasq) ==="
echo "  Interface: $ETH_IF"
echo "  Dev IP:    $DEV_IP"
echo "  HP MAC:    $HP_MAC"

# --- Step 1: Clean up old approaches ---

# Disable systemd dnsmasq service (we use our own unit)
if systemctl is-enabled dnsmasq.service > /dev/null 2>&1; then
    echo "Disabling system dnsmasq service..."
    sudo systemctl stop dnsmasq.service 2>/dev/null || true
    sudo systemctl disable dnsmasq.service 2>/dev/null || true
fi

# Remove NM dnsmasq-shared.d config (caused enable-tftp vs tftpd-hpa conflict)
sudo rm -f /etc/NetworkManager/dnsmasq-shared.d/pxe.conf

# Remove old /etc/dnsmasq.d configs
sudo rm -f /etc/dnsmasq.d/pxe.conf /etc/dnsmasq.d/no-dns.conf

# --- Step 2: Switch NM connection to manual (no NM dnsmasq) ---

echo "Switching NM '$NM_CON' to manual mode (static IP, no NM dnsmasq)..."
sudo nmcli con modify "$NM_CON" ipv4.method manual ipv4.addresses "$DEV_IP/24"

# Restart the connection to apply
sudo nmcli con down "$NM_CON" 2>/dev/null || true
sleep 1
sudo nmcli con up "$NM_CON"
sleep 1

# Verify IP is set
if ip addr show "$ETH_IF" | grep -q "$DEV_IP"; then
    echo "  $ETH_IF has $DEV_IP — good"
else
    echo "ERROR: $ETH_IF does not have $DEV_IP"
    exit 1
fi

# --- Step 3: Write dnsmasq config (DHCP-only) ---

echo "Writing dnsmasq config to $CONF..."
sudo tee "$CONF" > /dev/null <<EOF
# ForthOS PXE boot — DHCP only (standalone dnsmasq)
# TFTP handled by tftpd-hpa on port 69
# DNS disabled (port=0)

# Bind only to the direct-cable interface
interface=$ETH_IF
bind-interfaces

# DHCP range on the direct cable
dhcp-range=10.42.0.10,10.42.0.200,12h

# PXE: tell DHCP clients where to TFTP-boot from
# Format: filename, servername, server-address
dhcp-boot=pxelinux.0,,$DEV_IP

# Static lease for the HP laptop
dhcp-host=$HP_MAC,forthbox,10.42.0.50

# Disable DNS listener entirely (port=0)
port=0
no-resolv

# TFTP disabled — tftpd-hpa handles file serving on port 69

# Logging (check with: journalctl -u forthos-pxe -f)
log-dhcp
EOF

# --- Step 4: Create systemd service ---

echo "Creating systemd service $SERVICE..."
sudo tee "/etc/systemd/system/$SERVICE" > /dev/null <<EOF
[Unit]
Description=ForthOS PXE DHCP server (dnsmasq on $ETH_IF)
Documentation=file:///home/bbrown/projects/forthos/tools/pxe/HP-BIOS-SETUP.md
After=network-online.target tftpd-hpa.service
Wants=network-online.target
BindsTo=sys-subsystem-net-devices-${ETH_IF}.device
After=sys-subsystem-net-devices-${ETH_IF}.device

[Service]
Type=simple
ExecStartPre=/bin/sh -c 'ip addr show $ETH_IF | grep -q $DEV_IP'
ExecStart=/usr/sbin/dnsmasq --keep-in-foreground --conf-file=$CONF --log-facility=-
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# --- Step 5: Enable and start ---

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE"

# Stop any stale dnsmasq that might interfere
sudo systemctl stop "$SERVICE" 2>/dev/null || true
sudo systemctl start "$SERVICE"

sleep 2

# --- Step 6: Verify ---

if systemctl is-active "$SERVICE" > /dev/null 2>&1; then
    echo ""
    echo "=== SUCCESS ==="
    echo "  Service: $SERVICE (active)"
    echo "  Config:  $CONF"
    echo "  DHCP:    10.42.0.10 - 10.42.0.200"
    echo "  PXE:     pxelinux.0 via $DEV_IP"
    echo "  HP MAC:  $HP_MAC -> 10.42.0.50 (forthbox)"
    echo "  Log:     journalctl -u forthos-pxe -f"
    echo ""
    echo "DHCP offers will include PXE boot option."
    echo "tftpd-hpa serves the actual boot files on port 69."
else
    echo ""
    echo "ERROR: $SERVICE failed to start"
    echo "Check: journalctl -u forthos-pxe --no-pager -n 20"
    exit 1
fi
