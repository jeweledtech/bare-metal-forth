#!/usr/bin/env python3
"""Print the kernel's free pad: KERNEL_PADDED_SIZE minus the kernel content
(the kernel assembled once more without its final padding line).  Run by
the kernel rule on every build; the floor itself is the KERNEL_PAD_FLOOR
assert in forth.asm, which fails the build.

  python3 tools/pad_report.py src/kernel/forth.asm <scratch dir>
"""
import os
import re
import subprocess
import sys

asm, scratch = sys.argv[1], sys.argv[2]
src = open(asm).read()
pad = int(re.search(r'^KERNEL_PADDED_SIZE\s+equ\s+0x([0-9A-Fa-f]+)', src, re.M).group(1), 16)
floor = int(re.search(r'^KERNEL_PAD_FLOOR\s+equ\s+(\d+)', src, re.M).group(1))
lines = src.split('\n')
k = [i for i, l in enumerate(lines) if l.startswith('times KERNEL_PADDED_SIZE - ($ - $$) db 0')]
if len(k) != 1:
    sys.exit(f'pad_report: expected one padding line in {asm}, found {len(k)}')
os.makedirs(scratch, exist_ok=True)
nopad = os.path.join(scratch, 'forth-nopad.asm')
open(nopad, 'w').write('\n'.join(lines[:k[0]] + lines[k[0] + 1:]))
out = os.path.join(scratch, 'kernel-nopad.bin')
subprocess.run(['nasm', '-f', 'bin', '-I', os.path.dirname(asm) + '/', '-o', out, nopad], check=True)
content = os.path.getsize(out)
print(f'kernel pad: {pad - content} B free of {pad} (content {content}; floor {floor})')
