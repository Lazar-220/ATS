# Phase UI-A: Add CVs on Home, and the Requirements screen (frontend plan UI-3 + UI-4)

Run this in one session, without the orchestrator and subagents. This prompt is the approved plan: do not present
a separate plan; stop and ask only on an escalation (schema, public API, new dependency, real LLM calls, a changed
test assertion, a "Done when" item that cannot be met).

**Read:** `docs/review/frontend-plan.md` §2.2 (add-mode rows), §2.3, §4 "Rules that apply to every phase", "UI-3"
and "UI-4", Appendix A; `docs/PROGRESS.md` Decisions Q4, Q5, Q6, Q12 and the UI-2 rows;
`web/design/HANDOFF.md` §2 (`AddModeChip`, `TextInput`/`NumberInput`/`Select`, `Tooltip`, `SaveResult`),
§5, §6 (Requirements behaviour), §8; `web/design/Home.dc.html` (add mode) and `Requirements.dc.html`;
`css/components.css`, `css/screens.css`. In `web/src`: `Upload.tsx`, `PositionsList.tsx`, `api.ts`, `hooks.ts`,
`PositionEditor.tsx`, `RequirementsTable.tsx`, `draft.ts`, `copy.test.ts`, and `ui/`.
**Branch:** `phase/ui-a-addcvs-requirements` from `main` with UI-2 merged.

`web/design/` (flattened: no inner `design/` folder) and `docs/review/` are in `.git/info/exclude`: open them with Read; if a path is wrong, list `web/design/` once and use what is there.

## Goal

Home can add CVs to an existing position (`POST /positions/{position_id}/cvs`, already in `openapi.json`), and the
Requirements screen matches its board. No API, schema or text changes beyond those listed here.

## Commits (one per item)

1. `feat(web): add CVs to an existing position from Home`: `addCvs` in `api.ts` (multipart `cvs`, like
   `uploadRanking`) and `useAddCvs` in `hooks.ts` invalidating `["positions"]`; the "Add CVs" ghost button
   (`plus` icon) on every row; `AddModeChip` in place of the posting field (`close` icon, ellipsis, full text in
   `title`); add mode is `UploadForm` state, not a route; `uploadProblem` gains add mode with
   "Choose at least one CV PDF." (CVs field invalid); the same progress view. Q5 (a)–(e) exactly.
2. `feat(web): restyle the requirements screen`: header (`h1` filename with the "Position" fallback, "Ranked list"
   link, rubric line with icon, still visible while extracting, Q12), a real `<table>` editor with styled
   inputs/selects, per-row accessible names (Q6), icon-only Remove (`aria-label="Remove requirement {n}"`, `title`,
   header "Remove"), "Add requirement" in the footer; the field named by the validation message gets
   `aria-invalid`, via an additive `validateDetail(rows)` in `draft.ts` (`validate` keeps its signature and returns
   `validateDetail(rows)?.message ?? null`) with a new `draft.test.ts`; the action bar with `ui/Tooltip.tsx` on
   Confirm (`aria-disabled`, handler returns early), `SaveResult` notices and one `aria-live="polite"` area.
3. `fix(web): keep the save result across the reload`: Q4 option (b), only after the owner has confirmed the
   current behaviour (see below). Move the answer mutation from `RequirementsForm` up to `PositionEditor`, so
   "Saved.", "Already saved." and the API error survive the version-keyed remount; on a 409 the draft resets to the
   server version with the message visible; "Saved." after Confirm stays.
4. `docs: record phase UI-A`: `PROGRESS.md` phase row with evidence, plus a Decisions row "UI-3..UI-7 regrouped into
   UI-A (Add CVs + Requirements) and UI-B (Ranking + Assessment + final accessibility pass), run in one session
   without subagents (owner, 2026-11-25)".

## Traps

- Specimen classes (`.is-error`, `.is-disabled`, `.is-hover`, `.is-focus`, `.is-pressed`, `.is-busy`,
  `.is-selected`), `.proto*`, `.gtable`/`.grow`/`.gcell` are board-only. Express their looks on real state
  (`[aria-invalid="true"]`, `:disabled`, `[aria-disabled="true"]`, `:has(...)`); tables are real `<table>` with
  TanStack Table v9 as in `RankingTable.tsx`.
- The board's inline styles and hex colours become classes on tokens. No `style={{` or hex in `.tsx`.
- The board's `.tooltip` must stay hoverable and dismissible with Esc (WCAG 1.4.13); do not copy a
  `pointer-events: none` that blocks that.
- The Parent select is a real list of `<option>` from the rows, label unchanged (Q12; not the board's 12 fixed
  slots, HANDOFF §8). Removing a requirement resets its children's Parent to "None" (HANDOFF §6).
- Keep every existing `data-testid` (`rubric-status` and others) and existing test assertions.
- `copy.test.ts`: add the new texts ("Add CVs", "Adding CVs to ", "Stop adding CVs", "Choose at least one CV PDF.",
  "Remove", "Remove requirement ", the Q6 names); remove only "Requirement text" and "Parent requirement".
- Filenames and API messages are untrusted text: text nodes only, never in `title`/`document.title` except the chip's
  `title` attribute, which HANDOFF §2 requires.
- No new dependency, no real LLM call.

## Done when

- [ ] `make check` exits 0 on each commit and `npm --prefix web run build` exits 0 at the end.
- [ ] `draft.test.ts` and the add-mode `uploadProblem` tests pass; `route`, `status`, `ranking`, `highlight`, `health` tests keep their assertions.
- [ ] `git diff main -- web/openapi.json web/src/api-types.ts` is empty.
- [ ] `rg -n "#[0-9a-fA-F]{3,6}\b|style=\{\{|dangerouslySetInnerHTML" web/src --glob "*.tsx"` and `rg -n "is-error|is-disabled|is-hover|is-focus|is-pressed|is-busy|is-selected|grow--|gtable|gcell" web/src` find nothing.
- [ ] A short browser checklist for the owner in the report (synthetic files only): add two CVs to a position, Done, they appear in its ranking; × leaves add mode; while uploading × and inputs are disabled; edit + Save shows the new version and "Saved."; Discard; each validation message marks its field; Confirm unreachable while dirty but its tooltip opens by keyboard and Enter/Space do nothing; Confirm works when clean; Remove resets children's Parent; a 409 from two tabs shows the message and the server version.

End with the CLAUDE.md phase report. Do not merge; do not start UI-B.
