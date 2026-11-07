#!/usr/bin/env python3
"""Copy the private files a public tree expects (private TASK_SYNC_COPIES).

For each path the private repo tracks (git -C <private> ls-files):
  - skipped, and listed, if this repo tracks it: never overwritten;
  - copied to <dest>/<path> if this repo's .gitignore ignores it
    (git check-ignore --no-index), only when absent or different;
  - otherwise left out (neither tracked nor ignored here).
The ignore rules and the tracked list always come from this repo (the
current directory). --dest may be any directory, such as a git archive
export with no .git.

  python3 tools/sync_copies.py [--private DIR] [--dest DIR] [--dry-run]

--private defaults to $PRIVATE_REPO, else ../forthos-vocabularies.
Run after every clone, pull or merge, and for export-based rebuilds.
Prints one line per path acted on (copied: / would copy: / FAILED: /
skipped (tracked here):), then once:
  sync-copies: N private-tracked files at paths ignored here; C copied,
  E already equal, F failed; K skipped (tracked here)
Exit 1 if any copy fails, or if --private is not a git work tree.
"""
import argparse
import filecmp
import os
import shutil
import subprocess
import sys


def git(d, *args, stdin=None, ok=(0,)):
    r = subprocess.run(['git', '-C', d, *args], input=stdin, capture_output=True)
    if r.returncode not in ok:
        sys.exit(f'sync-copies: git {" ".join(args)} in {d} failed: {r.stderr.decode().strip()}')
    return r.stdout


def toplevel(d):
    r = subprocess.run(['git', '-C', d, 'rev-parse', '--show-toplevel'], capture_output=True, text=True)
    return os.path.realpath(r.stdout.strip()) if r.returncode == 0 else None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--private', default=os.environ.get('PRIVATE_REPO') or '../forthos-vocabularies')
    ap.add_argument('--dest', default='.')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    public = os.getcwd()
    if toplevel(public) != os.path.realpath(public):
        print(f'sync-copies: run from the public repo\'s root ({public} is not one)')
        return 1
    if not os.path.isdir(a.private) or toplevel(a.private) != os.path.realpath(a.private):
        print(f'sync-copies: --private {a.private} is not a git work tree')
        return 1

    private = [p for p in git(a.private, 'ls-files', '-z').decode().split('\0') if p]
    tracked = {p for p in git(public, 'ls-files', '-z').decode().split('\0') if p}
    skipped = [p for p in private if p in tracked]
    rest = [p for p in private if p not in tracked]
    out = git(public, 'check-ignore', '--no-index', '-z', '--stdin',
              stdin='\0'.join(rest).encode() + b'\0', ok=(0, 1)) if rest else b''
    ignored = {p for p in out.decode().split('\0') if p}
    selected = [p for p in rest if p in ignored]

    copied = equal = failed = 0
    for p in selected:
        src = os.path.join(a.private, p)
        dst = os.path.join(a.dest, p)
        try:
            if os.path.isfile(dst) and filecmp.cmp(src, dst, shallow=False):
                equal += 1
                continue
            if a.dry_run:
                print(f'would copy: {p}')
                copied += 1
                continue
            os.makedirs(os.path.dirname(dst) or '.', exist_ok=True)
            shutil.copyfile(src, dst)
            shutil.copymode(src, dst)
            print(f'copied: {p}')
            copied += 1
        except OSError as e:
            print(f'FAILED: {p}: {e.strerror or e}')
            failed += 1
    for p in skipped:
        print(f'skipped (tracked here): {p}')

    tag = 'sync-copies (dry run)' if a.dry_run else 'sync-copies'
    verb = 'would be copied' if a.dry_run else 'copied'
    print(f'{tag}: {len(selected)} private-tracked files at paths ignored here; {copied} {verb}, '
          f'{equal} already equal, {failed} failed; {len(skipped)} skipped (tracked here)')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
