#!/bin/bash
# Manifest hash of a staged TFTP tree: sorted per-file md5s,
# hashed. Usage: tree-hash.sh <dir>
# LC_ALL=C: byte-order sort, or the manifest hash is
# locale-dependent and the harness tree assert flaps across
# hosts. Filenames are grub-mknetdir module names plus four
# fixed files -- no spaces/newlines, xargs is safe.
set -e
cd "${1:?usage: tree-hash.sh <dir>}"
find . -type f | LC_ALL=C sort | xargs md5sum | md5sum | cut -d' ' -f1
