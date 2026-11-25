# Phase UI-2: Home (upload, progress, positions) and the not-a-CV row

**Read first:** §4.4 (the paragraph on CV text as untrusted data) and §6.3 (the "Frontend" row) of `docs/plan.md`;
`docs/review/frontend-plan.md` §2.2, §4 ("Rules that apply to every phase" and "UI-2"), §5 and Appendix A;
the `docs/PROGRESS.md` Decisions rows for UI-1 (Q2, Q3, Q9, Q12); `web/design/design/HANDOFF.md` §1, the §2 rows
`Button`, `Link`, `FileField`, `RequestStatus`, `DocumentState`, `DataTable` row, `ErrorNotice` and
`Loading`, `EmptyState`, the §3 tables "Positions" and "Upload request", §4 (first bullet), §5 and §8;
`web/design/design/css/tokens.css`, `css/components.css`, `css/screens.css`; the icons named below in
`web/design/design/Icons.dc.html`; the whole of `web/design/design/Home.dc.html` except the add-mode markup and
script; in `web/src`: `Upload.tsx`, `PositionsList.tsx`, `status.ts`, `status.test.ts`, `copy.test.ts`, `App.tsx`,
`RankingTable.tsx` (the TanStack Table pattern), `styles/*` and every file in `ui/`.
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
- Q5 (add mode) is UI-3. Build nothing of it here: no "Add CVs" button, no chip, no `addCvs`, no `plus` or
  `close` icon.

Kept from today (frontend plan §2.2, rows tagged **diff**): the form error stays until the next submit (it does
not clear when a file changes, unlike the board); the PDF check stays extension only (`isPdfName`, unchanged; the
board also accepts the MIME type); the form stays a real `<form onSubmit>`, so Enter submits (the board has no
form); the File column keeps `doc.filename ?? doc.document_id` and the Posting column keeps
`position.filename ?? position.id`.

## Build (commit units)

1. **`feat(web): restyle the upload form`**
   Add a pure `uploadProblem(posting: { name: string } | null, cvs: { name: string }[])` to `status.ts` that
   returns `null` or `{ message, fields }`, where `fields` lists the inputs to mark invalid (`"posting"`,
   `"cvs"`). The messages and their order are exactly today's (`Upload.tsx:52-61`): no posting or no CV gives
   "Choose one posting PDF and at least one CV PDF." with both fields; otherwise the first file that fails
   `isPdfName` (posting first, then the CVs in order) gives `` `${name} is not a PDF file.` `` with no field
   (`fields: []`), as on the board, which marks the fields only for the first message. `UploadForm` uses it
   instead of its inline checks.
   Restyle the form as on the board: the upload block is `<section className="panel" aria-labelledby=…>` with its
   `<h2>Upload</h2>` and the `.upload-form` grid inside the existing `<form onSubmit>`. Add `ui/FileField.tsx`
   (+ `FileField.css`) with the HANDOFF §2 props (`label`, `multiple`, `disabled`, `invalid`, `onChange`): a
   `.field` with a `.label` whose `htmlFor` matches an id from `useId`, the `.file` wrapper, and the native file input (`type="file"`, `accept="application/pdf,.pdf"`) with `aria-describedby="form-msg"` and `aria-invalid` when
   `invalid`. The fields named by the last failed submit are invalid until the next submit. The submit button
   becomes `ui/Button` (`type="submit"`, primary, `icon="upload"`, `busy` and `disabled` while uploading, text
   "Uploading…" / "Upload and rank" unchanged). Today's three `<p role="alert">` elements (the problem, the upload
   error, the status error) become one message area, `<div id="form-msg" aria-live="polite">` (HANDOFF §5), that is
   always rendered and shows the first of those three that is set, in that order, as the board's `.field-error`
   (`alert-circle` icon plus the text). The API's error text is shown as it comes. Add the `upload` icon.
   Tests: append them to `status.test.ts`, covering no posting, no CV, neither, a non-PDF posting, a non-PDF CV
   after a valid posting, and all valid. The existing tests and their assertions stay as they are.

2. **`feat(web): restyle upload progress and show not-a-CV as info`**
   Add a pure `documentRowVariant(doc: { status: string; message: string | null })` →
   `"attention" | "info" | "default"` to `status.ts`: `attention` when `documentNeedsAttention(doc.status)`;
   otherwise `info` when `doc.message !== null` (the board's rule, `msgInfo: !!d.msg && !att` in `Home.dc.html`;
   the backend sets the not-a-CV message at `src/ats/services/rankings.py:274-278`); otherwise `default`.
   The progress view is the board's `.upload-progress` block:
   - `RequestStatus`: the board's `.req-status req-status--{waiting|processing|done|failed}` (queued, running, done,
     failed) with `role="status"` and `aria-live="polite"` on this line only (today the whole section is live,
     `Upload.tsx:10`), and `data-testid="request-status"` kept from today. "Status: " in `.req-status__label`, the
     word from `requestLabel` in `.req-status__value`. Icons: `clock` (queued), `spinner` (running),
     `check-circle` (done), `x-circle` (failed). HANDOFF's prop names `'waiting' | 'processing'` are the labels,
     not new API values: the component takes the API status.
   - `DocumentState`: the board's `.state` with the text from `documentLabel` (unchanged). Icons: `clock` for
     Waiting, `file` for Text extracted, `check` with `state--ok` for Read, `alert-circle` with `state--attention`
     for Rejected and Failed, `info` for an unknown state, which is still shown raw.
   - The table: `<table className="table" aria-label="Uploaded files">` inside `.table-wrap`, built with TanStack
     Table as in `RankingTable.tsx` (no sorting), headers File, Kind, State, Message unchanged. Row classes are the
     real-table ones from `components.css`: `row--attention` and `row--info` (not the prototype's `grow--*`;
     `row--failed` is for Ranking, UI-5). The message cell is the board's `.msg`: `alert-circle` on an attention
     row; `info` icon and `msg--info` on an info row; the message as the API wrote it, as text. Port the prototype
     rule `.grow--attention .msg { color: var(--color-text-primary); }` (`screens.css:66`) as `.row--attention .msg`.
   - "Open the ranked list" uses a new `ui/Link.tsx` (HANDOFF §2 `Link`: `href`, `strong`, `trailingIcon`; the
     `.link` class, always underlined) with `strong` and `trailingIcon="arrow-right"`.
   - The failed sentence keeps `role="alert"` (Q12) and becomes the board's `.msg` with `alert-circle`; the board's
     inline `color: #E6EDF3; font-size: 14px` becomes a class on `var(--color-text-primary)` and the text-size
     token.
   Add the icons `clock`, `file`, `check`, `info` and `arrow-right` to `ui/Icon.tsx`, paths copied from
   `Icons.dc.html` / `Home.dc.html`. Add "Uploaded files" to the Home list in `copy.test.ts`. Tests for
   `documentRowVariant`: rejected and failed (attention, with and without a message), parsed with a message
   (info), parsed without a message (default), an unknown state with a message (info), uploaded without a
   message (default).

3. **`feat(web): restyle the positions table`**
   `PositionsList` as on the board: `<section className="section" aria-labelledby=…>` that owns
   `<h2>Positions</h2>` (move it out of `App.tsx`; the visually hidden `<h1>Positions</h1>` stays in `App.tsx`).
   The table is `<table className="table">` inside `.table-wrap`, built with TanStack Table (no sorting). The
   Posting cell wraps long names (the board's inline `overflow-wrap: anywhere` becomes a class). The Rubric cell is
   a `.state` with the text `rubric_status` exactly as today, and `alert-triangle` in `--color-caution` for
   `unconfirmed` (the board's inline `#C4A1FF` becomes a class) or `check` with `state--ok` for `confirmed`
   (HANDOFF §3). Version and Requirements carry `.col-num` on `th` and `td`; the Requirements cell keeps the
   `SETUP_LABEL` texts. The actions header is `<span className="sr-only">Actions</span>` (today it is `""`); the
   row links "Requirements" and "Ranked list" keep their texts and targets, use `ui/Link` and sit in
   `.row-actions`. Loading stays `ui/Loading`; the error stays `ErrorNotice` with "Try again"; the empty state
   becomes `ui/EmptyState.tsx` (+ `EmptyState.css`): `.empty` with the `inbox` icon (`icon--20`) and the text,
   unchanged; the board's inline flex becomes CSS. Add the `inbox` icon. Add "Actions" to the Home list in
   `copy.test.ts`. The query key `["positions"]` and the 5 s polling stay.

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
- [ ] `rg -n "#[0-9a-fA-F]{3,6}\b|style=\{\{" web/src --glob "*.tsx"` has no hits in `Upload.tsx`, `PositionsList.tsx`, `App.tsx` or `ui/`.
- [ ] `rg -n "is-error|is-disabled|is-hover|is-focus|is-pressed|is-busy|is-selected|grow--|gtable|gcell" web/src` finds nothing.
- [ ] `rg -n "dangerouslySetInnerHTML|innerHTML" web/src` finds nothing outside the injection test, and nothing imports from `web/design/`.
- [ ] `rg -n "data-testid=\"request-status\"" web/src` still finds the status line.
- [ ] `npm --prefix web run check:types` passes, and `git diff main -- web/openapi.json web/src/api-types.ts web/src/api.ts web/src/hooks.ts` is empty.
- [ ] The owner's browser check (list it in the report as a checklist, with `make up`, `make api`, `make worker`, `make web`, synthetic files only, no file under `data/real/`): a normal upload reaches Done and "Open the ranked list" opens the ranking; a scan PDF shows Rejected as an attention row; a PDF that is not a CV shows an info row with State "Read" and the API's message as written, not in red; a posting that cannot be read shows the failed sentence; "Choose one posting PDF and at least one CV PDF." marks both fields, a non-PDF file shows its message with no field marked, both in the one message area; an API refusal shown as it comes; the upload button busy with the spinner and "Uploading…"; the positions table with both rubric icons, right-aligned numbers, the links working, and the empty, loading and error states (error: stop the API); Enter submits the form; a visible focus ring on every control on Home, the file fields included; with reduced motion on, the spinners stop and the words stay.

## Traps

- The `.file` error and disabled looks exist only as specimen classes (`.file.is-error`, `.file.is-disabled`,
  `components.css:101-107`). Do not copy those selectors; express the same rules on real state, for example
  `.file:has(input[aria-invalid="true"])` and `.file:has(input:disabled)`.
- The board's inline styles (`#E6EDF3`, `#C4A1FF`, `margin-top: 12px` on the form message, the flex on `.empty`,
  `overflow-wrap` on the Posting cell) become classes on tokens. No `style={{` and no hex colour in `.tsx`.
- Copy CSS from the design into the component's CSS file or `web/src/styles`; never import from `web/design/`. Leave
  out the specimen classes (`.is-hover`, `.is-focus`, `.is-pressed`, `.is-busy`, `.is-error`, `.is-selected`),
  `.proto*`, `.gtable`/`.grow`/`.gcell`, `.file__fake-btn` and `.placeholder-note`; the uploaded-files table is a
  real `<table>` with `.table` and `.row--*`.
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
