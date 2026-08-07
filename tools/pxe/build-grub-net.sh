#!/bin/bash
# Stage the GRUB-PXE netboot tree into build/tftp/.
# Idempotent, no sudo. Config placement is load-bearing:
# netboot GRUB loads <prefix>/grub.cfg, and --subdir=grub makes
# the prefix (tftp)/grub -- so the cfg MUST land at
# build/tftp/grub/grub.cfg. A misplaced cfg surfaces as a silent
# menu-less GRUB prompt (leg A would catch it; don't make it).
set -e
cd "$(dirname "$0")/../.."
TREE=build/tftp

command -v grub-mknetdir >/dev/null || {
    echo "ERROR: grub-mknetdir not found (apt install grub-pc-bin)"
    exit 1
}
[ -f build/combined.img ] || {
    echo "ERROR: build/combined.img missing. Run 'make' first."
    exit 1
}

rm -rf "$TREE"
grub-mknetdir --net-directory="$TREE" --subdir=grub \
    >/dev/null 2>&1
[ -f "$TREE/grub/i386-pc/core.0" ] || {
    echo "ERROR: grub-mknetdir produced no i386-pc/core.0"
    exit 1
}

python3 tools/pxe/gen-grub-cfg.py -o "$TREE/grub/grub.cfg"

# memdisk: same binary the pxelinux tree serves, new home.
MEMDISK=""
for M in /usr/lib/syslinux/memdisk /usr/share/syslinux/memdisk \
         /srv/tftp/memdisk; do
    [ -f "$M" ] && MEMDISK="$M" && break
done
[ -n "$MEMDISK" ] || {
    echo "ERROR: memdisk not found (apt install syslinux-common)"
    exit 1
}
cp "$MEMDISK" "$TREE/memdisk"
cp build/combined.img "$TREE/forth.img"

echo "Staged $TREE:"
echo "  memdisk:   $MEMDISK"
echo "  forth.img: $(md5sum build/combined.img | cut -d' ' -f1)"
echo "  manifest:  $(bash tools/pxe/tree-hash.sh "$TREE")"
