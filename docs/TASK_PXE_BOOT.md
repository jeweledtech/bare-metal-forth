# Claude Code Task: PXE Network Boot Dev Workflow

## Context

ForthOS boots on the HP 15-bs0xx via SanDisk USB + GRUB + memdisk.
The current dev cycle is:

  edit → make → cp to USB → walk to HP → boot → test

This is too slow. We need:

  edit → make → push → HP reboots automatically → test

The HP has a wired ethernet port. PXE (Preboot Execution Environment)
is built into every PC BIOS/UEFI and allows booting from the network.
The dev machine (jollygeniusinc workstation) serves the image over TFTP.
The HP boots it without touching the USB drive.

Repository: `~/projects/forthos`
Dev machine: `jollygeniusinc` (Ubuntu, wired ethernet to same switch as HP)

---

## Task: Implement PXE Boot Dev Server

### What we want

```bash
make pxe-push    # build + restart TFTP server with new image
                 # HP reboots and PXE-boots the new image
```

On the HP side: select "Network Boot" (or it auto-selects via BIOS boot order).
No USB required after initial setup.

---

## Part 1: Dev Machine Setup

### 1a. TFTP server

Install and configure a TFTP server on the dev machine.

Script: `tools/pxe/setup-tftp.sh`

```bash
#!/bin/bash
# Install tftpd-hpa
sudo apt-get install -y tftpd-hpa syslinux-common pxelinux

# TFTP root
TFTP_ROOT=/srv/tftp
sudo mkdir -p $TFTP_ROOT/pxelinux.cfg

# Copy pxelinux bootloader
sudo cp /usr/lib/PXELINUX/pxelinux.0 $TFTP_ROOT/
sudo cp /usr/lib/syslinux/modules/bios/ldlinux.c32 $TFTP_ROOT/
sudo cp /usr/lib/syslinux/modules/bios/memdisk $TFTP_ROOT/

# Configure tftpd-hpa
sudo tee /etc/default/tftpd-hpa <<EOF
TFTP_USERNAME="tftp"
TFTP_DIRECTORY="$TFTP_ROOT"
TFTP_ADDRESS=":69"
TFTP_OPTIONS="--secure --create"
EOF

sudo systemctl enable tftpd-hpa
sudo systemctl restart tftpd-hpa
echo "TFTP server running at $TFTP_ROOT"
```

### 1b. DHCP / BOOTP (minimal)

We need the HP to get an IP and be told where to find pxelinux.0.
Use `dnsmasq` in proxy mode — it doesn't replace any existing DHCP
server, just adds PXE boot responses.

Script: `tools/pxe/setup-dnsmasq.sh`

```bash
#!/bin/bash
sudo apt-get install -y dnsmasq

# Get the ethernet interface name
ETH_IF=$(ip -o link show | grep -v lo | grep -v wlan | awk -F': ' '{print $2}' | head -1)
echo "Using interface: $ETH_IF"

# Get dev machine IP on that interface  
DEV_IP=$(ip -o -4 addr show $ETH_IF | awk '{print $4}' | cut -d/ -f1)
echo "Dev machine IP: $DEV_IP"

sudo tee /etc/dnsmasq.d/pxe.conf <<EOF
# PXE proxy mode — don't replace existing DHCP, just add PXE responses
interface=$ETH_IF
dhcp-range=$DEV_IP,proxy
dhcp-boot=pxelinux.0
enable-tftp
tftp-root=/srv/tftp
log-dhcp
EOF

sudo systemctl enable dnsmasq
sudo systemctl restart dnsmasq
echo "dnsmasq PXE proxy running"
echo "TFTP serving from /srv/tftp"
echo "PXE boot file: pxelinux.0"
```

### 1c. PXE menu config

File: `/srv/tftp/pxelinux.cfg/default`

```
DEFAULT forthos
LABEL forthos
  MENU LABEL ForthOS - Bare Metal Forth
  KERNEL memdisk
  APPEND initrd=forth.img harddisk
  IPAPPEND 2
```

Script `tools/pxe/install-pxelinux-cfg.sh` to install this file.

### 1d. Push script

Script: `tools/pxe/push.sh`

```bash
#!/bin/bash
set -e
TFTP_ROOT=/srv/tftp
IMG=build/bmforth.img

if [ ! -f "$IMG" ]; then
    echo "ERROR: $IMG not found. Run make first."
    exit 1
fi

sudo cp "$IMG" "$TFTP_ROOT/forth.img"
echo "Pushed $IMG -> $TFTP_ROOT/forth.img"
echo "HP can now PXE boot to get the new image"
echo "On HP: press F9, select Network Boot (or LAN)"
```

---

## Part 2: Makefile targets

Add to `Makefile`:

```makefile
# PXE dev workflow targets
.PHONY: pxe-setup pxe-push pxe-status

pxe-setup:
	@echo "Setting up PXE boot server..."
	@bash tools/pxe/setup-tftp.sh
	@bash tools/pxe/setup-dnsmasq.sh
	@bash tools/pxe/install-pxelinux-cfg.sh
	@echo "PXE setup complete."

pxe-push: build/bmforth.img
	@bash tools/pxe/push.sh

pxe-status:
	@echo "=== TFTP server ==="
	@systemctl status tftpd-hpa --no-pager | head -5
	@echo "=== dnsmasq ==="
	@systemctl status dnsmasq --no-pager | head -5
	@echo "=== TFTP files ==="
	@ls -la /srv/tftp/
	@echo "=== forth.img hash ==="
	@md5sum /srv/tftp/forth.img 2>/dev/null || echo "forth.img not yet pushed"
```

---

## Part 3: HP BIOS setup (document only — manual step)

Document in `tools/pxe/HP-BIOS-SETUP.md`:

```
HP 15-bs0xx PXE Boot Setup
===========================

1. Power on HP, press F10 for BIOS Setup
2. Go to: Advanced → Boot Options
3. Enable: "Network (PXE) Boot" (may be called "Network Boot" or "LAN Boot")
4. Set boot order: Network first (or use F9 at boot to select manually)
5. Save and exit

To PXE boot:
- Ensure HP is connected via ethernet to same switch as dev machine
- Ensure dev machine's PXE server is running (make pxe-status)
- Run: make pxe-push  (after building)  
- On HP: press F9, select "Network Boot" or "Realtek PXE"
- HP gets IP via DHCP proxy, downloads pxelinux.0, downloads forth.img
- ForthOS boots automatically

Fallback: USB boot still works as before.
```

---

## Part 4: Faster iteration — serial console (optional enhancement)

Once PXE works, add serial console output from ForthOS so you can see
the HP's output on the dev machine without looking at the screen.

The HP 15-bs0xx has no physical serial port, but a USB-to-serial adapter
(FTDI or CH340) plugged into the HP's USB port would give us a virtual
COM port. However, this requires a USB driver in ForthOS — complex.

**Simpler alternative: VGA framebuffer capture via HDMI capture card.**
If the HP is connected to a monitor, use an HDMI capture card (USB) on
the dev machine to see the HP's screen remotely.

**For now: PXE is sufficient.** Capture the screen with a phone camera
as we have been doing.

---

## Part 5: Automated test integration (future)

Once PXE + serial are working, `make test-hw` could:
1. `make` to build
2. `make pxe-push` to deploy
3. Send a magic packet to wake the HP (Wake-on-LAN if supported)
4. Read serial output to verify boot and run test words
5. Report pass/fail

This is Phase 2 — not part of this task. Just ensure the PXE
infrastructure doesn't preclude it.

---

## Deliverables checklist

- [ ] `tools/pxe/setup-tftp.sh` — TFTP server install + config
- [ ] `tools/pxe/setup-dnsmasq.sh` — DHCP proxy for PXE
- [ ] `tools/pxe/install-pxelinux-cfg.sh` — PXE menu config
- [ ] `tools/pxe/push.sh` — push built image to TFTP root
- [ ] `tools/pxe/HP-BIOS-SETUP.md` — manual HP config instructions
- [ ] `Makefile` — `pxe-setup`, `pxe-push`, `pxe-status` targets
- [ ] Tested: `make pxe-setup` runs without error on dev machine
- [ ] Tested: `make pxe-push` copies image to `/srv/tftp/forth.img`
- [ ] Tested: `make pxe-status` shows both services running
- [ ] README section added: "PXE Boot Development Workflow"

---

## Commit message

```
Add PXE network boot dev workflow

- tools/pxe/: TFTP server, dnsmasq DHCP proxy, push script
- Makefile: pxe-setup, pxe-push, pxe-status targets
- Replaces USB sneakernet with: make pxe-push → HP network boots
- dnsmasq runs in proxy mode, no conflict with existing DHCP
- Fallback USB boot unchanged
```
