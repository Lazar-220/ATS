# Phase UI-B: Ranking, Assessment and the final accessibility pass (frontend plan UI-5 + UI-6 + UI-7)

Run this in one session, without the orchestrator and subagents. This prompt is the approved plan: do not present
a separate plan; stop and ask only on an escalation (schema, public API, new dependency, real LLM calls, a changed
test assertion, a "Done when" item that cannot be met).

**Read:** `docs/review/frontend-plan.md` §2.4, §2.5, §4 "Rules that apply to every phase", "UI-5", "UI-6" and
"UI-7", Appendix A; `docs/PROGRESS.md` Decisions Q7, Q8, Q10, Q12 and the UI-2 and UI-A rows;
`web/design/HANDOFF.md` §2 (`SectionHeaderRow`, `Tooltip`, `Popover`, `ProvisionalBanner`, `ScoreCell`,
`ToCheckCell`, `VerdictBadge`, `QuoteState`, `FlagNote`, `RequirementCard`, `CvViewer`), §3 (Ranking row,
Assessment), §4, §5, §8; `web/design/Ranking.dc.html`, `Assessment.dc.html`; `css/components.css`,
`css/screens.css`. In `web/src`: `RankingScreen.tsx`, `RankingTable.tsx`, `ranking.ts`, `AssessmentScreen.tsx`,
`highlight.ts`, `copy.test.ts`, `ui/` (reuse `Tooltip`, `Link`, `EmptyState`, `Table.css` from UI-2 and UI-A).
**Branch:** `phase/ui-b-ranking-assessment` from `main` with UI-A merged.

`web/design/` (flattened) and `docs/review/` are in `.git/info/exclude`: open them with Read; if a path is wrong,
list `web/design/` once and use what is there.

## Goal

Ranking and Assessment match their boards, with the last new capability (To check with its breakdown), and the
whole UI passes one accessibility walkthrough. No API, schema or behaviour
changes beyond those listed here.

## Commits (one per item)

1. `feat(web): restyle the ranked list`: page head with the "Requirements" link; one `ui/Banner.tsx`
   (`role="note"`, "Provisional" + today's sentence, only when there are rows, Q12) replacing the per-row
   "rubric unconfirmed" tag; Score, Failed mandatory and Assessment cells with icons; "(name not found)" in italic;
   sr-only "Actions"; section header rows at the server-order boundaries from pure `sectionOf(row)` /
   `sectionStarts(rows)` in `ranking.ts` (never re-sort; `#` stays `row.index + 1`), the help tooltip on
   "Misses a mandatory requirement"; the "To check" column from a pure `toCheck(row)` (badge when total > 0,
   tooltip on Assessed rows only, wording per Q10, "–" on failed rows per Q7); "How the score works" with
   `ui/Popover.tsx` (`aria-expanded`, `role="dialog"`, closes on Esc, outside click and ×, returns focus), the
   board's text in one constant with a comment pointing to `src/ats/pipeline/score.py`. Tests for the new pure
   functions in a new file or appended to `ranking.test.ts` (existing assertions unchanged).
2. `feat(web): restyle the assessment screen`: `h1` name; the summary without " · rubric unconfirmed" and the
   Provisional banner instead; tenure text unchanged (Q12); the failed notice; `FlagNote` with a catalog in
   `flags.ts` (titles from the board, CV-flag bodies = today's five sentences, verdict-flag bodies = `detail`,
   unknown code = title) and `flags.test.ts`; `RequirementCard` (title `<button aria-pressed>` with `::after`,
   flags above it, refinements indented); card numbers only if you verify the verdict order matches the editor's
   row order (Q8), otherwise none, and say which in the report; `VerdictBadge`, `QuoteState`; `CvViewer` as
   `<pre class="cv" tabindex="0" data-testid="cv-text">` built from the existing `segment`/`toRanges`, with the card
   list and the pane each in a 720 px scroll area; a pure `centredScrollTop(...)` with a test, `pane.scrollTo` with
   `behavior: "auto"` under reduced motion.
3. `fix(web): …`: one commit per defect found in the accessibility walkthrough below (none if none).
4. `docs: record phase UI-B and the redesign`: `PROGRESS.md` phase row with evidence; Decisions rows: Q2 and Q9
   closed as "no change" (`npm run build` stays a phase check, no Playwright/axe); the UI-A open questions
   (tab-switch refetch drops unsaved edits, a stale "Saved.") recorded under "Known risks / deferred".
   `SETUP.md` only if something changed.

## Traps

- `highlight.ts` and its tests do not change. Offsets are code points (HANDOFF §4); only verified evidence is
  highlighted, text inside a highlight uses `--color-text-primary`.
- No `scrollIntoView` anywhere: it also scrolls the page.
- Keep `data-testid="unverified"` and `data-testid="cv-text"` on the equivalent elements.
- Specimen classes (`.is-*`), `.proto*`, `.gtable`/`.grow`/`.gcell` are board-only; express their looks on real
  state. Tables are real `<table>` with TanStack Table v9. The board's inline styles and hex colours become classes
  on tokens.
- Section headers are `<tr class="row--section"><th colspan scope="colgroup">`; they never change the server order.
- Tooltips: hoverable, dismissible with Esc, persistent (WCAG 1.4.13), triggers focusable, never the only home of
  essential text.
- `copy.test.ts`: remove only what Appendix A allows ("Unverified quotes", the per-row tag, "Flag ",
  " · rubric unconfirmed"); add every new text (Appendix A "New texts" for Ranking and Assessment, the eight flag
  titles).
- CV text, names, filenames, rationales and flag details are untrusted: text nodes only, never in `title` or
  `document.title`.
- No new dependency, no real LLM call. Browser checks with `LLM_PROVIDER=fake` and synthetic CVs only.

## Accessibility walkthrough (commit 3, by you in code, then the owner in the browser)

Every screen: focus order top bar, breadcrumb, page actions, content (Assessment: cards in rubric order, then the
pane); focus always visible; every status, verdict and flag has an icon plus a word; reduced motion stops
transitions and spinners (words stay) and makes the pane jump; at 1024 px and 200 % zoom no content is lost and
tables scroll inside their wrapper.

## Done when

- [ ] `make check` exits 0 on each commit and `npm --prefix web run build` exits 0 at the end.
- [ ] New tests pass (`sectionStarts`, `toCheck`, `flags`, `centredScrollTop`); `route`, `status`, `ranking`, `highlight`, `health`, `draft` assertions unchanged.
- [ ] `git diff main -- web/openapi.json web/src/api-types.ts web/src/highlight.ts` is empty.
- [ ] `rg -n "#[0-9a-fA-F]{3,6}\b|style=\{\{|dangerouslySetInnerHTML|scrollIntoView" web/src --glob "*.tsx"` and `rg -n "is-error|is-disabled|is-hover|is-focus|is-pressed|is-busy|is-selected|grow--|gtable|gcell" web/src` find nothing (whole `web/src` now).
- [ ] A browser checklist for the owner in the report: a position with candidates in all three groups (a high score in the second group below a lower one in the first); To check tooltip by mouse and keyboard; the popover closes in all three ways and focus returns; 2 s polling updates in place; an Assessment with an emoji and Cyrillic before a quote (highlight lands on the quote); selecting a card scrolls only the pane; Not met shows no quote line; an Unverified verdict highlights nothing; a failed assessment shows its error; missing CV text shows "The CV text is not available."; plus the walkthrough above.

End with the CLAUDE.md phase report. Do not merge.
