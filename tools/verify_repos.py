#!/usr/bin/env python3
"""ForthOS Repo Split Verification
Run from anywhere on your dev machine:
  python3 tools/verify_repos.py

Checks:
1. Public repo has all free files tracked
2. Public repo has NO paid files tracked
3. .gitignore blocks paid files in public repo
4. Private repo has all paid files tracked
5. Local disk has everything for development
6. Makefile doesn't embed paid vocabs
"""
import os, subprocess, sys

PUB = os.path.expanduser("~/projects/forthos")
PRIV = os.path.expanduser("~/projects/forthos-vocabularies")

# Free files that MUST be tracked in public repo
PUB_YES = [
    "src/boot/boot.asm",
    "src/kernel/forth.asm",
    "forth/dict/hardware.fth",
    "forth/dict/port-mapper.fth",
    "forth/dict/echoport.fth",
    "forth/dict/pci-enum.fth",
    "forth/dict/editor.fth",
    "forth/dict/x86-asm.fth",
    "forth/dict/disasm.fth",
    "forth/dict/mirror.fth",
    "forth/dict/ne2000.fth",
    "forth/dict/net-dict.fth",
    "forth/dict/rtl8139.fth",
    "forth/dict/serial-16550.fth",
    "forth/dict/ps2-keyboard.fth",
    "forth/dict/ps2-mouse.fth",
    "forth/dict/pit-timer.fth",
    "forth/dict/vga-graphics.fth",
    "forth/dict/asm-vocab.fth",
    "forth/dict/catalog-resolver.fth",
    "Makefile", "README.md", "LICENSE",
    ".gitignore", "docs/index.html",
]

# Paid files that must NOT be tracked in public
PUB_NO = [
    "forth/dict/ahci.fth",
    "forth/dict/ntfs.fth",
    "forth/dict/fat32.fth",
    "forth/dict/auto-detect.fth",
    "forth/dict/rtl8168.fth",
    "forth/dict/surveyor.fth",
    "forth/dict/graphics.fth",
    "forth/dict/audio.fth",
    "forth/dict/video.fth",
    "forth/dict/meta-compiler.fth",
    "forth/dict/target-x86.fth",
    "forth/dict/target-arm64.fth",
    "forth/dict/arm64-asm.fth",
    "tools/translator/Makefile",
    "tools/translator/src/main/translator.c",
    "tests/test_metacompiler.py",
    "tests/test_meta_compile.py",
    "tests/test_meta_boot.py",
    "tests/test_meta_b6b.py",
    "tests/test_disk_survey.py",
    "tests/test_pipeline_e2e.py",
    "tests/test_arm64_asm.py",
    "tests/test_arm64_target.py",
]

# Files that MUST be tracked in private repo
PRIV_YES = [
    "forth/dict/ahci.fth",
    "forth/dict/ntfs.fth",
    "forth/dict/fat32.fth",
    "forth/dict/auto-detect.fth",
    "forth/dict/rtl8168.fth",
    "forth/dict/surveyor.fth",
    "forth/dict/graphics.fth",
    "forth/dict/audio.fth",
    "forth/dict/video.fth",
    "forth/dict/meta-compiler.fth",
    "forth/dict/target-x86.fth",
    "forth/dict/target-arm64.fth",
    "forth/dict/arm64-asm.fth",
    "tools/translator/Makefile",
    "README.md",
    "tests/test_metacompiler.py",
    "tests/test_disk_survey.py",
    "tests/test_arm64_asm.py",
    "tests/test_arm64_target.py",
]

def tracked(repo):
    r = subprocess.run(["git","ls-files"],
        cwd=repo, capture_output=True, text=True)
    return set(r.stdout.strip().split("\n"))

def ignored(repo, path):
    r = subprocess.run(["git","check-ignore","-q",path],
        cwd=repo, capture_output=True)
    return r.returncode == 0

def section(title, checks):
    print(f"\n{'='*56}")
    print(f"  {title}")
    print(f"{'='*56}")
    p = f = 0
    for ok, msg in checks:
        s = "  OK" if ok else "FAIL"
        print(f"  {s}  {msg}")
        if ok: p += 1
        else: f += 1
    return p, f

def main():
    tp = tf = 0

    # 1. Public tracked
    pt = tracked(PUB)
    c = [(f in pt, f"Tracked: {f}") for f in PUB_YES]
    p,f = section("PUBLIC — Free files tracked", c)
    tp += p; tf += f

    # 2. Public NOT tracked
    c = [(f not in pt, f"Clean: {f}") for f in PUB_NO]
    p,f = section("PUBLIC — Paid files removed", c)
    tp += p; tf += f

    # 3. Gitignore
    c = [(ignored(PUB,f), f"Blocked: {f}")
         for f in PUB_NO[:13]]  # vocab files
    p,f = section("PUBLIC — .gitignore blocks paid", c)
    tp += p; tf += f

    # 4. Private tracked
    pvt = tracked(PRIV)
    c = [(f in pvt, f"Present: {f}") for f in PRIV_YES]
    p,f = section("PRIVATE — Paid files present", c)
    tp += p; tf += f

    # 5. Local disk
    c = [(os.path.exists(os.path.join(PUB,f)),
          f"On disk: {f}") for f in PUB_YES + PUB_NO]
    p,f = section("LOCAL — Everything on disk", c)
    tp += p; tf += f

    # 6. Makefile safety
    with open(os.path.join(PUB,"Makefile")) as mf:
        mk = mf.read()
    embed_line = ""
    for line in mk.split('\n'):
        if line.startswith('EMBED_VOCABS'):
            embed_line = line; break
    c = []
    for v in ["ahci.fth","ntfs.fth","rtl8168.fth",
              "meta-compiler.fth","surveyor.fth"]:
        c.append((v not in embed_line,
                  f"Not embedded: {v}"))
    for v in ["hardware.fth","port-mapper.fth",
              "echoport.fth","pci-enum.fth"]:
        c.append((v in embed_line,
                  f"Embedded: {v}"))
    for t in ["test-pipeline-e2e","test-meta-compile",
              "test-ubt-expansion"]:
        c.append((t not in mk,
                  f"No target: {t}"))
    p,f = section("BUILD — Makefile clean", c)
    tp += p; tf += f

    # Summary
    print(f"\n{'='*56}")
    if tf == 0:
        print(f"  ALL {tp} CHECKS PASSED")
        print(f"  Repos are clean and correct!")
    else:
        print(f"  {tp} passed, {tf} FAILED")
        print(f"  Review failures above!")
    print(f"{'='*56}\n")
    return 0 if tf == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
