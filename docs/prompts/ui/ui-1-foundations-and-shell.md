# Phase UI-1: Foundations and app shell

**Read first:** §4.4 (the paragraph on CV text as untrusted data) and §6.3 (the "Frontend" row) of `docs/plan.md`;
`docs/review/frontend-plan.md` §4 ("Rules that apply to every phase" and "UI-1"), §5, §6 and Appendix A;
`web/design/design/HANDOFF.md` §1, §2 (rows `TopBar`, `HealthLine`, `Breadcrumb`, `Button`, `ErrorNotice`,
`Loading`), §4 (first bullet) and §5; `web/design/design/css/tokens.css`, `css/components.css`,
`css/screens.css`; the header and breadcrumb markup of `web/design/design/Home.dc.html` and the whole of
`web/design/design/NotFound.dc.html`; every file in `web/src`.
**Depends on:** the approved frontend plan (`docs/review/frontend-plan.md`, approved 2026-11-23) on `main` at `0c3a5d2` or later.
**Branch:** `phase/ui-1-foundations-shell`

`web/design/` and `docs/review/` are in `.git/info/exclude`. Open their files with Read at the exact paths above;
Glob and Grep may skip them. If one of them is missing, stop and ask.

## Goal

Every screen runs on the design tokens and the Inter font inside the new app shell (top bar, health line,
breadcrumb), and the guard tests are in place before any component moves into a subfolder. The screens' own content
keeps its current look until UI-2 to UI-6.

## Owner decisions for the redesign (2026-11-23)

Record each one as a row in the `docs/PROGRESS.md` Decisions table in the docs commit (unit 7). Only those marked
**UI-1** are built in this phase.

- Q1 **UI-1**: add `@fontsource-variable/inter` (runtime dependency).
- Q2: `npm run build` stays a per-phase check and is not added to `make check` or CI; decide again at UI-7.
- Q3: every UI phase is merged into `main` (`--no-ff`, CLAUDE.md). The mixed look between phases is accepted.
- Q4: on Requirements, the answer mutation moves from `RequirementsForm` up to `PositionEditor` (option b), as a
  separate `fix(web)` commit in UI-4. UI-4 does not start until the owner has confirmed the current behaviour in a
  browser.
- Q5: add mode on Home: "Add CVs" moves focus to the CV file input; the chip falls back to the position id; entering
  or leaving add mode clears the form message and the previous progress; the form stays in add mode after Done until
  × is pressed; "Add CVs" is offered on every row.
- Q6: the editor uses the board's per-row accessible names ("Requirement {n}", "Type, requirement {n}", …).
- Q7: To check shows "–" on failed rows.
- Q8: Assessment cards get flat numbers in rubric order, but only after the UI-6 implementer has checked the code and
  the backend and confirmed that the verdict order on Assessment matches the editor's row order. If it does not, the
  cards get no numbers.
- Q9: no browser tooling (Playwright, axe) in UI-1 to UI-6; decide at UI-7.
- Q10: the To check tooltip is pluralised: "1 quote not verified", "2 quotes not verified".
- Q11 **UI-1**: Home gets a visually hidden `<h1>Positions</h1>`.
- Q12: today's behaviour stays in all five cases: the rubric line stays visible while extracting; the Provisional
  banner appears only when the ranking has rows; tenure still shows "0 months" / "? months"; the Parent option label
  is unchanged; `role="alert"` stays on NotFound and on the failed-request sentence, in the board's order.
- Q13 **UI-1**: add `web/design` to `.dockerignore`.

## Build (commit units)

1. **`test(web): scan nested source files for HTML injection`**
   `no-html-injection.test.ts` lists `src` without `recursive`, so files in subfolders would go unchecked. List the
   files recursively, still excluding `api-types.ts` and `*.test.ts`. Put the listing in a small helper, so unit 5
   can add an assertion that a nested file is scanned. The forbidden words and the assertions stay as they are.

2. **`test(web): pin the user-facing texts`**
   `copy.test.ts` checks that every string in Appendix A of the frontend plan (the lists "Shell", "Home",
   "Requirements", "Ranking", "Assessment", including the five CV-flag sentences) appears in the non-test sources of
   `web/src`. Use the same file listing as unit 1. Two rules, chosen by whether the string contains whitespace:
   - **No whitespace** (one word, with only its own characters: "State", "Score", "Upload", "Position",
     "Version", "Parent", "Rubric", "Posting", "Candidate", "Requirement", "Processing", "ATS", "CV", "No",
     "Read", "Done", "None", "Met", and also "Loading…", "Saved.", "(empty)", "#", "–"): it must appear **whole**,
     as a quoted string literal (`"State"`, `'State'` or `` `State` ``) or as a JSX text node (only whitespace
     between it and the surrounding `>` and `<`).
   - **Contains whitespace** (sentences and fragments, including those with a leading or trailing space:
     "Save your changes first, then confirm", "API: ", ", weight ", " is not a PDF file."): matched as a
     substring.

   The reason: single words also occur inside identifiers (`useState`, `DocumentState`, `UploadForm`), so a
   substring match would still pass after the text had been removed from the screen. No texts are removed or added
   in this phase.

3. **`chore(web): add Inter font and design tokens`**
   `npm install @fontsource-variable/inter` inside `web/` and commit the lock file. Check the import path in the
   package's README; HANDOFF §1 names `@fontsource-variable/inter/wght.css`. Add `web/src/styles/tokens.css` (copied
   from the design, **without** the four `@font-face` blocks with `/_blob/` URLs) and `web/src/styles/base.css`
   (`.ats` base type with `font-feature-settings: var(--font-features)`, box sizing, the focus ring, `.sr-only`,
   `.num`, `.icon`, the spinner with its reduced-motion rule, `body`, `.app`, `.page`, `.page--wide`, `.h1`, `.h2`).
   `color-scheme: dark` is already set in `tokens.css`, in the `:root, [data-theme="dark"]` block
   (`web/design/design/css/tokens.css:68-69`). Keep it there when you copy the file, and do not repeat it in
   `base.css`. If your copy of `tokens.css` lacks it, set it on `:root` in `base.css` and say so in the report.
   Import the font and both files once in `main.tsx`. Root element `className="ats app"`. Add `design` to the
   ESLint `ignores`.

4. **`chore(docker): keep the design files out of the web image`**
   Add `web/design` to `.dockerignore` (Q13).

5. **`feat(web): add icon set and base controls`**
   `web/src/ui/Icon.tsx`: a fixed set of icons as JSX `<svg>` paths, copied from the boards, `aria-hidden="true"`.
   Add only the icons this phase uses. `web/src/ui/Button.tsx` + `Button.css` (variants `primary`, `secondary`,
   `ghost`, `icon`; sizes `md` and `sm`; `busy` with spinner and `aria-busy`; `ariaDisabled`, whose click and
   keyboard handlers return early). `web/src/ui/Notice.tsx` + `Notice.css`: `ErrorNotice` moves here with the same
   export name and props, restyled as the board's `.notice` with "Try again" as a small secondary button. It keeps
   today's element attributes and structure (`role="alert"` on the container, the message first, then the
   `type="button"` retry button only when `onRetry` is given; `web/src/Notice.tsx:2-13`). Update the imports and
   delete `web/src/Notice.tsx` in the same commit (no dead code). `web/src/ui/Loading.tsx`: spinner plus text, `role="status"`, replacing the existing
   `<p>Loading…</p>` elements (text unchanged). Extend the unit 1 test to assert that `ui/Icon.tsx` is among the
   scanned files.

6. **`feat(web): add top bar, health line and breadcrumb`**
   `web/src/health.ts`: a pure `healthState(...)` → `checking | ok | degraded | unreachable`, taking the query's
   pending, error and data. `degraded` means `status` is not `ok` or `database` is not `reachable`, which covers the
   503 body. Add `health.test.ts`. `ui/TopBar.tsx` ("ATS" as a link to `#/`, no sidebar), `ui/HealthLine.tsx`
   (icon by state, `role="status"`, the texts and `data-testid="health"` exactly as in `App.tsx:45-54`),
   `ui/Breadcrumb.tsx` (`<nav aria-label="Breadcrumb">` with an `<ol>`, an icon separator, `aria-current="page"` on
   a last item without `href`). Rework `App.tsx`: a `<header>` for the top bar, a `<main class="page">` for the
   breadcrumb and the screen (`page--wide` on Ranking and Assessment). Breadcrumbs: Home "Positions" (current page,
   no link); Requirements, Ranking and NotFound "Positions"; Assessment "Positions › Ranked list". Home gets the
   visually hidden `<h1>Positions</h1>` (Q11). NotFound in the board's order: breadcrumb first, then
   `<p role="alert">There is no such page.</p>` (Q12). The polling intervals and query keys stay unchanged.

7. **`docs: record phase UI-1 and the redesign decisions`**
   `docs/SETUP.md`: the new dependency in §5 and how the font is bundled (no CDN). `.dockerignore` lives in the
   repository, so it does not go under "Machine state". `docs/PROGRESS.md`: the phase row, the Q1 to Q13 decisions
   above, and the measured evidence.

## Out of scope

Restyling the content of Home, Requirements, Ranking and Assessment (UI-2 to UI-6). Add CVs, the not-a-CV row,
To check. `Link`, `EmptyState`, `Tooltip`, `Popover`, `Banner` and any other primitive the shell does not use yet.
The light theme. `document.title` per route (HANDOFF §4: no untrusted text in chrome). Any change to `openapi.json`,
`api-types.ts`, the Makefile, `compose.yaml`, `docker/web.Dockerfile` or the CI workflow.

## Done when

- [ ] `make check` exits 0 on every commit of the branch (state how you checked each one), and `npm --prefix web run build` exits 0 at the end.
- [ ] `web/dist` contains the Inter woff2 files, and `rg -n "https?://" web/dist --glob "*.css"` finds no font URL.
- [ ] `no-html-injection.test.ts` scans nested files: its assertion that `ui/Icon.tsx` is scanned passes.
- [ ] `copy.test.ts` passes, and its list is the full Appendix A set (count stated in the report). Strings without whitespace are matched whole, as a quoted literal or a JSX text node; only strings with whitespace are matched as substrings. The report shows the test failing once on a scratch copy where the header "State" has been removed and the word survives only inside identifiers such as `useState` or `DocumentState`, run with the file left uncommitted and reverted.
- [ ] `web/src/Notice.tsx` no longer exists, and `rg -n "from \"\./Notice\"" web/src` finds nothing.
- [ ] `route.test.ts`, `status.test.ts`, `ranking.test.ts` and `highlight.test.ts` pass with no change to their assertions (`git diff main -- web/src/*.test.ts` touches only `no-html-injection.test.ts` and new files).
- [ ] `health.test.ts` covers checking, ok, degraded (the 503 body) and unreachable.
- [ ] `rg -n "#[0-9a-fA-F]{3,6}\b|style=\{\{" web/src/ui web/src/App.tsx web/src/styles` has no hits in `.tsx` files.
- [ ] `npm --prefix web run check:types` passes, and `git diff main -- web/openapi.json web/src/api-types.ts` is empty.
- [ ] The owner's browser check (list it in the report as a checklist, with `make up`, `make api`, `make worker`, `make web`): the dark theme and Inter on every route; "ATS" goes to `#/`; the health line in its states with the API up, with the database stopped and with the API stopped (the spinner shows while checking); breadcrumbs per route as in unit 6; NotFound order and text; a visible focus ring on every control in the shell; with reduced motion on, the spinner stops and the text stays; Home, Requirements, Ranking and Assessment still work end to end with synthetic files, and no text on them became unreadable.

## Traps

- Copy CSS from the design into `web/src/styles`; never import from `web/design/`. Leave out the specimen classes
  (`.is-hover`, `.is-focus`, `.is-pressed`, `.is-busy`, `.is-error`, `.is-selected`), `.proto*` and the grid-table
  classes (HANDOFF §1, §8).
- `node --test` strips types but does not compile JSX. Keep the logic you test in `.ts` files (`health.ts`), not in
  components.
- A recursive listing returns paths with `\` on Windows and `/` in CI. Match file names by basename and extension,
  not by a path prefix.
- Appendix A contains curly quotes (“ ”), an en dash (–), an em dash (—) and an ellipsis (…). Copy them exactly; a
  straight quote or three dots will not match.
- Do not use `dangerouslySetInnerHTML` for the icons. Write the paths as JSX.
- The dark tokens apply to the old screens too. Accept their interim look (Q3), but do not let any text become
  unreadable; if one does, fix only that colour, in the screen's existing inline style, and say so in the report.
- The font is the only new dependency. If you need another one, stop and ask.
- If an existing test's assertion has to change, or a "Done when" item cannot be met, stop and say so. Do not start
  UI-2.
