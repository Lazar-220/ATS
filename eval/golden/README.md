# Golden set

Synthetic positions and CVs whose labels are known by construction (plan §5.1). Nothing here is a
real person, employer or document. Layout and loaders: `src/ats/eval/golden.py`.

```
positions/<id>/position.json     gold requirements; posting.txt is the source, posting.pdf is rendered
profiles/<cv_id>.json            the planned verdict per requirement, the fact behind it, and the quote
cvs/<cv_id>.txt                  CV written from the profile; .pdf is rendered from it
labels/*.jsonl, split.json       derived: `uv run python -m ats.eval build`
```

Workflow: write the profile first, then the CV from it, then `uv run python -m ats.eval render`
(PDFs) and `uv run python -m ats.eval build` (validates every quote, writes labels and split).

## Labelling conventions

A verdict is about what the CV shows, not about what the candidate might know.

- `met`: the CV shows the requirement is satisfied, in words or by clear implication from described work.
- `partial`: part of it is shown. Cases that are `partial` by convention:
  - a duration requirement where the union of the candidate's periods reaches at least 50% of
    `min_months` but not all of it;
  - "basic knowledge" or similar self-limiting wording against a requirement of working knowledge;
  - a skill that is only named in a list, with no sign of use (plan §4.4: "a skill that exists
    only in a list, without confirmation in experience, gives at most `partial`");
  - a degree or course that is in progress.
- `not_met`: no evidence, a duration under 50% of `min_months`, an explicit number below the
  minimum (a team of 4 against "at least 5"), or a finished-but-unrelated qualification.
- Tenure counts the union of periods: overlapping jobs are not added up. Dates written
  "present" or "danas" are read as of the reference date **2026-11-17**. Profiles avoid cases
  where the verdict flips within a year of that date. The date is an `as_of` argument, never
  `today()`: the eval passes `GOLDEN_AS_OF` (`src/ats/eval/golden.py`), the tenure code of 1.4a
  takes the same parameter, and production passes the real date. Result files record it.
- Plan §3 defines no verdict semantics beyond the score weights (§2.4) and "a skill only in a
  list gives at most `partial`" (§4.4), which this agrees with. No conflict found.
- A `met` or `partial` verdict carries a quote: verbatim, inside one line of the CV source (for a
  two-column CV, one cell). `not_met` has none.

Relevance (CV against a position, for endpoint 2): 3 = would be shortlisted; 2 = plausible, with
gaps in the mandatory requirements; 1 = weak, related field; 0 = irrelevant. It is a design
judgement made with the profile, not a formula.

## Class distribution of the gold verdicts

Verdicts are skewed toward `met`, so accuracy must be read against the majority class.

| Part | Pairs | met | partial | not_met | Majority-class accuracy |
| --- | --- | --- | --- | --- | --- |
| overall | 866 | 589 (68.0%) | 77 (8.9%) | 200 (23.1%) | 68.0% |
| dev | 606 | 411 (67.8%) | 47 (7.8%) | 148 (24.4%) | 67.8% |
| test | 260 | 178 (68.5%) | 30 (11.5%) | 52 (20.0%) | 68.5% |

A judge that answers `met` for every pair already scores about 68%. `partial` is rare (77 pairs),
so macro-F1 and the weighted kappa matter more than accuracy, and the `partial` class has few
test examples (30). Every result file carries the distribution of the pairs it evaluated and the
majority-class accuracy in its header.

**The stub judge numbers are not a baseline.** The stub spoils gold labels on purpose to prove the
plumbing; its accuracy, kappa and grounding say nothing about any model. The first baseline is the
real judge of phase 1.4b.

## Formats

PDF only, single-column and two-column. DOCX golden CVs are out of scope: endpoint 1 rejects
anything that is not a PDF, so a DOCX CV could not enter the pipeline the eval measures. Revisit
only if DOCX becomes a product feature.

## Status of the labels

**The gold labels have not been manually verified.** The manual 20% check is deferred by the
owner (see `docs/PROGRESS.md`, Decisions and Carried over). Every result file says so, and so must
any baseline built on this set.

## Style

`style` says language and script of a CV: `sr_latin` (Serbian with diacritics), `sr_ascii`
(Serbian Latin typed without diacritics), `sr_cyrillic`, `en`, `mixed` (Serbian and English in one
CV). The template is `single` or `two_column`. A two-column source is the left column, a line
`=== RIGHT COLUMN ===`, then the right column; the renderer writes the two row by row, so PDF
extraction interleaves them, on purpose.

## Hard cases

A profile may carry `hard_case` with a tag (`implicit_evidence`, `overlapping_periods`,
`basic_knowledge`, `list_only`, `course_in_progress`, `career_change`) and a note saying what makes
it hard. They live inside the normal pool and are reported separately.
