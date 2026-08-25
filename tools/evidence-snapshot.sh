#!/bin/sh
# evidence-snapshot.sh NAME FILE... -- anchor an evidence source as a git object.
#
# Builds a commit from HEAD's tree plus the named files (tracked-dirty or
# untracked), refs it at refs/evidence/NAME, and prints the push line.
# refs/evidence/* is NOT in the default refspec: an unpushed snapshot is
# one reclone away from the b8380213 unrecoverability this exists to end.
#
# OPEN-CORE ASSERTION (load-bearing, not advisory): the snapshot TREE is
# checked with `git check-ignore --no-index` after write-tree and the ref
# is not created if any path in it is ignore-positive.  Gitignored paths
# here are paid-side; these refs go to the PUBLIC remote, so this refusal
# is the boundary.  The argument check below it is the same test earlier
# and friendlier -- but the tree check is the one that counts, because
# read-tree seeds from HEAD and would carry a once-committed, later-
# ignored file past an arguments-only check.  --no-index because plain
# check-ignore skips tracked paths, which is exactly that case.
#
# This REFUSES rather than filters, deliberately: silently dropping an
# ignored path would anchor a snapshot that builds differently from what
# was tested -- trading a leak for an unreproducible anchor.
#
# Paid inputs ride as a fingerprint (printed below, ready to paste into
# the evidence log), never as objects.
#
# PUSH REACH: the snapshot parents to HEAD, so pushing it publishes every
# object reachable from HEAD -- including unpushed master commits.  The
# script prints how many the push would carry; read that line.
set -eu
cd "$(git rev-parse --show-toplevel)"
NAME=$1; shift
[ $# -ge 1 ] || { echo "usage: $0 NAME FILE..." >&2; exit 2; }

# Fast, friendly input check (not the load-bearing one).
if LEAK=$(printf '%s\n' "$@" | git check-ignore --no-index --stdin); then
    echo "REFUSED: gitignored (paid-side) paths given as inputs:" >&2
    echo "$LEAK" >&2
    exit 1
fi

export GIT_INDEX_FILE=$(mktemp)
trap 'rm -f "$GIT_INDEX_FILE"' EXIT
git read-tree HEAD
git add -- "$@"
TREE=$(git write-tree)

# Load-bearing check: assert on what would ship, not on what was asked.
# Scope: the snapshot's DELTA against HEAD, not the whole tree.  HEAD
# carries six tracked-and-later-ignored docs/TASK_*.md (2026-07 blanket
# ignore, landed after they were committed) which are already public in
# every clone -- a whole-tree check refuses every snapshot forever over
# paths this push cannot newly expose.  What the boundary guards is what
# the snapshot INTRODUCES beyond HEAD; that is the delta.
if LEAK=$(git diff --name-only HEAD "$TREE" | git check-ignore --no-index --stdin); then
    echo "REFUSED: snapshot introduces ignore-positive paths beyond HEAD (ref not created):" >&2
    echo "$LEAK" >&2
    exit 1
fi

SNAP=$(git commit-tree "$TREE" -p HEAD -m "evidence snapshot: $NAME")
git update-ref "refs/evidence/$NAME" "$SNAP"
echo "refs/evidence/$NAME -> $SNAP"

# Fingerprint of the paid-side BUILD inputs, ready to paste into the log.
# The set is EMBED_VOCABS from the Makefile intersected with check-ignore
# -- what builds, not what's lying around.  A glob over forth/dict/ would
# sweep in paid-but-unembedded vocabs (atapi-ahci, meta-compiler, ...) and
# two checkouts building byte-identical images would fingerprint
# differently.  Sorted order, and the line names its members so it is
# self-describing.
# make expands its own variable (continuations and all): no external
# parser to drift.  A vanished TARGET exits make non-zero and errexit
# stops us at this assignment; the [ -n ] below catches the target
# existing but expanding to NOTHING.  Different failure modes, different
# mechanisms -- neither guard is dead code.
EMBED_SET=$(make -s print-embed-vocabs | tr ' ' '\n' | grep -v '^$')
# Empty is refuse-worthy, not free-tier: "there are no paid embeds" and
# "I could not find the list" must not collapse into the reassuring one.
# The free-tier message below is reachable only when the list parsed AND
# the check-ignore intersection is genuinely empty.
[ -n "$EMBED_SET" ] || { echo "REFUSED: EMBED_VOCABS came back empty from make" >&2; exit 1; }
IGNORED_VOCABS=$(printf '%s\n' "$EMBED_SET" | git check-ignore --no-index --stdin | sort) || IGNORED_VOCABS=""
if [ -n "$IGNORED_VOCABS" ]; then
    FP=$(echo "$IGNORED_VOCABS" | xargs sha256sum | sha256sum | cut -d' ' -f1)
    echo "untracked-inputs fingerprint (sha256 of sha256sum over, sorted):"
    echo "$IGNORED_VOCABS" | sed 's/^/  /'
    echo "  = $FP"
else
    echo "no ignore-positive vocabs on disk: HEAD-tree provenance is complete (free tier)"
fi

AHEAD=$(git rev-list --count origin/master..HEAD 2>/dev/null || echo '?')
echo "push reach: HEAD is $AHEAD commit(s) ahead of origin/master; pushing this ref publishes them all"
echo "now push it: git push origin 'refs/evidence/*:refs/evidence/*'"
