# FINDING — five test scripts swallow SIGINT through a bare `except:` (2026-10-04)

Recorded against master (`17c912f`). Not fixed here; it belongs with the
`.py` step of TASK_HARNESS_KILL_BY_PID.

## Observed

Since batch 2, converted recipes run their test with
`timeout --foreground`, so a SIGINT to make's process group reaches the
Python script. For most scripts the recipe then exits within 0–1s. Three
did not in the gate runs:

| Recipe / fixture | SIGINT | SIGTERM |
|---|---|---|
| test-file-stream | ran to completion (152s, `Passed: 16/16`) | 0s |
| test-vocabs / test_editor | 39s | 0s |
| test-vocabs / test_x86_asm | 47s | 1s |

In every case the trap still killed the QEMU and removed the pidfile, so no
H2 gate failed. Only promptness suffered.

## Mechanism

These scripts wrap `s.recv()` in a bare `except:`, which also catches
`KeyboardInterrupt`. A SIGINT that arrives while the script is blocked in
`recv` is swallowed and the script carries on. One that arrives during
`time.sleep()`, outside the `try`, ends it. So the result depends on timing.
SIGTERM is not turned into a Python exception, so it always ends the script.

The five scripts with the pattern (bare-`except:` count):

| Script | Count |
|---|---|
| tests/smoke_test.py | 2 |
| tests/test_file_stream_helpers.py | 2 |
| tests/test_flush_stress.py | 2 |
| tests/test_editor.py | 2 |
| tests/test_x86_asm.py | 2 |

The scripts that exited promptly in the same runs (test_driver_vocabs,
test_disasm, test_abort, …) have none. smoke_test.py and
test_flush_stress.py happened to be interrupted during a sleep in the gate
runs, so they exited fast. They are listed because they have the same
pattern.

## Fix (not applied)

`except:` → `except Exception:` at each site, which lets KeyboardInterrupt
through. Ten sites in five files.
