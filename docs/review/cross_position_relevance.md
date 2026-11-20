# Cross-position relevance labels: review before phase 2.3

Read-only review of `eval/golden/profiles/` (80 CVs × 6 positions), the CV texts and the six postings.
Nothing was changed; every label change below is a proposal. Suggested labels are my reading of the CV
text against the posting, not a judge run.

**Verdict: the PROGRESS.md concern is confirmed.** Recall@N counts relevance ≥ 2 (§5, prompt 2.3). Of the
73 pairs with relevance ≥ 2, 66 are a CV against its own position and only 7 are cross-position. A
prefilter that only recognises the job family reaches 0.90 recall, and with N = 20 every home pool
(10–17 CVs) fits in the top N. After the corrections in section 2, only 2 cross-position pairs ≥ 2 remain.

## 1. Matrix: CVs with relevance ≥ 1 (of which ≥ 2)

Rows are the CV's own position (pool size), columns the position it is scored against.

| CV pool | backend | bus. analyst | data analyst | fin. controller | proj. manager | sales manager |
| --- | --- | --- | --- | --- | --- | --- |
| be (10) | 10 (9) | 0 | 7 (0) | 0 | 0 | 0 |
| ba (11) | 1 (0) | 11 (10) | 8 (0) | 1 (0) | 10 (4) | 0 |
| da (11) | 5 (0) | 1 (0) | 11 (9) | 8 (0) | 0 | 0 |
| fc (17) | 0 | 0 | 7 (0) | 17 (15) | 0 | 0 |
| pm (14) | 1 (1) | 10 (2) | 0 | 0 | 14 (10) | 1 (0) |
| sm (17) | 0 | 0 | 0 | 0 | 1 (0) | 17 (13) |

Cross-position labels overall: 339 × 0, 54 × 1, 7 × 2, no 3. What the non-zero cells rest on:

- **ba → pm (10, four at 2):** the words Jira, backlog, sprint. The four 2s are exactly the four BA CVs with
  home relevance 3; none led a project, a team or a budget.
- **pm → ba (10, two at 2):** Jira, Confluence, backlog. Only pm_12 has real analyst work (an earlier BA job).
- **be → da (7) and da → be (5):** Python and SQL being named; da_10 on a "Database Developer" job.
- **da → fc (8):** Excel, sometimes an economics degree. **fc → da (7):** Power BI in four, Excel alone in three.
- **ba → da (8):** one bullet, "SQL for data checks".
- **Singles:** ba_03 → be (ex-Java developer), ba_07 → fc (ex-accountant), da_01 → ba, pm_04 → be (2),
  pm_11 → sm (shop assistant), sm_11 → pm (site engineer).
- **Sales manager is an island:** one CV in, one CV out. 62 of 63 outside CVs are 0 for it.

Pattern: the cross label follows the home fit level more than the CV text (strong BA → pm 2, strong FC → da 1),
so near-identical CVs get different labels (pairs 2, 5, 6, 7, 8 below).

## 2. Ten pairs where the label looks wrong

| # | CV | Position | Now | Suggest | Reason from the CV text |
| --- | --- | --- | --- | --- | --- |
| 1 | ba_01 | project_manager | 2 | 1 | Only PM evidence is "Jira backlog, sprints and release notes"; no project, team or budget. Weaker than pm_03 (home, 1). Same for ba_04, ba_05, ba_08. |
| 2 | pm_01 | business_analyst | 2 | 1 | No requirements work; an analyst is only a team member ("programeri, testeri, analitičar"). pm_05, pm_08, pm_13 have the same evidence and are 1. |
| 3 | pm_14 | business_analyst | 1 | 0 | "Координатор радова" on building maintenance; no Jira, no requirements, English B1. pm_06, with Jira and Confluence, is 0. |
| 4 | ba_07 | financial_controller | 1 | 2 | "Racunovodja … 03/2016 - 10/2023" (91 months) and "Smer Racunovodstvo i revizija": meets degree and tenure. Stronger than fc_12 and fc_15 (home, 1). |
| 5 | da_01 | business_analyst | 1 | 0 | No requirements, user stories, Jira or BPMN. da_04, da_08, da_11 are the same profile and are 0. |
| 6 | ba_03 | project_manager | 0 | 1 | "Backlog u Jira-i, svakodnevno", five years BA in fintech: same basis as ba_02, ba_09, ba_10, ba_11 (all 1). |
| 7 | be_06 | data_analyst | 0 | 1 | "SQL reports and views in PostgreSQL", "MySQL queries for reports": closer to analyst work than be_05 (1). |
| 8 | be_08 | data_analyst | 0 | 1 | Python plus "PostgreSQL, složeni upiti i migracije", English C1: the same evidence as be_05 (1). |
| 9 | da_07 | financial_controller | 1 | 0 | Maths teacher turned analyst; the only link is "Excel za čišćenje izvoza iz ERP-a". da_01, same evidence, is 0. Also applies to da_04 and da_11. |
| 10 | pm_04 | backend_developer | 2 | 1 | Borderline. Rests on "Razvoj servisa u Javi i Pythonu" (ended 12/2019); Git and Docker are list-only; no REST (weight 3), SQL or tests. |

Too easy rather than wrong: the label-0 pairs against sales_manager carry at most a stray sales word
(ba_09 "Координатор продаје", fc_16 "rad sa kupcima"), never B2B selling, targets or a CRM. Also,
fc_03, fc_08, fc_09 → da = 1 rest on Excel alone while fc_06 and fc_11 (same Excel evidence) are 0.

## 3. Missing pairs: spec for extra CVs

Two kinds are missing: cross-position CVs that really are relevance 2 (recall@N must keep them), and
look-alikes that share the posting's vocabulary but are 0 or 1 (NDCG@10 must push them down).
Priority A is 10 CVs and keeps the set at 90, the §5.1 ceiling; B adds 6.

| Cluster | Profile to write | Labels | Pri |
| --- | --- | --- | --- |
| PM / BA | BA who also ran delivery: Scrum Master, team of 6, tracked project budget | ba 3, pm 2 | A |
| PM / BA | Product owner: backlog, user stories, acceptance criteria; no BPMN, SQL, team or budget | ba 2, pm 1 | A |
| PM / BA | Scrum Master / agile coach, 3 years, no budget, no line management | pm 2, ba 1 | A |
| PM / BA | PMO administrator: Jira reports, budget sheets in Excel, never led a project | pm 1, ba 0 | B |
| BE / DA | Data engineer: Python, SQL, Airflow, Docker, Git; no REST, no dashboards | be 2, da 2 | A |
| BE / DA | BI developer: strong SQL, Power BI, light Python, no statistics | da 2, be 1 | A |
| BE / DA | QA automation engineer: pytest, Python, Docker, tests APIs but never built one | be 2, da 0 | A |
| BE / DA | Data scientist: Python, regression, notebooks; light SQL, no dashboards | da 2, be 1 | B |
| FC / DA | FP&A analyst: budget, forecast, Power BI, SQL, Excel; no MSFI, no SAP, 3 years | fc 2, da 2 | A |
| FC / DA | Auditor: MSFI, ACCA, Excel; no budgeting, no SAP | fc 2, da 0 | A |
| FC / DA | BI analyst inside a finance department: SQL and Power BI on SAP data, no accounting | da 2, fc 1 | B |
| FC / DA | Bank credit-risk analyst: Excel, regression, basic SQL, economics degree | da 2, fc 1 | B |
| SM / others | Sales operations analyst: Salesforce reports, SQL, Power BI, forecasts; never sold | da 2, sm 1 | A |
| SM / others | Procurement manager in packaging or FMCG: supplier contracts, negotiation, team of 4 | sm 1, fc 0 | A |
| SM / others | Presales consultant in IT: client workshops, offers, tenders, requirements | ba 2, sm 1, pm 1 | B |
| SM / others | Commercial controller: price lists, margins, sales budget, SAP SD | fc 2, sm 1 | B |

Constraints for the new CVs:

- Each still needs a home position with full claims; pick the position where its label is highest.
- At least 4 of the 10 in Serbian (one Cyrillic), so the hard pairs are not English-only.
- After `ats.eval build`, check that each cluster has at least one new CV in the test split; today the
  test split holds only 2 cross-position pairs ≥ 2 (ba_05 → pm, pm_01 → ba).
- Expected result with the A list: 12 new pairs at relevance ≥ 2 that come from adjacent-role CVs
  (three of those CVs are ≥ 2 for two positions at once), against 2 such pairs today after the
  section 2 corrections. Sales manager still gets no outside CV at 2; that is realistic, but its
  recall@N will stay easy and should be read that way.
