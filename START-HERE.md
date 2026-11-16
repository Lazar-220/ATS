# ATS: paket za Claude Code

Ovaj fajl je za tebe. Sve ostalo u paketu čita Claude Code, pa je na engleskom.

## Šta je u paketu

```
CLAUDE.md                       trajni kontekst projekta: pravila, invarijante, commit i report format
.claude/settings.json           model (Sonnet), dozvole, hook-ovi
.claude/hooks/                  ruff posle svake izmene; ruff + unit testovi pre svakog commit-a
.claude/agents/                 dva sub-agenta: eval-failure-reviewer, phase-verifier
docs/SETUP.md                   preduslovi, zavisnosti po fazama, env promenljive, komande za pokretanje
docs/PROGRESS.md                status faza, izmereni brojevi, odluke
docs/prompts/00-bootstrap.md    faza 0
docs/prompts/v1/                1.1a – 1.8  (10 promptova)
docs/prompts/v2/                2.1 – 2.6   (6 promptova)
docs/prompts/v3/                3.1 – 3.8   (8 promptova)
```

## Postavljanje (jednom)

1. Instaliraj preduslove iz `docs/SETUP.md`, odeljak 1. `uv` mora da postoji pre prve sesije, jer ga hook-ovi koriste.
2. Napravi prazan folder projekta i raspakuj paket u njega, tako da `CLAUDE.md` bude u korenu.
3. Kopiraj svoj plan u `docs/plan.md`. Promptovi se pozivaju na njegove sekcije (§2.4, §3.2…).
4. Plan na dva mesta kaže da su pun DDL i upiti u tabu „Schemas and queries (SQL)". Tog taba nema u fajlu koji si mi poslao. Ako ga imaš, izvezi ga u `docs/schema.sql`. Ako ga nemaš, Claude Code će u fazi 1.1a izvesti šemu iz §2.5 i pokazati ti DDL pre migracije.
5. Otvori folder u VS Code-u i prihvati dijalog o poverenju u folder. Bez toga `allow` pravila iz projekta ne važe.
6. U Claude Code panelu proveri: `/model` pokazuje Sonnet 5.5, `/hooks` pokazuje dva hook-a, `/permissions` pokazuje pravila iz `.claude/settings.json`.

Na Windowsu radi u WSL2 (Ubuntu), sa repozitorijumom na Linux fajl-sistemu. Docker Desktop ionako radi preko WSL2, a `make` i hook-ovi tamo rade bez izmena.

## Ekstenzija ili terminal

Koristi VS Code ekstenziju kao glavni interfejs, a instaliraj i samostalni CLI.

- Motor je isti: isti model, isti `CLAUDE.md`, isti `settings.json`, hook-ovi i sub-agenti, ista istorija razgovora.
- Ekstenzija ti daje ono što ti za ovaj projekat najviše treba: diff svake izmene u editoru, pregled i izmenu plana pre odobrenja, vraćanje koda na raniju tačku (checkpoints), više razgovora u tabovima, `@` reference na fajl i opseg linija.
- CLI ima pun skup komandi, `!` prečicu za shell i tab completion. Ekstenzija ne stavlja `claude` u PATH, pa CLI instaliraj posebno i pokreći ga u integrisanom terminalu VS Code-a kad ti zatreba. `claude --resume` nastavlja razgovor započet u ekstenziji.

## Dozvole i rad van direktorijuma

Kako Claude Code to tretira:

- Alati za fajlove (čitanje, izmena) rade bez pitanja samo u radnom direktorijumu. Za sve van njega traži odobrenje.
- Shell komande nisu vezane za direktorijum, ali svaka traži odobrenje osim ako je na `allow` listi.
- `CLAUDE.md` utiče na to šta će Claude pokušati, ne na to šta mu je dozvoljeno. Dozvole daju samo `settings.json`, režim dozvola i tvoj klik na upit.

Šta sam podesio da se tvoja volja sprovede:

1. **`CLAUDE.md`, sekcija „Working outside the repository"**: izričito kaže da je rad van projekta odobren kad aplikaciji treba servis, uz pravila: najavi šta radi i zašto, radije Docker nego instalacija na host, svaku promenu van repozitorijuma upiše u `docs/SETUP.md` („Machine state") sa komandom za poništavanje.
2. **`allow`**: git (bez push-a), `uv`, `make`, `npm`, `docker compose` i čitanje Docker stanja, Hugging Face keš, dokumentacija biblioteka iz plana. To pokriva Postgres, Langfuse, n8n i modele bez ijednog upita.
3. **`ask`** (uvek pita, čak i kad bi `allow` pustio): `git push`, `sudo`, `rm -rf`, brisanje Docker volumena, `git reset --hard`.
4. **`deny`**: `.env` (API ključ ne ulazi u kontekst modela), `data/real/` (pravi CV-jevi), `~/.ssh`, `~/.aws`.

Sve što nije ni na jednoj listi i dalje dobija upit. Kad odgovoriš „Yes, and don't ask again", pravilo se upisuje u `.claude/settings.local.json`.

Kad Claude Code treba da čita ili menja fajlove u konkretnom folderu van projekta:

- u sesiji: `/add-dir /putanja/do/foldera`
- pri pokretanju CLI-ja: `claude --add-dir /putanja/do/foldera`
- trajno, u `.claude/settings.local.json` (ne ide u git):

```json
{
  "permissions": {
    "additionalDirectories": ["/apsolutna/putanja/do/foldera"]
  }
}
```

Dve stvari namerno nisam uključio. Režim `bypassPermissions` gasi sve upite, a dokumentacija ga predviđa samo za izolovana okruženja (kontejner, VM); na ličnom laptopu ti upit za nepoznatu komandu više vredi nego što smeta. Sandbox ne uključuj za ovaj projekat, jer ograničava shell komande na nivou OS-a, što je suprotno od onoga što tražiš.

Napomena o `allow` listi: `uv run *` i `make *` znače da se kod iz projekta izvršava bez upita. To je svestan izbor, jer bi inače svako pokretanje testova tražilo klik.

## Kako se radi jedna faza

1. Nov razgovor za svaku fazu (nov tab u ekstenziji). Kontekst prethodne faze ne treba; stanje je u `docs/PROGRESS.md` i u kodu.
2. Prebaci režim na **Plan** i pošalji:

   ```
   @docs/prompts/v1/1.1a-skeleton.md Implement this phase. Follow CLAUDE.md.
   ```

3. Pročitaj plan koji predloži. Ispravi šta treba, pa odobri. Za teže faze (1.4b, 2.3, 3.3, 3.4) pre slanja ukucaj `/effort high`.
4. Claude Code radi po commit jedinicama iz prompta: jedna jedinica, provera, commit. Commit sa neispravnim lint-om ili testom hook blokira.
5. Na kraju dobijaš „Phase report": šta je urađeno, commit-ovi, **nove zavisnosti**, **komande za pokretanje i proveru**, dokaz za svaku stavku iz „Done when".
6. Pre spajanja pošalji:

   ```
   Use the phase-verifier subagent on docs/prompts/v1/1.1a-skeleton.md
   ```

   Sub-agent proverava fazu iz čistog konteksta, bez uvida u to kako je kod nastao.
7. Probaj sam komande iz izveštaja. Kad si zadovoljan: `Merge this phase into main.`

Zavisnosti i komande za pokretanje nalaze se na dva mesta: unapred u `docs/SETUP.md` (preduslovi, paketi po fazama, `make` komande), i u izveštaju svake faze. `CLAUDE.md` obavezuje Claude Code da `docs/SETUP.md` ažurira u istom commit-u u kom doda paket, servis ili komandu.

## Redosled faza

| # | Prompt | Šta dobijaš | Pravi Gemini pozivi |
| --- | --- | --- | --- |
| 0 | `00-bootstrap.md` | git, uv, ruff, pyright, pytest, Makefile | ne |
| 1.1a | `v1/1.1a-skeleton.md` | Compose, Postgres, migracije, red poslova, worker, web skelet | ne |
| 1.1b | `v1/1.1b-ingest.md` | endpoint 1 (202), tekst iz PDF-a, pismo i jezik, normalizacija | ne |
| 1.2 | `v1/1.2-requirements.md` | `LLMClient`, ekstrakcija zahteva, endpoint 3, ekran za potvrdu | 1 ručna proba |
| 1.3 | `v1/1.3-golden-set-and-harness.md` | zlatni skup, `make eval` | 6 (staje u besplatnu kvotu) |
| 1.4a | `v1/1.4a-cv-parsing.md` | maskiranje, parsiranje CV-ja, staž | dev skup: plaćeni tier ili više dana |
| 1.4b | `v1/1.4b-judge-and-score.md` | sudija, provera citata, skor, baseline | plaćeni tier |
| 1.5 | `v1/1.5-interface.md` | rang lista, presude sa označenim citatom | ne |
| 1.6 | `v1/1.6-observability.md` | Langfuse, cena i latencija po koraku | malo |
| 1.7 | `v1/1.7-guardrails-and-ci.md` | skriveni tekst, red-team skup, GitHub Actions | red-team skup |
| 1.8 | `v1/1.8-v1-gate.md` | odluka da li je v1 gotov, tag `v1.0.0` | plaćeni tier, 3 prolaza |
| 2.1 | `v2/2.1-chunking-and-embeddings.md` | `chunk` tabela, bge-m3, backfill, reindex | ne |
| 2.2 | `v2/2.2-evidence-retrieval.md` | dense, leksički, hibrid, rerank; ablacija | za poređenje sudije |
| 2.3 | `v2/2.3-endpoint-2.md` | endpoint 2: prefilter, top N, top K | plaćeni tier |
| 2.4 | `v2/2.4-batch.md` | uvoz 100 CV-jeva, oporavak workera | plaćeni tier |
| 2.5 | `v2/2.5-hnsw-experiment.md` | merenje: exact naspram HNSW | ne |
| 2.6 | `v2/2.6-v2-gate-and-refactor.md` | odluka za v2, refaktor pred v3 | plaćeni tier |
| 3.1 | `v3/3.1-code-validator.md` | provere kodom, varijante A i B | iz keša + malo |
| 3.2 | `v3/3.2-verifier-and-rejudging.md` | verifikator, ponovno suđenje, A/B/C/D | najskuplji eval u projektu |
| 3.3 | `v3/3.3-questions-and-rules.md` | pitanja HR-u, verzionisana pravila | malo |
| 3.4 | `v3/3.4-resolver.md` | agent sa 7 alata i budžetima | plaćeni tier |
| 3.5 | `v3/3.5-rubric-lint-and-question-value.md` | pitanja unapred, filter korisnosti pitanja | plaćeni tier |
| 3.6 | `v3/3.6-langgraph-port.md` | isti tok na LangGraph-u | malo |
| 3.7 | `v3/3.7-mcp-and-notifications.md` | MCP server, n8n obaveštenje | ne |
| 3.8 | `v3/3.8-red-team.md` | uspešnost napada po sloju odbrane, tag `v3.0.0` | plaćeni tier |

Faze se rade redom. Gejtovi (1.8 i 2.6) su tu da zaustave rad: ako prag nije pređen, sledeća verzija ne počinje, kako plan i kaže.

## Gde sam odstupio od plana

| Šta | Zašto |
| --- | --- |
| `LLMClient` se pravi u 1.2, ne u 1.4 | Ekstrakcija zahteva u 1.2 već zove model, a rate limiting je po planu obavezan od prvog poziva. |
| F1 ekstrakcije se meri u 1.3, ne u 1.2 | Zlatni oglasi nastaju tek u 1.3. |
| „Izmena zahteva ponovo ocenjuje CV-jeve" se proverava u 1.4b | Sudija ne postoji pre 1.4b; 1.2 samo stavlja posao u red. |
| Maskiranje ličnih podataka je u 1.4a | Tabela faza ga ne pominje, a mora postojati pre prvog LLM poziva koji vidi CV. |
| 1.1 i 1.4 su podeljene na a i b; dodati su 0, 1.8 i 2.6 | Jedna faza treba da stane u jedan razgovor. Gejtovi i refaktori iz plana su dobili svoj prompt. |
| U v1 se citat koji ne prođe proveru ne prikazuje kao dokaz | Petlje nema do v3, a kriterijum 1.4 traži da svaki prikazani citat postoji u CV-ju. |
| Tekstove zlatnih CV-jeva piše sam Claude Code | Plan traži da generator bude drugi model od sudije. Ovako je to ispunjeno i ne troši Gemini kvotu. |

Četiri odluke plan ne definiše. Promptovi traže od Claude Code-a da ti predloži rešenje pre implementacije: kako se računa težina zahteva koji ima `parent_id` (1.4b), formula kad oglas nema poželjne zahteve (1.4b), šta varijanta B radi sa označenom presudom (3.1), šta je tačno „shortlist" (3.5).

## Na šta da paziš

- **Gemini kvota.** Testovi nikad ne zovu pravi model. Pre svakog pokretanja sa više od pet pravih poziva Claude Code ispisuje broj poziva i procenu cene i čeka potvrdu. Besplatnih 20 poziva dnevno ne pokriva eval od 1.4b nadalje.
- **Default model.** Na Pro planu `default` je sada Opus 5.5. Zato `settings.json` eksplicitno postavlja `"model": "sonnet"`, što je trenutno Sonnet 5.5.
- **Faza 1.3** troši najviše Claude tokena, jer se pišu profili i 60–90 CV-jeva. Prompt je deli u serije od desetak CV-jeva sa commit-om posle svake.
- **Pravi CV-jevi.** `data/real/` je zabranjen za čitanje. Sve što Claude Code pročita odlazi Anthropic-u, isto kao što bi besplatni Gemini tier video sadržaj.
- **RAM.** Langfuse, reranker i n8n ne staju zajedno u 12 GB. Promptovi 1.6, 2.2 i 3.7 traže proveru `docker stats` pre paljenja.
- **Hook-ovi.** Ako ti gejt pre commit-a zasmeta u nekoj sesiji, pokreni Claude Code sa `ATS_SKIP_GATE=1`.
- **v3 promptovi** su napisani prema planu kakav je danas. Posle gejtova v1 i v2 plan će se verovatno promeniti (pragovi, odluka o petlji u 3.2), pa ih tada pregledaj pre upotrebe.
