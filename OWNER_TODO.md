# Owner to-do

Only what you must do, most important first. All commands are for Git Bash in the repository root.
Nothing here is pushed or merged yet. Branch: `phase/1.8-v1-gate`.

## (a) Label review, about 20 minutes

The gate passed with gold labels that nobody has checked by hand. Check them now.

```bash
make label-review
```

Expected: a first line `25 test-split verdicts to review (gold labels are not manually verified)`,
then blocks like

```
ba_06  requirement 5: At least 2 years of daily work with Jira
  gold: partial   gold quote: 'Project Assistant | Brzi Servis d.o.o. | 09/2025 - present'
  judge: not_met
  listed because: frozen list (gate proposal); wrong: judged not_met
```

It is read-only: no model call, nothing written. It lists the 8 pairs of the gate proposal's frozen
list, the `uncertain.json` pairs in the test split, and every verdict the gate run got wrong or
flagged. For each block, open the CV (`eval/golden/cvs/<cv_id>.pdf` or the `.txt` next to it) and
the posting, and ask: is the gold verdict right for what the CV text says? Look at durations
(months counted from dates), "basic knowledge" wording, and skills that sit only in a list.

If a gold label is wrong:

1. Edit the verdict in `eval/golden/profiles/<cv_id>.json`.
2. `uv run python -m ats.eval build` (rewrites `labels/*.jsonl` and `split.json`; the split does
   not change). Expected: `6 positions, 80 CVs (56 dev, 24 test), 866 verdicts`.
3. Record the change in `docs/PROGRESS.md` (Decisions): CV, requirement, old and new label, why.
4. Recompute the gate from the cache, with no new LLM call:
   `LLM_MODEL=gemini-3.5-flash-lite LLM_RPM=14 LANGFUSE_ENABLED=false make eval STAGES=judge SPLIT=test DRY_RUN=1`
   must print `LLM calls: 48 (48 already in the response cache, 0 would go to the model)`; then
   the same command with `YES=1` writes a new result file (a repeat run, all cache hits). The judge
   answers do not depend on the gold labels, so only the scores move. Note that gold labels that
   change after seeing the judge's answers are not blind: say so in the record.

## (b) Private GitHub remote and the first push

First check that nothing private is tracked or unignored. Both were run on 2026-11-21 and gave:

```bash
git ls-files data/ eval/reference .env
```

Expected output: nothing (it printed nothing).

```bash
git check-ignore -v .env data/real eval/reference
```

Expected (and seen):

```
.gitignore:17:.env	.env
.gitignore:23:data/	data/real
.gitignore:31:eval/reference/	eval/reference
```

Run both again right before you push. Then, choosing your own repository name:

```bash
gh repo create <name> --private --source . --remote origin
git push -u origin main
git push -u origin phase/1.8-v1-gate
```

(`main` does not yet contain phase 1.8; the CI run for the branch is the one that matters until you
merge.) In the Actions tab, six jobs should be green:

| Job | What it should show |
| --- | --- |
| ruff | `All checks passed!` |
| pyright | `0 errors, 0 warnings, 0 informations` |
| unit-tests | about 435 passed, 88 deselected |
| integration-tests | the `pgvector/pgvector:pg17` service starts; the integration tests pass, including `test_worker_signal.py` (the SIGTERM test, skipped on Windows, runs on Linux) |
| web | typecheck, lint and `node --test` pass |
| smoke-eval | prints `no model was called`, verdict accuracy about 49%, quote validity 100% |

If one fails, read its log first; do not change the thresholds in `eval/smoke_cache/manifest.json`
to make it pass.

## (c) Langfuse: compose diff and the deferred live check

1. Diff `compose.langfuse.yaml` against the official Langfuse self-host Docker Compose file
   (langfuse.com, self-hosting, Docker Compose). It was written without the official file. Look
   for settings it lacks.
2. The live check (MANUAL_CHECKS.md section 1.6, steps 2, 3, 5 and 6) stopped on the 1 GB
   free-memory rule: with Langfuse up, free host memory was 249,636 KB and the containers used
   about 1.95 GiB. Close other applications (browser, IDE, Docker Desktop's other containers)
   first, then:

```bash
make down
powershell -Command "(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory"
make langfuse-up
powershell -Command "(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory"
docker stats --no-stream
```

The number is KB. The rule: if it drops below 1,048,576 (1 GB) after `make langfuse-up`, stop,
run `make langfuse-down` and try again after closing more. If it stays above, follow steps 2, 3, 5
and 6 of MANUAL_CHECKS.md section 1.6 (the live trace costs about 3 real calls on the free tier;
use `LLM_MODEL=gemini-3.5-flash-lite LLM_RPM=14`). Always finish with `make langfuse-down`, then
`make up`.

## (d) Skipped or deferred

**Model B dev run** (gemini-3.1-flash-lite was cut by provider errors after 4 calls; 4 of 150 used
for the run, not measured):

```bash
LLM_MODEL=gemini-3.1-flash-lite LLM_RPM=14 LANGFUSE_ENABLED=false make eval STAGES=judge SPLIT=dev DRY_RUN=1
LLM_MODEL=gemini-3.1-flash-lite LLM_RPM=14 LANGFUSE_ENABLED=false make eval STAGES=judge SPLIT=dev YES=1
```

Expected from the dry run: about `LLM calls: 112 (4 already in the response cache, 108 would go to
the model)`. If B wins on dev against the 3.5 run, gating on B would be a second test-split
exposure; the 3.5-flash-lite gate result stands as the baseline.

**The 1.5 browser walkthrough**: `MANUAL_CHECKS.md`, section "Phase 1.5" (nine steps; no browser
was available to the agents, so none was checked, and the text-not-HTML check is the one that
matters most). Proposal: add Playwright as a dev dependency in `web/` so it can be automated. This
needs your decision; it was not added.

**Real smoke cache re-record** (the committed cache is demo data):

```bash
make smoke-cache REAL=1 DRY_RUN=1
make smoke-cache REAL=1 YES=1
```

about 40 calls; then set the `thresholds` in `eval/smoke_cache/manifest.json` a few points under
`measured`, run `make smoke`, commit the directory.

**Merge decision** (yours alone):

```bash
git checkout main && git merge --no-ff phase/1.8-v1-gate
```

The `v1.0.0` tag and the README description of v1 are a follow-up, only if you confirm.
