# Gate 1.8 (v1): proposed metrics and pass/fail thresholds

Status: **proposal only**, written 2026-11-17 before any judge measurement exists. Nothing here is
decided until the owner approves it. Every number is marked **plan** (quoted from `docs/plan.md`)
or **mine** (my proposal).

## What the plan says

- §7: "You move to the next version only when the previous one's eval passes. The thresholds are
  initial targets; calibrate them after the first measurement."
- §7, v1 gate box: "verdict accuracy measured / all quotes exist in the CV".
- §7, row 1.4: "verdict accuracy on the test part is measured and recorded as a baseline, with a
  target of ≥ 80%; every displayed quote exists in the CV".
- §5.2: "accuracy and macro-F1 over three classes, confusion matrix, weighted kappa because the
  classes are ordinal"; rank: "NDCG@10, precision@5 with relevance ≥ 2, Kendall tau against the gold rank".
- §5.3: "Each variant is run three times"; "the conclusion is drawn from the bootstrap interval,
  not from the difference of means."

The plan gives two numeric conditions for v1: accuracy ≥ 80% and 100% of displayed quotes existing.
It has no "1.8" row and no threshold for macro-F1, kappa, per-class recall or rank. Those are mine.

## Data the gate is measured on

Test split: 260 verdicts from 24 CVs: met 178 (68.5%), partial 30 (11.5%), not_met 52 (20.0%).
A judge that always answers `met` scores 68.5% accuracy, macro-F1 0.27 and kappa 0. Over all 866
verdicts the distribution is 589 / 77 / 200 (majority 68.0%). **The gold labels are not manually
verified.**

## Metrics and thresholds

All on the test split, each computed per run and averaged over three runs (plan §5.3).

| # | Metric | Threshold | Source | Why |
| --- | --- | --- | --- | --- |
| 1 | Accuracy | ≥ 80% | plan | The plan's target. |
| 2 | Accuracy, lower bound of the 95% interval | > 68.5% | mine | Proves the judge beats always-`met`. |
| 3 | Macro-F1, three classes | ≥ 0.70 | mine | 80% accuracy with a near-ignored `partial` class lands just under 0.70. |
| 4 | Linear-weighted Cohen's kappa | ≥ 0.60 | mine | Linear weights match the score weights 1 / 0.5 / 0 (plan §2.4). |
| 5 | Recall, `not_met` | ≥ 0.80 | mine | A missed `not_met` raises a score and can hide a failed mandatory requirement. |
| 6 | Recall, `partial` | ≥ 0.50 | mine | A floor only: 30 examples cannot support a tighter bar. |
| 7 | Displayed quotes that exist in the CV | 100% | plan | The plan's second gate condition. |

Reported with the gate, not gating (all mine): unweighted Cohen's kappa; the confusion matrix;
the count of gold `not_met` judged `met` and the reverse; the share of `met`/`partial` verdicts
whose quote failed the code check before any handling; accuracy by language/script, by layout and
by hard-case tag; tokens, cost and p95 per CV.

Coherence check on thresholds 1 and 4: at exactly 80% accuracy with predicted class shares equal
to the gold ones, unweighted kappa is about 0.58. Weighted kappa is higher when errors are mostly
adjacent (`met`/`partial`), lower when they are `met`/`not_met`. So 0.60 is about the same bar as
80%, and fails a judge that reaches 80% through two-step errors.

## Ranking metric (reported, not gating; mine)

The plan's NDCG@10 and precision@5 belong to endpoint 2 (v2) and need more than the roughly four
test CVs per position. For v1 I propose comparing the score computed from predicted verdicts with
the score computed from gold verdicts, by the same formula (plan §2.4):

- Kendall tau-b per position, plus pairwise concordance pooled over all within-position pairs;
- mean absolute score error in points, over the 24 CVs;
- agreement on the "failed mandatory requirement" flag, which decides the first sort key.

About 36 within-position pairs are too few for a threshold. Suggested reading: pooled concordance
under 0.80 or a mean absolute error over 10 points is a warning to investigate, not a fail.

## Confidence intervals

Verdicts from one CV are not independent, so the interval resamples CVs, not verdicts (mine;
the plan names a bootstrap but not the unit):

1. Draw 24 CVs with replacement from the 24 test CVs; take every verdict of each drawn CV.
2. Use the same draw for all three runs, compute each metric per run, average over runs.
3. Repeat 10,000 times with a fixed, recorded seed. Report the 2.5th and 97.5th percentiles.
4. A resample with no gold `partial` or `not_met` is skipped and counted.

Expected width, my estimate and not a measurement: at 80% accuracy the interval is about ±5 points
if verdicts were independent, and about ±6 to ±8 points with clustering (design effect 1.5 to 2.5).
`not_met` recall is about ±11 points or wider; `partial` recall about ±18 or wider. Two consequences:

- The gate cannot show that true accuracy is ≥ 80%. It shows a point estimate ≥ 80% and an interval
  clear of the majority baseline. Requiring the lower bound ≥ 80% would need about 87% measured.
- 24 clusters is few; percentile intervals run slightly narrow. Treat a bound within one point of
  a threshold as touching it.

## Sensitivity check: uncertain verdicts

Recompute metrics 1 to 6 on the test split without the verdicts listed in `docs/PROGRESS.md`,
Decisions, "The writers flagged verdicts..." including the three kept after the audit (mine;
PROGRESS.md already asks for this in the 1.4b baseline for accuracy and macro-F1).

- The exclusion list is frozen as (cv_id, requirement) pairs in a file before the run. Entries
  that name only a CV (`fc_10`, `fc_16`, `pm_06`, `pm_07`, `da_05`, `ba_07`, `ba_09` and others)
  must first be resolved to requirements; where that is not possible the whole CV is excluded.
- Report how many test verdicts were removed. Several listed CVs are in the dev split, so the
  number may be small.

## Pass/fail rule (mine)

- **PASS:** conditions 1 to 7 all hold on the full test split, and 1 and 3 to 6 also hold without
  the uncertain verdicts.
- **FAIL:** any of 1 to 7 fails on both the full and the reduced set. Per plan §7: "you stay in the
  same version and fix the pipeline; new features wait."
- **INCONCLUSIVE:** the full and the reduced set disagree on any condition. The disputed labels are
  checked by hand, then the gate is recomputed from the cached responses with no new LLM call.
- A pass before the manual 20% check (carried over to "before 1.8 (owner)") is recorded as
  "pass, gold labels not manually verified".

## Conditions on the run (mine)

- Thresholds are fixed when this proposal is approved. The plan allows calibrating "after the first
  measurement"; any change is recorded in PROGRESS.md with its reason, before the gate run.
- Prompts are tuned on the dev split only (plan §5.1). The 1.4b baseline already looks at the test
  split once; the gate report states how many times the test split was evaluated before it.
- The report names the model. PROGRESS.md carries over a comparison of `gemini-3.6-flash` and
  `gemini-3.8-flash` to this gate; the thresholds apply to whichever model is chosen for v1.

## Open questions for the owner

1. Is the manual 20% check a precondition of the gate, or is a labelled "not verified" pass enough?
2. Should the `partial` floor (0.50) gate at all, given 30 examples?
3. Three runs of 24 CVs is about 72 judge calls plus parsing, above the free daily quota: paid
   tier, or one run with the run-to-run variance left unmeasured?
4. Should ranking stay report-only until the test split has more CVs per position?
