# docs/evidence/ -- durable evidence policy

Text evidence (`.txt`, `.log`, `.md`) is tracked: run excerpts,
audit results, baselines that rollback procedures read from
(e.g. `g4-baseline-2026-08-22.txt`, consumed by RUNBOOK-G6 step
H.1). Cite evidence here, never `/tmp` -- `/tmp` citations
evaporate.

Binary captures (`.bin`) are LOCAL BY POLICY, not by accident.
They fall under the blanket `*.bin` build-artifact rule
(`.gitignore` line 5) and are deliberately left there: the
2026-07-15 arc directories hold tiny register-capture files
(~131 as of 2026-08-23), and publishing raw binaries in a
public repo buys nothing permanent history can't regret.

This note exists because a blanket ignore rule that silently
hides content produces false "searched and found nothing"
results (the ATAPI `docs/TASK_*.md` invisibility finding, docket
2026-07). If a future `git add docs/evidence/` stages fewer
files than `ls -R` shows, this is why -- and if a `.bin` ever
needs to be public, negate the rule explicitly in `.gitignore`
rather than working around it.
