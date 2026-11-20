# Manual checks

What to try by hand in the running app, per phase. Each phase appends its own section.
Inputs are synthetic golden files under `eval/golden/` only. Never use anything from `data/real/`.

Setup for every check (Git Bash, each in its own terminal):

```bash
make up && make migrate      # Postgres in Docker
make api                     # :8000
make worker                  # watch its first log line
make web                     # :5173
```

Two ways to run the worker:

- **Demo, no key, no quota:** set `LLM_PROVIDER=fake` in `.env` before `make worker`. The first
  log line must say `llm_provider=FAKE`. Answers are keyword matches, so scores are not real.
  Use it to check the interface, not the judgement.
- **Real model:** `LLM_PROVIDER=gemini` (the default) and a valid `LLM_API_KEY`. One posting plus
  three CVs is about 8 calls (1 requirement extraction, 3 parses, 3 judgements, plus retries).
  Mind the free quota of about 20 requests a day.

For a clean start: `make down`, then `docker compose down -v` (this deletes the database), then
`make up && make migrate`.

## Phase 1.4b (judge and score), through the API

Inputs: `eval/golden/positions/backend_developer/posting.pdf` and
`eval/golden/cvs/be_01.pdf`, `be_02.pdf`, `be_03.pdf`.

1. Upload (replace the paths if you run it from elsewhere):
   `curl -F posting=@eval/golden/positions/backend_developer/posting.pdf -F cvs=@eval/golden/cvs/be_01.pdf -F cvs=@eval/golden/cvs/be_02.pdf -F cvs=@eval/golden/cvs/be_03.pdf http://localhost:8000/rankings`
   Expect HTTP 202 with a `request_id` and a `position_id`.
2. Poll `GET /rankings/<request_id>` until `status` is `done`.
3. `GET /positions/<position_id>/ranking`: expect one row per CV, a real name per row, scores
   from high to low, and candidates with a failed mandatory requirement after the others.
4. `GET /assessments/<assessment_id>` for one row: every `evidence` has `char_start` and
   `char_end`, and `cv_text[char_start:char_end]` is the quote (try it in Python). A verdict
   flagged `quote_not_found` has `evidence: null`.
5. Upload the same four files again: no new worker LLM calls (worker log shows none), same ids.

## Phase 1.5 (interface), in the browser at http://localhost:5173

Same inputs as above. Do this from a clean database, with no other tool than the browser.

1. **Upload.** Open the page. Pick the posting and the three CVs, press "Upload and rank".
   Expect: a status line that moves from waiting to processing to done, and one table row per
   file with its state. Choose a non-PDF file instead: expect a message, no request sent.
2. **Rejected document.** Upload any PDF with no text layer (a scan) as a CV: expect the row to
   show "Rejected" with the message in red, while the other CVs still finish. (No scan is
   committed; skip this if you have no synthetic one.)
3. **Requirements.** Open "Requirements" for the new position. Expect the list from the
   posting, status "unconfirmed". Edit one weight and save: the version goes up by one.
4. **Ranked list.** Press "Open the ranked list" (or "Ranked list" on the home page). Expect
   one row per CV with the real name, score, "Failed mandatory", the assessment state and the
   label "rubric unconfirmed" while the rubric is unconfirmed. Confirm the rubric on the
   requirements screen and reload the list: the label is gone.
5. **Check verdicts.** Press "Check verdicts" on a row. Left: every requirement with verdict,
   rationale and flags. Right: the CV text. Click a requirement that is met: the CV pane scrolls
   to its quote and the quote is highlighted in a stronger colour. Click another: the highlight
   moves. A verdict marked "Unverified" shows no highlight when selected.
6. **Text, not HTML.** Make a CV whose text contains markup (from the repo root):
   `uv run python -c "import sys; sys.path.insert(0,'tests'); from pdfs import make_pdf; open('xss_cv.pdf','wb').write(make_pdf('Test Person\ntest.person@example.com\nSenior Python developer\n<b>bold</b> &amp; <script>alert(1)</script>\n'*3))"`
   and upload it as a CV with the backend posting (delete `xss_cv.pdf` afterwards). The CV pane
   must show `<b>bold</b> &amp; <script>alert(1)</script>` as written, with no alert and no
   formatting. With the demo worker the requirement "Senior Python developer" style keywords
   may match; with the real model, any verdict is fine, only the rendering is checked.
7. **Navigation.** The browser's back button returns from the assessment to the list and from
   the list to the home page. A made-up address such as `#/nope` shows "There is no such page".
8. **Errors.** Stop `make api`, press "Try again" on a screen: an error message, then recovery
   after `make api` is back.
9. **Real name, masked model input.** The name shown is the real one. With the real model, the
   worker's log and the model never see it; with the demo worker the integration test
   `tests/integration/test_demo_walkthrough.py` asserts it (run `make test-int`).

## Real LLM smoke test (owner, costs real money)

1. `make smoke-real`: dry run, no call. Expect `LLM calls: 4`, about 5400 input and 6600 output tokens, about $0.03.
2. `make smoke-real YES=1`: 4 real calls (parse and judge for 2 dev CVs), a few cents; more only if a judge answer lacks a requirement.
3. Pass: the run ends with the metrics table and a result file under `eval/results/`, no error, flagged-verdict share low, cost and latency printed. A daily 429 stops the run with a message; try again after the quota resets. A repeat run is served from the cache.

## 1.6 Observability (owner)

Needs about 2 GB of free Docker memory: run `make down` (stops the app's containers) first. Docker Desktop must be running.

1. **Diff the compose file.** Compare `compose.langfuse.yaml` with the official Langfuse self-host compose (langfuse.com, self-hosting, Docker Compose). It was written without the official file, so look for settings it lacks (the images, tags and memory limits are the ones that were tested).
2. **Start and look.** `make langfuse-up`, then open http://localhost:3000 and sign in with `dev@ats.local` and `ats-local-password` (the placeholders in the compose file). Project `ats`.
3. **Live trace with the real model** (costs real money, a few cents; free-tier quota is about 20 calls a day). Put `LANGFUSE_ENABLED=true` and the three `LANGFUSE_*` lines from `.env.example` in `.env`, set `LLM_PROVIDER=gemini` and your key, restart `make worker`, upload one posting and one synthetic CV from the interface. In Langfuse, Tracing: open the trace named `assessment`. Expect the spans extraction, masking, parsing, judge, quote_check, score; under `judge` a generation `judge_v1` with the prompt (system and user), the answer, input and output tokens, cost and latency. The CV's own trace is `document_ingest` (generation `cv_parse_v1`). The id of the assessment's trace is in the database: `docker exec ats-postgres-1 psql -U ats -d ats -c "select trace->>'trace_id', cost_usd from assessment"`.
4. **Real cost per CV and LLM latency** (the numbers the fake provider cannot give): `make eval STAGES=judge SPLIT=dev LIMIT=5 DRY_RUN=1`, then with `YES=1` (20 real calls, about $0.10). The report prints cost per CV (parse and judge) and p95 latency per call. Record them in `docs/PROGRESS.md` (Measured numbers) with the model name and "real model".
5. **Experiments.** With `LANGFUSE_ENABLED=true` the same `make eval` run also uploads to Langfuse: Datasets, `ats-golden-dev`, and the run list shows one experiment per run. Run it twice (change `LIMIT` or the model) and compare the two per item.
6. **Personal data.** In any trace, search the text for the candidate's name, email, phone and address: none should appear (the integration test `tests/integration/test_tracing.py` checks this with a synthetic CV; this is the same check on real output).
7. **Stop.** `make langfuse-down` (the traces stay in Docker volumes; `docker compose -f compose.langfuse.yaml down -v` deletes them). Set `LANGFUSE_ENABLED=false` again if you do not want tracing.
