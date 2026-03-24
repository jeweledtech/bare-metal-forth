HP 15-bs0xx PXE Boot Setup
===========================

One-time BIOS configuration to enable PXE network boot.

Setup
-----

1. Power on HP, press F10 for BIOS Setup
2. Go to: Advanced -> Boot Options
3. Enable: "Network (PXE) Boot"
   (may be called "Network Boot" or "LAN Boot")
4. Set boot order: Network first
   (or use F9 at boot to select manually each time)
5. Save and exit

To PXE Boot
-----------

1. Ensure HP is connected via ethernet cable to same
   switch/router as the dev machine
2. On dev machine: make pxe-status (verify services running)
3. On dev machine: make pxe-push (after building)
4. On HP: power on, press F9 for boot menu
5. Select "Network Boot" or "Realtek PXE B04 D00"
6. HP gets IP via DHCP proxy
7. Downloads pxelinux.0 -> memdisk -> forth.img via TFTP
8. ForthOS boots automatically

Dev Workflow
-----------

    edit -> make -> make pxe-push -> F9 on HP -> test

Troubleshooting
--------------

No PXE option in F9 menu:
  - Check BIOS F10 -> Advanced -> Boot Options
  - Enable Network Boot / PXE Boot
  - Some HPs need Secure Boot disabled

HP says "PXE-E32: TFTP open timeout":
  - Check ethernet cable
  - make pxe-status (both services must be active)
  - Check firewall: sudo ufw allow 69/udp
  - Check firewall: sudo ufw allow 67:68/udp
  - Verify dnsmasq log: journalctl -u dnsmasq -f

HP downloads but crashes:
  - Verify image: make pxe-status shows correct md5
  - Try: make clean && make && make pxe-push
  - Ensure pxelinux.cfg/default has "harddisk" not "floppy"

Fallback
--------

USB boot (GRUB + memdisk) still works as before.
Just select USB drive instead of Network Boot in F9 menu.
