#!/bin/bash
# make-usb-image.sh — compose a complete, writable ForthOS disk image and its
# release manifest fragment, server-side (CI or a build box). This is the
# non-interactive, loopback-file counterpart of tools/make-uefi-usb.sh, which
# still owns the interactive /dev/sdX path and its NVMe refusal guard.
#
# TRANSITIONAL FORMAT — this composes a GRUB + memdisk carrier image, which is
# exactly what CARRIER-3 (TASK, boot-carrier removal) sets out to delete. It is
# correct for today's boot format and worth having now, but it is NOT the
# permanent release format: CARRIER-3 adds a `usb-image-native` target (no GRUB,
# no memdisk, no FAT32 ESP) that supersedes this one. Do not build a release
# pipeline that assumes this format is forever.
#
# TASK_FORTHOS_CREATOR.md §1 (Option 1, composed image) + §3 (releases.json).
# The Creator app never composes an image; all composition lives here.
#
# Two phases, so the format-critical half can be tested without root:
#   compose  (needs root: losetup/mount/grub-install)  raw .img on a loop file
#   package  (no root)  gzip + sha256 of both + sizes + manifest fragment
#
# Usage:
#   sudo bash tools/make-usb-image.sh            # compose + package (VERSION req.)
#   bash tools/make-usb-image.sh --package-only <raw.img>   # package an existing raw
#
# Env: VERSION (e.g. 0.9.3, required unless --package-only supplies it via NAME),
#      CHANNEL (default stable), OUTDIR (default build/release),
#      RAW_BYTES (default 268435456 = 256 MiB), DL_BASE, NOTES_URL_BASE.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UEFI_SCRIPT="$ROOT/tools/make-uefi-usb.sh"
MEMDISK="/usr/lib/syslinux/memdisk"
IMG_SRC="$ROOT/build/combined.img"        # the memdisk payload = combined.img
KERNEL_BIN="$ROOT/build/kernel.bin"

CHANNEL="${CHANNEL:-stable}"
OUTDIR="${OUTDIR:-$ROOT/build/release}"
RAW_BYTES="${RAW_BYTES:-268435456}"
DL_BASE="${DL_BASE:-https://dl.jeweledtech.com/forthos}"
NOTES_URL_BASE="${NOTES_URL_BASE:-https://forthos.jeweledtech.com/releases}"
TARGET_ID="x86-csm"

die() { echo "make-usb-image: $*" >&2; exit 1; }

# ---- grub.cfg + the EFI build are DERIVED from make-uefi-usb.sh, never copied,
#      so this script and the interactive one cannot drift (test_doc_drift /
#      test_uefi_boot use the same extraction). ----
extract_grubcfg() {
    awk "/<< 'GRUBCFG'/{f=1;next} /^GRUBCFG/{f=0} f" "$UEFI_SCRIPT"
}

# ---- package (no root): gzip, hash both, size both, emit the §3.1 fragment ----
package() {
    local raw="$1" ver="$2"
    [ -f "$raw" ] || die "raw image not found: $raw"
    local base="forthos-${TARGET_ID}-${ver}"
    local gz="$OUTDIR/${base}.img.gz"
    mkdir -p "$OUTDIR"
    gzip -9 -c "$raw" > "$gz"

    local raw_bytes gz_bytes raw_sha gz_sha kernel_bytes released
    raw_bytes=$(stat -c%s "$raw")
    gz_bytes=$(stat -c%s "$gz")
    raw_sha=$(sha256sum "$raw" | cut -d' ' -f1)
    gz_sha=$(sha256sum "$gz" | cut -d' ' -f1)
    kernel_bytes=$([ -f "$KERNEL_BIN" ] && stat -c%s "$KERNEL_BIN" || echo 0)
    released=$(date -u +%Y-%m-%d)

    # sidecar .sha256 files, sha256sum-checkable (two-space format)
    printf '%s  %s\n' "$gz_sha" "${base}.img.gz" > "$gz.sha256"
    printf '%s  %s\n' "$raw_sha" "${base}.img" > "$OUTDIR/${base}.img.sha256"

    # §3.1 images[] entry. schema-exact field names and types.
    cat > "$OUTDIR/${base}.manifest.json" <<JSON
{
  "version": "${ver}",
  "channel": "${CHANNEL}",
  "filename": "${base}.img.gz",
  "url": "${DL_BASE}/${ver}/${base}.img.gz",
  "compressed_bytes": ${gz_bytes},
  "uncompressed_bytes": ${raw_bytes},
  "sha256": "${gz_sha}",
  "sha256_uncompressed": "${raw_sha}",
  "released": "${released}",
  "release_notes_url": "${NOTES_URL_BASE}/${ver}",
  "kernel_bytes": ${kernel_bytes},
  "vocab_set": "free"
}
JSON

    echo "make-usb-image: wrote"
    echo "  $gz  (${gz_bytes} bytes, sha256 ${gz_sha})"
    echo "  $OUTDIR/${base}.img.sha256  (raw ${raw_bytes} bytes, sha256 ${raw_sha})"
    echo "  $OUTDIR/${base}.manifest.json"
    [ "$kernel_bytes" = 0 ] && echo "  NOTE: build/kernel.bin absent; kernel_bytes emitted as 0" >&2
    return 0
}

# ---- compose (needs root): a 256 MiB GPT disk on a loopback file, laid out
#      exactly as make-uefi-usb.sh lays out a stick ----
compose() {
    local ver="$1"
    [ "$(id -u)" -eq 0 ] || die "compose needs root (losetup/mount/grub-install). Run with sudo, or use --package-only on an already-composed raw image."
    [ -f "$IMG_SRC" ] || die "$IMG_SRC not found — run 'make build/combined.img' first"
    [ -f "$MEMDISK" ] || die "syslinux memdisk not found at $MEMDISK (apt install syslinux-common)"
    command -v grub-install >/dev/null || die "grub-install not found (grub-pc-bin)"

    mkdir -p "$OUTDIR"
    local raw="$OUTDIR/forthos-${TARGET_ID}-${ver}.img"
    rm -f "$raw"; truncate -s "$RAW_BYTES" "$raw"

    # GPT: 1 MiB BIOS-boot (ef02) + ESP (ef00) — identical to make-uefi-usb.sh.
    sgdisk --zap-all "$raw" >/dev/null
    sgdisk -n 1:2048:+1M -t 1:ef02 -c 1:"BIOS Boot"  "$raw" >/dev/null
    sgdisk -n 2:0:0      -t 2:ef00 -c 2:"EFI System" "$raw" >/dev/null

    local loop mnt; loop=$(losetup -Pf --show "$raw"); mnt=$(mktemp -d)
    # shellcheck disable=SC2064
    trap "umount '$mnt' 2>/dev/null || true; losetup -d '$loop' 2>/dev/null || true; rmdir '$mnt' 2>/dev/null || true" EXIT

    mkfs.vfat -F 32 -n FORTHBOOT "${loop}p2" >/dev/null
    mount "${loop}p2" "$mnt"
    mkdir -p "$mnt/boot/grub" "$mnt/EFI/BOOT"
    cp "$MEMDISK" "$mnt/memdisk"
    cp "$IMG_SRC" "$mnt/forth.img"
    extract_grubcfg > "$mnt/boot/grub/grub.cfg"
    [ -s "$mnt/boot/grub/grub.cfg" ] || die "extracted grub.cfg is empty (make-uefi-usb.sh heredoc changed)"

    grub-install --target=i386-pc --boot-directory="$mnt/boot" --recheck "$loop" >/dev/null
    grub-mkstandalone --format=x86_64-efi \
        --output="$mnt/EFI/BOOT/BOOTX64.EFI" \
        --locales="" --fonts="" --themes="" \
        "boot/grub/grub.cfg=$mnt/boot/grub/grub.cfg"

    sync; umount "$mnt"; losetup -d "$loop"; rmdir "$mnt"; trap - EXIT
    echo "make-usb-image: composed $raw"
    package "$raw" "$ver"
}

# ---- dispatch ----
if [ "${1:-}" = "--package-only" ]; then
    raw="${2:?usage: --package-only <raw.img>}"
    ver="${VERSION:-$(basename "$raw" | sed -n 's/^forthos-[a-z0-9-]*-\(.*\)\.img$/\1/p')}"
    [ -n "$ver" ] || die "VERSION not set and not derivable from the filename"
    package "$raw" "$ver"
else
    ver="${VERSION:?set VERSION=<x.y.z> (compose mode)}"
    compose "$ver"
fi
