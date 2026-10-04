# FINDING — test-flush fails 8/17 on master, and two recipes run outside `make test` (2026-10-04)

Recorded against master (`17c912f`). Not fixed here. Owner to sequence.

## Observed

`test-flush` fails before and after its kill-by-PID conversion, with the
same nine failures, check for check:

```
FAIL: block 900 (slot 0) -- expected 170, got 58
FAIL: block 901 (slot 1) -- expected 187, got 32
FAIL: block 902 (slot 2) -- expected 204, got 32
FAIL: block 903 (slot 3) -- expected 221, got 32
FAIL: block 900 (single) -- expected 170, got 58
FAIL: block 901 (single) -- expected 187, got 32
FAIL: block 902 (single) -- expected 204, got 32
FAIL: block 903 (single) -- expected 221, got 32
FAIL: disk read -- expected 99, got 58
Passed: 8/17
```

- Before conversion: `da10a01` (the old pattern-kill recipe), 8/17.
- After conversion: the batch-2b gate run, both the normal run and the H3
  rerun, 8/17, same nine lines.

The values read back, 58 (`:`) and 32 (space), look like Forth source text
where the test expects the bytes it wrote. One possible cause, **not
verified**: the catalog has grown into blocks 900–903, which the test uses as
scratch. Check the catalog layout and the test's block choice before
deciding.

## Why nobody saw it

`test-flush` is not a prerequisite of `make test`, so no full run reports it.
Neither is `test-squote-laydown-backstop0`. That one passes (23/23 at
`da10a01` and after conversion), but it is equally invisible if it ever
breaks.

| Recipe | In `make test`? | Status on master |
|---|---|---|
| test-flush | no | **fails 8/17** |
| test-squote-laydown-backstop0 | no | passes 23/23 |

## Not fixed

For the owner: decide whether each recipe belongs in `make test`. If
test-flush stays out, record why next to the recipe.
