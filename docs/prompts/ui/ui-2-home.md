# Phase UI-2: Home (upload, progress, positions) and the not-a-CV row

**Read first:** §4.4 (the paragraph on CV text as untrusted data) and §6.3 (the "Frontend" row) of `docs/plan.md`;
`docs/review/frontend-plan.md` §2.2, §4 ("Rules that apply to every phase" and "UI-2"), §5 and Appendix A;
the `docs/PROGRESS.md` Decisions rows for UI-1 (Q2, Q3, Q9, Q12); `web/design/design/HANDOFF.md` §1, the §2 rows
for the Home components (upload form, file field, request status, document state, progress table, positions
table, empty state), §4 and §5; `web/design/design/css/tokens.css`, `css/components.css`, `css/screens.css`;
the whole of `web/design/design/Home.dc.html` except the add-mode markup and script; in `web/src`: `Upload.tsx`,
`PositionsList.tsx`, `status.ts`, `status.test.ts`, `copy.test.ts`, `App.tsx`, `RankingTable.tsx` (the
TanStack Table pattern), `styles/*` and every file in `ui/`.
**Depends on:** UI-1 merged into `main` (`46c81fe`), `main` at `1415df5` or later.
**Branch:** `phase/ui-2-home`

`web/design/` and `docs/review/` are in `.git/info/exclude`. Open their files with Read at the exact paths above;
Glob and Grep may skip them. If one of them is missing, stop and ask.

## Goal

Home (the upload form, the upload progress and the positions table) matches the board, except add mode, which is
UI-3. A document the backend flags as "not a CV" is shown as a neutral info row instead of a red one. Behaviour,
texts, polling and API calls stay as they are, except where this prompt says otherwise.

## Earlier decisions that apply

Already recorded in `docs/PROGRESS.md`; do not record them again.

- Q2: `npm --prefix web run build` is a phase check, not part of `make check` or CI.
- Q3: the phase is merged into `main` with `--no-ff`; the other screens keep their interim look.
- Q9: no browser tooling (Playwright, axe). The owner does the browser checklist.
- Q12: `role="alert"` stays on the sentence "The posting could not be read, so there is nothing to rank against.".
- Q5 (add mode) is UI-3. Build nothing of it here: no "Add CVs" button, no chip, no `addCvs`.

Kept from today (frontend plan §2.2, rows tagged **diff**): the form error stays until the next submit (it does
not clear when a file changes); the PDF check stays extension only (`isPdfName`, unchanged); the form stays a real
`<form onSubmit>`, so Enter submits; the File column keeps `doc.filename ?? doc.document_id` and the Posting column
keeps `position.filename ?? position.id`.

## Build (commit units)

1. **`feat(web): restyle the upload form`**
   Add a pure `uploadProblem(posting: File | null, cvs: File[])` to `status.ts` that returns `null` or
   `{ message, fields }`, where `fields` lists the inputs to mark invalid (`"posting"`, `"cvs"`). The messages and
   their order are exactly today's (`Upload.tsx:52-61`): no posting or no CV gives "Choose one posting PDF and at
   least one CV PDF." on both fields; otherwise the first file that fails `isPdfName` (posting first, then the CVs
   in order) gives `` `${name} is not a PDF file.` `` on the field that holds it. Take only `name` from each file, so
   the test can pass plain objects. `UploadForm` uses it instead of its inline checks.
   Restyle the form as on the board: labels with `htmlFor` and ids from `useId`, the design's file field
   (`::file-selector-button`), `aria-invalid` and the error border on the fields `uploadProblem` names, cleared on
   the next submit that passes. The submit button becomes `ui/Button` (primary, `busy` while uploading, text
   "Uploading…" / "Upload and rank" unchanged). Today's three `<p role="alert">` elements (the problem, the upload
   error, the status error) become one message area, `<p id="form-msg" aria-live="polite">` (HANDOFF §5), that
   shows the first of those three that is set, in that order; the API's error text is shown as it comes.
   Tests: append them to `status.test.ts`; the existing tests and their assertions stay as they are.

2. **`feat(web): restyle upload progress and show not-a-CV as info`**
   Add a pure `documentRowVariant(doc: { status: string; message: string | null })` →
   `"attention" | "info" | "default"` to `status.ts`: `attention` when `documentNeedsAttention(doc.status)`;
   otherwise `info` when `doc.message !== null` (the board's rule, `Home.dc.html:236-243`; the backend sets the
   not-a-CV message at `src/ats/services/rankings.py:274-278`); otherwise `default`. State keeps its label
   ("Read" for `parsed`); an unknown state is still shown raw (`documentLabel`), with the info icon as on the
   board. The message text is shown as the API wrote it, as text.
   The progress view: the status line "Status: {label}" with the board's icon and `aria-live="polite"` on that
   line only (today the whole section is live, `Upload.tsx:10`); the table becomes
   `<table aria-label="Uploaded files">` built with TanStack Table as in `RankingTable.tsx` (no sorting), with the
   row classes for `attention` and `info` from `screens.css` and the info icon in the message cell of an info row.
   "Open the ranked list" and the failed sentence stay, the latter with `role="alert"` (Q12). Add the `info` icon
   (and any other icon the board's Home uses in this unit) to `ui/Icon.tsx`, paths copied from the board.
   Add "Uploaded files" to the Home list in `copy.test.ts`. Tests for `documentRowVariant` cover: rejected and
   failed (attention, with and without a message), parsed with a message (info), parsed without a message
   (default), an unknown state with a message (info), uploaded without a message (default).

3. **`feat(web): restyle the positions table`**
   `PositionsList` as on the board: a TanStack Table `<table>`; the rubric cell with the board's icon
   (caution for `unconfirmed`, check for `confirmed`) beside the text `rubric_status` exactly as today; Version and
   Requirements right-aligned with `.num`; the Requirements cell keeps the `SETUP_LABEL` texts; the actions column
   header is `<span className="sr-only">Actions</span>` (today it is `""`); the row links "Requirements" and
   "Ranked list" keep their texts and targets, styled with the board's classes. Loading stays `ui/Loading`; the error
   stays `ErrorNotice` with "Try again"; the empty state becomes `ui/EmptyState.tsx` (+ `EmptyState.css`, icon plus
   text, text unchanged). Add "Actions" to the Home list in `copy.test.ts`. The query key `["positions"]` and the
   5 s polling stay.

4. **`docs: record phase UI-2`**
   `docs/PROGRESS.md`: the phase row, the measured evidence, and a Decisions row for any implementation choice that
   is not in this prompt. `docs/SETUP.md` only if something in it changed (no new dependency is expected).

## Out of scope

Add mode and anything else from UI-3 ("Add CVs", the chip, "Choose at least one CV PDF.", `POST /positions/{id}/cvs`).
Requirements, Ranking and Assessment (UI-4 to UI-6). Clearing the form error when a file changes; accepting a PDF by
MIME type; replacing the form with a button. `Tooltip`, `Popover`, `Banner` and any primitive Home does not use.
The light theme. Any change to `openapi.json`, `api-types.ts`, `hooks.ts`, `api.ts`, the Makefile, `compose.yaml`,
`docker/web.Dockerfile` or the CI workflow.

## Done when

- [ ] `make check` exits 0 on every commit of the branch (state how you checked each one), and `npm --prefix web run build` exits 0 at the end.
- [ ] `uploadProblem` and `documentRowVariant` tests pass, covering the cases in units 1 and 2.
- [ ] `git diff main -- web/src/status.test.ts` shows only added lines; `route.test.ts`, `ranking.test.ts`, `highlight.test.ts`, `health.test.ts` and `no-html-injection.test.ts` are unchanged and pass.
- [ ] `copy.test.ts` passes; `git diff main -- web/src/copy.test.ts` adds exactly "Uploaded files" and "Actions" and removes nothing.
- [ ] `rg -n "#[0-9a-fA-F]{3,6}\b|style=\{\{" web/src --glob "*.tsx"` has no hits in `Upload.tsx`, `PositionsList.tsx` or `ui/`.
- [ ] `rg -n "dangerouslySetInnerHTML|innerHTML" web/src` finds nothing outside the injection test, and nothing imports from `web/design/`.
- [ ] `npm --prefix web run check:types` passes, and `git diff main -- web/openapi.json web/src/api-types.ts web/src/api.ts web/src/hooks.ts` is empty.
- [ ] The owner's browser check (list it in the report as a checklist, with `make up`, `make api`, `make worker`, `make web`, synthetic files only, no file under `data/real/`): a normal upload reaches Done and "Open the ranked list" opens the ranking; a scan PDF shows Rejected as an attention row; a PDF that is not a CV shows an info row with State "Read" and the API's message as written; a posting that cannot be read shows the failed sentence; both validation messages, each with the right field marked invalid and the message in the one message area; an API refusal shown as it comes; the positions table with both rubric icons, right-aligned numbers, the links working, and the empty, loading and error states (error: stop the API); Enter submits the form; a visible focus ring on every control on Home.

## Traps

- Copy CSS from the design into the screen's CSS file or `web/src/styles`; never import from `web/design/`. Leave out
  the specimen classes (`.is-hover`, `.is-focus`, `.is-pressed`, `.is-busy`, `.is-error`, `.is-selected`),
  `.proto*`, `.gtable`/`.grow`/`.gcell` and `.placeholder-note`; apply the grid-table look to the real `<table>`.
- `@tanstack/react-table` is v9 (`useTable`, `tableFeatures`, `createColumnHelper`). Copy the pattern from
  `RankingTable.tsx`; do not write v8 code (`useReactTable`, `getCoreRowModel`) from memory.
- `node --test` strips types but does not compile JSX. Keep the tested logic in `status.ts`, not in components.
- A CV filename and the document message are untrusted text: render them as text nodes, never as markup or in
  `title`/`document.title` (HANDOFF §4).
- The info row must not use the error colour. The rule is `message !== null` and not attention; do not key it on
  the message text.
- Do not change `documentNeedsAttention`, `documentLabel`, `isPdfName` or their behaviour; `status.test.ts` pins them.
- No new dependency is expected. If you need one, stop and ask.
- If an existing test's assertion has to change, or a "Done when" item cannot be met, stop and say so. Do not start
  UI-3.
