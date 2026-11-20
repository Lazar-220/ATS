# CV-ranking service with a measurable LLM judge: case study (draft)

Status on 2026-11-17: a personal project in development. Phases 0 to 1.4a of version 1 are merged. It has not been used in production or on real CVs, and the judge has not been measured yet.

## Problem

HR uploads a job posting PDF and a set of CV PDFs. The service scores every CV against the posting's requirements and shows a ranked list, with a verdict (`met`, `partial`, `not_met`) and a verbatim quote from the CV for each requirement. CVs are in Serbian (Latin and Cyrillic) and English. The design goal is that every verdict can be checked without opening the PDF, and that every quality claim comes from a measurement.

## Architecture

- **Code computes, the LLM judges.** The LLM is called once per posting (requirement extraction) and per CV for parsing and judging. Tenure, date arithmetic, the score and the ranking are computed by code. The score is `100 × (0.7 × mandatory + 0.3 × nice-to-have)` with met = 1, partial = 0.5, not_met = 0.
- **Grounding.** A `met` or `partial` verdict must carry a verbatim quote, and code checks that the quote exists in the CV text.
- **Untrusted input.** The LLM receives only masked text (name, email, phone and address stay in a separate table). CV text goes into a fenced data block, and the judge has no tools.
- **One database, no extra infrastructure.** FastAPI, a worker process, Postgres with raw SQL through psycopg 3. The job queue is a Postgres table read with `FOR UPDATE SKIP LOCKED`. Every LLM output is a Pydantic schema, and all calls go through one client with rate limiting, retries and a response cache.
- **Three gated versions.** v1 is the judge without vectors, v2 adds retrieval over a CV database (pgvector), v3 adds a validation loop with questions to HR. A version starts only when the previous one's eval passes. v2 and v3 are designed, not built.

## Evaluation method

- **Golden set.** 6 synthetic positions and 80 synthetic CVs, 866 gold verdicts (606 dev, 260 test). Labels are known by construction: a profile with the planned verdict and quote is written first, then the CV from it. The set covers five language and script styles, single-column and two-column PDFs, and 20 hard cases (for example a skill named only in a list, or overlapping job periods).
- **Class skew.** 68.0% of the gold verdicts are `met`, so a judge that always answers `met` scores about 68%. Accuracy is reported next to that number, with macro-F1 and weighted kappa.
- **Independent audit.** A separate model instance that saw only the CV text, the requirement texts and the labelling conventions re-derived 392 verdicts on 36 CVs. It agreed with the gold labels on 388 (99.0%), and one gold label was changed. The author and the auditor are the same model family (Claude), so the audit shows that the labels are consistent with the conventions, not that they are right.
- **The gold labels have not been manually verified.** The planned manual check of a 20% sample is deferred, and the audit is not that check.

## Key decisions and their cost

| Decision | Cost |
| --- | --- |
| Synthetic golden set, built from profiles | Synthetic CVs are cleaner than real ones, and an LLM judging LLM-written text gives optimistic numbers. |
| Audit by a model in place of the manual check, for speed | Shared blind spots are not caught. Every result must say "gold labels not manually verified". |
| Default model `gemini-3.6-flash`, because the planned `gemini-3.8-flash` kept returning 503 | Numbers measured on 3.6 are not evidence about 3.8 or about the plan's cost estimate. The baselines must be re-measured on 3.8. |
| Name and address masking by code, without an LLM | Known limits. One address leak is known in a two-column CV, and the address leak rate is not measured. |
| Free Gemini tier (about 20 requests per day) | The real CV-parsing run is deferred. Only a dry-run estimate exists. |
| Extraction prompt not tuned after the first run | In three of six postings the model adds a base requirement that the posting states only inside a refinement. |

## What is measured so far

| Metric | Value | Conditions and caveats |
| --- | --- | --- |
| Requirement extraction F1 | 97.7% (precision 95.6%, recall 100.0%), target ≥ 85% | Six real calls on the six golden postings, `gemini-3.6-flash`. No prompt tuning has happened, but these are the same six postings any later tuning would use. |
| Masking leak rate | email 0 of 80, phone 0 of 80, name 0 of 80 | Code only, no model. The masker was written while looking at these CVs, so this is not a held-out number. |
| Gold label audit agreement | 388 of 392 (99.0%) | Same model family as the author of the labels. Not a manual check. |
| CV parsing | not measured | Dry run only: 18 calls, estimated about $0.115. No model was called. |
| Judge verdict accuracy | not measured | Target ≥ 80% on the test part, to be read against the 68.5% majority class there. |
