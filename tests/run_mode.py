#!/usr/bin/env python3
"""The run mode of a test whose subject is partly private (private
TASK_TEST_COUNT_LINES, Part B): one rule, every caller.

PRIVATE_REPO and PRIVATE_REPO_ORIGIN come from the recipe (make's value
and $(origin PRIVATE_REPO)); run by hand, ../forthos-vocabularies beside
the tree, origin "file" (the Makefile default).
  private: PRIVATE_REPO/forth/dict exists, and every path the caller
           names is there (under PRIVATE_REPO, or under this tree).
  public:  PRIVATE_REPO/forth/dict absent, origin "file" (the default).
  FAIL (exit 1, before any QEMU): absent but set explicitly, or present
           without the caller's paths. Never a fallback to public mode.

Each caller pins its own totals per mode; a check that did not run reads
as not passed (N-k/T, exit 1), never a smaller N/N that looks whole.
The last line names the mode:
  Passed: N/T (private mode: PRIVATE_REPO <path>)
  Passed: N/T (public mode: K private checks not run, PRIVATE_REPO absent)
A wholly private test in public mode prints, and exits 0:
  SKIPPED (public mode: PRIVATE_REPO absent): <target>, T checks not run

As a command, for recipes (before any QEMU):
  python3 tests/run_mode.py <target> [--private p ...] [--tree p ...]
exits 0 to run; prints the SKIPPED line and exits 10 (the recipe then
exits 0); prints the FAIL line and exits 1.
"""
import os
import sys

SKIP_EXIT = 10


class Mode:
    def __init__(self, private, repo):
        self.private = private
        self.repo = repo

    def line(self, passed, total, public_note=None):
        """The last line. public_note replaces the count of checks not
        run, for a caller whose checks are the same in both modes."""
        if self.private:
            mode = f'private mode: PRIVATE_REPO {self.repo}'
        else:
            mode = f'public mode: {public_note}, PRIVATE_REPO absent'
        return f'Passed: {passed}/{total} ({mode})'

    def not_run(self, k):
        return f'{k} private check{"" if k == 1 else "s"} not run'

    def skip(self, target, total):
        print(f'SKIPPED (public mode: PRIVATE_REPO absent): {target}, {total} checks not run',
              flush=True)
        sys.exit(0)


def resolve(root, private=(), tree=()):
    """The mode, or FAIL and exit 1. private: paths under PRIVATE_REPO;
    tree: paths under root (this tree)."""
    repo = os.environ.get('PRIVATE_REPO') or os.path.join(root, '..', 'forthos-vocabularies')
    origin = os.environ.get('PRIVATE_REPO_ORIGIN', 'file')
    if os.path.isdir(os.path.join(repo, 'forth', 'dict')):
        miss = [os.path.join(repo, p) for p in private if not os.path.exists(os.path.join(repo, p))]
        miss += [os.path.join(root, p) for p in tree if not os.path.exists(os.path.join(root, p))]
        if miss:
            print(f'FAIL: PRIVATE_REPO {repo} found, these not: {miss} '
                  '(no fallback to public mode)', flush=True)
            sys.exit(1)
        return Mode(True, repo)
    if origin != 'file':
        print(f'FAIL: PRIVATE_REPO set ({origin}) to {repo}, not found '
              '(no fallback to public mode)', flush=True)
        sys.exit(1)
    return Mode(False, repo)


def main(argv):
    target, private, tree, into = argv[0], [], [], None
    for a in argv[1:]:
        if a in ('--private', '--tree'):
            into = private if a == '--private' else tree
        else:
            into.append(a)
    m = resolve(os.getcwd(), private, tree)
    if not m.private:
        print(f'SKIPPED (public mode: PRIVATE_REPO absent): {target}, the test is private',
              flush=True)
        sys.exit(SKIP_EXIT)
    sys.exit(0)


if __name__ == '__main__':
    main(sys.argv[1:])
