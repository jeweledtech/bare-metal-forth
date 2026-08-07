#!/bin/bash
# Copy the staged GRUB tree to /srv/tftp ALONGSIDE pxelinux
# (no filename collisions: grub/, memdisk, forth.img vs
# pxelinux.0, pxelinux.cfg/). Prints deploy provenance.
# PRINTS the dnsmasq cutover line; NEVER applies it -- the
# cutover is an iron-session step with a written rollback
# (spec D1, RUNBOOK-G6.md step 2).
set -e -o pipefail
cd "$(dirname "$0")/../.."
TREE=build/tftp
TFTP_ROOT=/srv/tftp

[ -d "$TREE/grub" ] || {
    echo "ERROR: $TREE not staged. Run 'make grub-net' first."
    exit 1
}

echo "Provenance (staged tree):"
(cd "$TREE" && find . -type f -exec md5sum {} \; | sort -k2 |
    while read -r m f; do
        printf '  %s  %8d  %s\n' "$m" \
            "$(stat -c%s "$f")" "$f"
    done)
MANIFEST=$(bash tools/pxe/tree-hash.sh "$TREE")
echo "  manifest: $MANIFEST"

sudo cp -r "$TREE"/. "$TFTP_ROOT"/

# Verify what actually landed (deploy provenance discipline):
# hash only the files we own -- /srv/tftp also holds the pxelinux
# tree. This subset equals the staged tree's FULL manifest by
# construction (the staged tree contains exactly these files), so
# the two computations agree by design, not coincidence.
DEP=$( (cd "$TFTP_ROOT" &&
    find ./grub ./memdisk ./forth.img -type f | LC_ALL=C sort |
    xargs md5sum | md5sum | cut -d' ' -f1) )
STG=$( (cd "$TREE" &&
    find ./grub ./memdisk ./forth.img -type f | LC_ALL=C sort |
    xargs md5sum | md5sum | cut -d' ' -f1) )
if [ "$DEP" != "$STG" ]; then
    echo "ERROR: deployed tree hash $DEP != staged $STG"
    echo "Remediation: rerun 'make pxe-push-grub' (recopies staged"
    echo "tree); do NOT cut dnsmasq over until DEP == STG."
    exit 1
fi
echo "Deployed OK: our-files hash $DEP"
echo ""
echo "=== CUTOVER (manual, iron session ONLY -- not applied) ==="
echo "In the dnsmasq config, change:"
echo "    dhcp-boot=pxelinux.0"
echo "to:"
echo "    dhcp-boot=grub/i386-pc/core.0"
echo "then restart dnsmasq. ROLLBACK = revert that one line."
