#!/bin/bash
# check-coverage.sh — fail if a hardware-device vocabulary exists in forth/dict/
# but HARDWARE-COVERAGE.md does not name it. Makes coverage staleness a build
# failure instead of a thing someone has to remember (the 2026-09-29 miss:
# pci-enum/rtl8168/xhci shipped while the doc still said PLANNED).
#
# Scope: only device-class vocabularies, selected by the catalog CATEGORY field.
# UI/app/form/gui/system/tools/substrate and generated 'driver' output are not
# hardware coverage and are skipped. Only files PRESENT are checked, so a public
# clone without the paid vocabularies still passes. "Named" means the basename
# appears somewhere in the doc — it asserts the vocab is accounted for, with
# whatever status, not that it is claimed covered.
# No set -e: walk every vocab and report the full miss list, not die on
# the first grep that finds nothing.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DOC="${1:-$ROOT/HARDWARE-COVERAGE.md}"    # optional arg: alternate doc, for tests
DICT="$ROOT/forth/dict"
HW_CATS=" pci network usb storage serial timer input audio video filesystem "

[ -f "$DOC" ] || { echo "check-coverage: $DOC missing"; exit 1; }
miss=""
for f in "$DICT"/*.fth; do
    cat=$(grep -m1 '\\ CATEGORY:' "$f" 2>/dev/null | sed 's/.*CATEGORY: *//' | tr -d '[:space:]')
    [ -n "$cat" ] || continue
    case "$HW_CATS" in *" $cat "*) ;; *) continue ;; esac
    base=$(basename "$f")
    grep -qF "$base" "$DOC" || miss="$miss$base ($cat)\n"
done
if [ -n "$miss" ]; then
    echo "check-coverage: FAIL — hardware vocabularies not named in HARDWARE-COVERAGE.md:"
    printf "  %b" "$miss"
    echo "  Add each to the doc (any status) so coverage cannot go stale."
    exit 1
fi
echo "check-coverage: OK — every present hardware-category vocabulary is named in HARDWARE-COVERAGE.md"
