#!/bin/bash
# Verify the full ForthOS PXE boot stack
# Run via: make pxe-status
set -u

ETH_IF="enp77s0"
DEV_IP="10.42.0.1"
HP_MAC="ac:e2:d3:39:0f:40"
TFTP_ROOT="/srv/tftp"
PASS=0
FAIL=0
WARN=0

pass() { echo "  [OK]   $1"; PASS=$((PASS + 1)); }
fail() { echo "  [FAIL] $1"; FAIL=$((FAIL + 1)); }
warn() { echo "  [WARN] $1"; WARN=$((WARN + 1)); }

echo "=== ForthOS PXE Boot Stack Verification ==="
echo ""

# --- 1. Network interface ---
echo "--- Interface: $ETH_IF ---"
if ip link show "$ETH_IF" > /dev/null 2>&1; then
    STATE=$(ip -o link show "$ETH_IF" | grep -o 'state [A-Z]*' | cut -d' ' -f2)
    if [ "$STATE" = "UP" ]; then
        pass "$ETH_IF is UP"
    else
        fail "$ETH_IF is $STATE (cable connected?)"
    fi
else
    fail "$ETH_IF does not exist"
fi

if ip addr show "$ETH_IF" 2>/dev/null | grep -q "$DEV_IP"; then
    pass "$ETH_IF has $DEV_IP"
else
    fail "$ETH_IF missing IP $DEV_IP"
fi
echo ""

# --- 2. DHCP server (forthos-pxe dnsmasq) ---
echo "--- DHCP: forthos-pxe.service ---"
if systemctl is-active forthos-pxe.service > /dev/null 2>&1; then
    pass "forthos-pxe.service is active"
else
    fail "forthos-pxe.service is not running"
    echo "       Fix: make pxe-setup"
fi

if systemctl is-enabled forthos-pxe.service > /dev/null 2>&1; then
    pass "forthos-pxe.service is enabled (survives reboot)"
else
    warn "forthos-pxe.service is not enabled"
fi

# Check dnsmasq is listening on DHCP port (67) on the right interface
if ss -ulnp 2>/dev/null | grep -q ':67 '; then
    pass "DHCP server listening on port 67"
else
    fail "Nothing listening on DHCP port 67"
fi

# Check config has dhcp-boot
if [ -f /etc/forthos-pxe-dnsmasq.conf ]; then
    if grep -q "dhcp-boot=pxelinux.0" /etc/forthos-pxe-dnsmasq.conf; then
        pass "dhcp-boot=pxelinux.0 configured"
    else
        fail "dhcp-boot missing from config"
    fi
    if grep -q "^enable-tftp" /etc/forthos-pxe-dnsmasq.conf; then
        fail "Config has enable-tftp (conflicts with tftpd-hpa!)"
    else
        pass "No enable-tftp (tftpd-hpa handles TFTP)"
    fi
else
    fail "/etc/forthos-pxe-dnsmasq.conf not found"
fi
echo ""

# --- 3. TFTP server ---
echo "--- TFTP: tftpd-hpa ---"
if systemctl is-active tftpd-hpa > /dev/null 2>&1; then
    pass "tftpd-hpa is active"
else
    fail "tftpd-hpa is not running"
fi

if ss -ulnp 2>/dev/null | grep -q ':69 '; then
    pass "TFTP server listening on port 69"
else
    fail "Nothing listening on TFTP port 69"
fi
echo ""

# --- 4. Boot files in TFTP root ---
echo "--- Boot files: $TFTP_ROOT ---"
for FILE in pxelinux.0 ldlinux.c32 memdisk forth.img; do
    if [ -f "$TFTP_ROOT/$FILE" ]; then
        SIZE=$(stat -c%s "$TFTP_ROOT/$FILE" 2>/dev/null)
        pass "$FILE ($SIZE bytes)"
    else
        fail "$FILE missing"
    fi
done

if [ -f "$TFTP_ROOT/pxelinux.cfg/default" ]; then
    pass "pxelinux.cfg/default exists"
    # Verify it references memdisk + forth.img
    if grep -q "memdisk" "$TFTP_ROOT/pxelinux.cfg/default" && \
       grep -q "forth.img" "$TFTP_ROOT/pxelinux.cfg/default"; then
        pass "Boot menu references memdisk + forth.img"
    else
        warn "Boot menu may be misconfigured"
    fi
else
    fail "pxelinux.cfg/default missing (run: make pxe-setup)"
fi
echo ""

# --- 5. TFTP transfer test ---
echo "--- TFTP transfer test (localhost) ---"
if command -v tftp > /dev/null 2>&1; then
    # Test pxelinux.0
    TMPDIR=$(mktemp -d)
    if timeout 5 tftp "$DEV_IP" -c get pxelinux.0 "$TMPDIR/pxelinux.0" 2>/dev/null && \
       [ -s "$TMPDIR/pxelinux.0" ]; then
        pass "pxelinux.0 retrievable via TFTP"
    else
        fail "Cannot retrieve pxelinux.0 via TFTP"
    fi
    # Test forth.img
    if timeout 5 tftp "$DEV_IP" -c get forth.img "$TMPDIR/forth.img" 2>/dev/null && \
       [ -s "$TMPDIR/forth.img" ]; then
        pass "forth.img retrievable via TFTP"
    else
        fail "Cannot retrieve forth.img via TFTP"
    fi
    rm -rf "$TMPDIR"
else
    warn "tftp client not installed (apt install tftp) — skipping transfer test"
fi
echo ""

# --- 6. Conflict checks ---
echo "--- Conflict checks ---"
# NM dnsmasq should NOT be running
if pgrep -f "dnsmasq.*NetworkManager" > /dev/null 2>&1; then
    warn "NM dnsmasq still running (may conflict)"
else
    pass "No NM dnsmasq running"
fi

# System dnsmasq should NOT be running
if systemctl is-active dnsmasq.service > /dev/null 2>&1; then
    fail "System dnsmasq.service is active (will conflict)"
else
    pass "System dnsmasq.service is not active"
fi

# Check for stale NM shared config
if [ -f /etc/NetworkManager/dnsmasq-shared.d/pxe.conf ]; then
    warn "Stale NM config: /etc/NetworkManager/dnsmasq-shared.d/pxe.conf"
else
    pass "No stale NM dnsmasq config"
fi
echo ""

# --- 7. HP laptop lease ---
echo "--- HP laptop (MAC $HP_MAC) ---"
LEASE_FILE="/var/lib/misc/dnsmasq.leases"
# dnsmasq with --conf-file may use a different lease file
for LF in "$LEASE_FILE" /var/lib/dnsmasq/dnsmasq.leases /tmp/forthos-pxe.leases; do
    if [ -f "$LF" ] && grep -qi "$HP_MAC" "$LF" 2>/dev/null; then
        LEASE=$(grep -i "$HP_MAC" "$LF")
        pass "HP has DHCP lease: $LEASE"
        break
    fi
done
# Also check ARP table
if ip neigh show dev "$ETH_IF" 2>/dev/null | grep -qi "${HP_MAC//:/ }\\|$HP_MAC"; then
    HP_IP=$(ip neigh show dev "$ETH_IF" | grep -i "$HP_MAC" | awk '{print $1}')
    pass "HP visible in ARP table: $HP_IP"
else
    warn "HP not in ARP table (not powered on or not connected?)"
fi
echo ""

# --- 8. Firewall ---
echo "--- Firewall ---"
if command -v ufw > /dev/null 2>&1 && ufw status 2>/dev/null | grep -q "active"; then
    # Check if DHCP/TFTP ports are allowed
    if ufw status | grep -q "67"; then
        pass "UFW allows port 67 (DHCP)"
    else
        warn "UFW may block port 67 (DHCP) — run: sudo ufw allow 67/udp"
    fi
    if ufw status | grep -q "69"; then
        pass "UFW allows port 69 (TFTP)"
    else
        warn "UFW may block port 69 (TFTP) — run: sudo ufw allow 69/udp"
    fi
else
    pass "No active firewall (UFW inactive or not installed)"
fi
echo ""

# --- Summary ---
echo "==========================================="
echo "  PASS: $PASS   FAIL: $FAIL   WARN: $WARN"
echo "==========================================="
if [ $FAIL -eq 0 ]; then
    echo ""
    echo "PXE stack is ready. On the HP laptop:"
    echo "  1. Press F9 at boot"
    echo "  2. Select 'Network Boot' or 'Realtek PXE B04 D00'"
    echo "  3. ForthOS boots in ~5 seconds"
else
    echo ""
    echo "Fix the FAIL items above, then re-run: make pxe-status"
    exit 1
fi
