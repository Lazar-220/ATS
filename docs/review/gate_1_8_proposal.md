# Gate 1.8 (v1): metrics and pass/fail thresholds

Status: **accepted by the owner on 2026-11-17**, before any judge measurement exists, with four
answers (marked **owner** below). Every number is marked **plan** (quoted from `docs/plan.md`),
**mine** (proposed by Claude, accepted) or **owner**.

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
It has no "1.8" row and no threshold for macro-F1, kappa, per-class recall or rank.

## Data the gate is measured on

Test split: 260 verdicts from 24 CVs: met 178 (68.5%), partial 30 (11.5%), not_met 52 (20.0%).
A judge that always answers `met` scores 68.5% accuracy, macro-F1 0.27 and kappa 0. Over all 866
verdicts the distribution is 589 / 77 / 200 (majority 68.0%). **The gold labels are not manually
verified**, except the eight pairs listed under "Frozen exclusion list", which the owner checks by
hand before the run.

## How the gate is decided

One run on the test split, on a single model (**owner**; the plan's three runs are dropped, so
run-to-run variance is unmeasured and the report says so). The gate **passes** when all six
conditions hold on the full test split (260 verdicts) and conditions 1 and 3 to 5 also hold on the
reduced set (252 verdicts, without the frozen exclusion list):

1. accuracy ≥ 80%;
2. the lower bound of the 95% CV-level bootstrap interval of accuracy is above 68.5%;
3. macro-F1 ≥ 0.70;
4. linear-weighted Cohen's kappa ≥ 0.60;
5. recall of `not_met` ≥ 0.80;
6. 100% of displayed quotes exist in the CV.

It **fails** when a condition fails on both sets, or when condition 2 or 6 fails; then, per plan
§7, "you stay in the same version and fix the pipeline; new features wait." It is **inconclusive**
when the full and the reduced set disagree on condition 1, 3, 4 or 5; the owner then decides from
the manual check of the eight pairs, and the gate is recomputed from cached responses with no new
LLM call. A pass is recorded as "pass, gold labels not manually verified" (**owner**). Recall of
`partial` and the ranking metrics never decide the gate (**owner**).

## Gating metrics

| # | Metric | Threshold | Source | Why |
| --- | --- | --- | --- | --- |
| 1 | Accuracy | ≥ 80% | plan | The plan's target. |
| 2 | Accuracy, lower bound of the 95% interval | > 68.5% | mine | Proves the judge beats always-`met`. |
| 3 | Macro-F1, three classes | ≥ 0.70 | mine | 80% accuracy with a near-ignored `partial` class lands just under 0.70. |
| 4 | Linear-weighted Cohen's kappa | ≥ 0.60 | mine | Linear weights match the score weights 1 / 0.5 / 0 (plan §2.4). |
| 5 | Recall, `not_met` | ≥ 0.80 | mine | A missed `not_met` raises a score and can hide a failed mandatory requirement. |
| 6 | Displayed quotes that exist in the CV | 100% | plan | The plan's second gate condition. |

Coherence of 1 and 4: at exactly 80% accuracy with predicted class shares equal to the gold ones,
unweighted kappa is about 0.58. Weighted kappa is higher when errors are mostly adjacent
(`met`/`partial`) and lower when they are `met`/`not_met`, so 0.60 is about the same bar as 80%
and fails a judge that reaches 80% through two-step errors.

## Reported, not gating

- **Recall of `partial`, with its interval (owner).** Below 0.50 it triggers a manual check of the
  30 gold `partial` test verdicts and the judge's answers to them, not a fail. With 30 examples the
  interval is about ±18 points or wider.
- **Ranking (owner: report-only).** The score from predicted verdicts against the score from gold
  verdicts, same formula (plan §2.4): Kendall tau-b per position; pairwise concordance pooled over
  all within-position pairs; mean absolute score error in points over the 24 CVs; agreement on the
  "failed mandatory requirement" flag. The plan's NDCG@10 and precision@5 belong to endpoint 2
  (v2) and need more than about four test CVs per position. Pooled concordance under 0.80 or a
  mean absolute error over 10 points is a warning to investigate (mine).
- Unweighted Cohen's kappa; the confusion matrix; the count of gold `not_met` judged `met` and the
  reverse; the share of `met`/`partial` verdicts whose quote failed the code check before any
  handling; accuracy by language/script, layout and hard-case tag; tokens, cost and p95 per CV.

## Confidence intervals (mine)

Verdicts from one CV are not independent, so the interval resamples CVs, not verdicts:

1. Draw 24 CVs with replacement from the 24 test CVs; take every verdict of each drawn CV.
2. Compute each metric on the resample. Repeat 10,000 times with a fixed, recorded seed.
3. Report the 2.5th and 97.5th percentiles. A resample with no gold `partial` or `not_met` is
   skipped and counted.

Expected width, an estimate and not a measurement: about ±6 to ±8 points on accuracy (design
effect 1.5 to 2.5), about ±11 or wider on `not_met` recall. So the gate shows a point estimate
≥ 80% and an interval clear of the majority baseline; it cannot show that true accuracy is ≥ 80%.
24 clusters is few and percentile intervals run slightly narrow: a bound within one point of a
threshold is treated as touching it. The interval covers sampling of CVs only, not run-to-run
variation of the model, which one run cannot measure.

## Frozen exclusion list

The flagged and contested verdicts of `docs/PROGRESS.md` (Decisions, "The writers flagged
verdicts..."; Measured numbers, the audit row) that fall in the test split. All other listed CVs
are in the dev split. The owner checks these eight by hand before the run; the list stays frozen
whatever that check finds, and a gold label it changes is changed in the profile, rebuilt and
recorded in PROGRESS.md before the run.

| CV | Requirement | Gold | Why it is listed |
| --- | --- | --- | --- |
| `ba_06` | 5 | partial | Contested in the audit; gold changed from `not_met` (Jira 14 months of 24, "basic"). |
| `be_07` | 1 | partial | Writer's flag. |
| `be_07` | 2 | not_met | Writer's flag. |
| `da_05` | 2 | partial | Duration 9 months from a threshold (SQL, about 27 months of 36). |
| `fc_10` | 3 | partial | "Basic knowledge" convention (IFRS). |
| `pm_07` | 4 | not_met | Duration rests on weeks (Scrum since 08/2026, 3 months of 24). |
| `sm_08` | 3 | met | Implicit evidence. |
| `sm_09` | 6 | partial | Writer's flag. |

Removed: 8 of 260 (met 1, partial 5, not_met 2). Reduced set: 252 verdicts (met 177, partial 25,
not_met 50). Three rows are my resolution of entries PROGRESS.md gives by CV only: `da_05` to
requirement 2, `fc_10` to requirement 3 and `pm_07` to requirement 4, read from the profile facts.
`pm_07` requirement 2 (38 months of 48) and requirement 3 (basic Scrum) are not listed, because
PROGRESS.md flags `pm_07` only for the verdict that rests on weeks.

## Conditions on the run

- Thresholds are fixed as of this acceptance. The plan allows calibrating "after the first
  measurement"; any change is recorded in PROGRESS.md with its reason, before the gate run.
- Prompts are tuned on the dev split only (plan §5.1). The 1.4b baseline already looks at the test
  split once; the gate report states how many times the test split was evaluated before it.
- One model answers every call and the report names it (**owner**). A run in which the OpenRouter
  fallback answered any call is "dev-smoke, non-baseline" and cannot decide the gate.
- No paid tier (**owner**). If the judge takes one call per CV, the run is about 24 judge calls
  plus up to 24 parsing calls, more than the free quota of about 20 requests a day, so it spans
  several days and resumes from the response cache.
