#!/bin/bash
# Label a pushed PXE image (private TASK_PXE_PUSH_LABEL): the menu names
# the image it serves. One function for push.sh and push-grub.sh.
#   label.sh --check <root>    refuse (exit 1) unless <root>/grub/grub.cfg
#                              has a memdisk entry; run BEFORE any copy
#   label.sh <root> <image>    after the copy: write <root>/forth.img.sha256
#                              (sha256sum form), rewrite entry 0's title to
#                              "ForthOS - memdisk <build date, UTC> <sha8>",
#                              read both back
# Writes go through $SUDO (default sudo; the root is root-owned). The
# "ForthOS - memdisk" prefix is what test_g6_chain finds the menu by.
set -e -o pipefail
SUDO="${SUDO-sudo}"
ENTRY='^menuentry "ForthOS( -)? memdisk'

entry_line() {
    [ -f "$1/grub/grub.cfg" ] || {
        echo "ERROR: $1/grub/grub.cfg not found; nothing pushed"
        return 1
    }
    N=$(grep -E -n -m1 "$ENTRY" "$1/grub/grub.cfg" | cut -d: -f1)
    [ -n "$N" ] || {
        echo "ERROR: no memdisk menuentry in $1/grub/grub.cfg; nothing pushed"
        return 1
    }
}

if [ "$1" = "--check" ]; then
    entry_line "${2:?usage: label.sh --check <root>}"
    exit 0
fi

ROOT="${1:?usage: label.sh <root> <image>}"
IMG="${2:?usage: label.sh <root> <image>}"
entry_line "$ROOT"
SHA=$(sha256sum "$IMG" | cut -d' ' -f1)
DATE=$(date -u -r "$IMG" +%F)
TITLE="ForthOS - memdisk $DATE ${SHA:0:8}"

printf '%s  forth.img\n' "$SHA" | $SUDO tee "$ROOT/forth.img.sha256" >/dev/null
$SUDO sed -i "${N}s|.*|menuentry \"$TITLE\" {|" "$ROOT/grub/grub.cfg"

# Read back what landed (deploy provenance discipline)
(cd "$ROOT" && sha256sum --quiet -c forth.img.sha256) || {
    echo "ERROR: $ROOT/forth.img is not $IMG ($SHA)"
    exit 1
}
GOT=$(sed -n "${N}p" "$ROOT/grub/grub.cfg")
[ "$GOT" = "menuentry \"$TITLE\" {" ] || {
    echo "ERROR: entry 0 reads '$GOT', not '$TITLE'"
    exit 1
}
echo "  sha256: $SHA"
echo "  date:   $DATE (build, UTC)"
echo "  title:  $TITLE"
