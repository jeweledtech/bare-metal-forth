#!/bin/bash
# Manifest hash of a staged TFTP tree: sorted per-file md5s,
# hashed. Usage: tree-hash.sh <dir>
set -e
cd "${1:?usage: tree-hash.sh <dir>}"
find . -type f | sort | xargs md5sum | md5sum | cut -d' ' -f1
