# 🧭 CareerCompass

> An AI-powered career platform for B.Tech CSE students and early-career professionals in India: match a high-fit role, benchmark the pay, plan the skills, and track the live jobs you apply to.

CareerCompass is more than a role quiz. It matches you to high-fit tech roles, benchmarks Indian
compensation, generates a personalized AI skill roadmap, and turns that roadmap into a trackable,
week-by-week study plan — with a context-aware AI mentor you can chat with throughout. It does not
stop at the plan either: the same app searches **live postings** from the public job boards, links
straight out to the original listing to apply, and keeps every application on a stage you can see.

The project is a **monorepo**: a **FastAPI** backend, a **React + TypeScript** single-page frontend,
and the original **Streamlit** app preserved in `legacy/` for reference.

---

## ✨ Features

| Feature | What it does |
|---|---|
| 🎯 **Interest-first, transparent role matching** | Ranks roles by how well they align with your *stated* interests (65% weight) and your existing skills (35% weight), and filters out roles with zero interest synergy. Every card shows the arithmetic: the two component scores, the interests and skills that counted, and the profile chips that would raise the match. |
| 🧠 **Semantic recall** | A two-stage matcher: candidates are first *recalled* from a Qdrant vector index (so a role can surface on the meaning of your profile and free-text goal, not only on identical chips), then *scored and explained* by the same transparent formula as ever. Each result says whether it was found by keywords, by meaning, or both. The index is optional and built by an explicit migration — without it, matching is keyword-only. |
| 📚 **Role catalog** | 100 curated corporate and modern engineering roles across 8 categories — including AI/ML, data, cloud, security, hardware and product tracks — each with responsibilities, qualifications, growth paths, and hiring companies. The Category filter is that closed taxonomy plus one escape hatch: a role the eight cannot place is filed under **Other / Unclassified** rather than becoming a ninth category nobody declared. |
| 💼 **Live jobs, filtered** | A dedicated **Jobs** page searches the postings collected from the public boards and filters them by role/keywords, location, work arrangement and experience — every condition has to be satisfied, so a search for "java" cannot answer with a listing that never mentions it, and the counts cover the whole collection because the filters run in the vector store and the words are matched against the eligible payloads — and a **✨ Use my profile** action runs the search straight off your questionnaire answers. Location suggestions are the boards' real places, each with the count a search for it returns, and results put postings whose *titles* carry your words first (marked on the card), with the index's meaning ranking the rest. Every match card carries an **Explore Jobs** action that deep-links to the page with that role already filled in and searched, and each role card and role page also lists its own **live openings** inline, ranked with your profile folded in (`POST /jobs/for-role`). Cards show the posting's title, company, location, work arrangement, salary when the board states one, posting date, source and the original application link — and every search says when the postings were **harvested**, with an amber warning once that date is more than two weeks old. Each card also carries the classifier's reading of its advert — the role family and its category, the demanded versus welcomed skills, or **Unclassified** with the reason — and a listing nobody has read yet offers a one-click **🤖 Classify this role** instead, so the reading is made where a reader asks for it rather than assumed across a feed the classifier has only sampled. |
| 🧭 **AI role classification** | Reads each listing's own advert — description and requirements, not the title it was posted under — and files it in a declared vocabulary of 63 role families across the 8 categories, returning the canonical role, related titles, **required** and **preferred** skills kept apart, minimum experience, seniority, work arrangement and a confidence. Two roles that merely overlap in skills are kept distinct (SRE vs DevOps vs Platform Engineer; Generative AI vs AI Agent Engineer), Java Backend Developer / Backend Engineer / Software Engineer I all land on Backend Development, and a listing whose advert says too little is reported as **Unclassified** with the reason rather than guessed at. Verdicts are stored per listing (keyed on the advert text, the model and the prompt wording) so the same advert is never classified twice, its category becomes a filter over the classified part of the feed through the API (`/jobs/search?category=`) — and `/jobs/classify` spends an AI token only when it actually reaches the model. |
| 🔖 **Saved jobs & application tracking** | Every posting carries a **Save job** button, and the saved ones live on an **Applications** page grouped by the stages a search actually follows — Saved → Applied → Interview → Offer, plus Closed for the ones that went nowhere — each with a free-text note, the date it was last moved, and a link back to the original listing. A row is a *snapshot* taken when it was saved, so it survives the board taking the listing down and the index being rebuilt; it is private to the account, and saving the same posting twice can never reset a stage you already advanced. |
| 💰 **India salary benchmarks** | Fresher (0–1 yr), mid (1–3 yrs) and senior (3+ yrs) CTC bands for every role, each stated as an *envelope* — low end a typical mid-market/services offer, high end a strong product-company or GCC offer — with the market and product-company medians and every source (and its sample size) linked on the role page. |
| 🤖 **AI skill roadmap** | Google Gemini generates a structured 3-phase plan (Immediate → Level Up → Explore) with one curated free resource per skill. Every role card has a one-click **Generate AI Roadmap** button that lands on the rendered plan. |
| 🛠️ **Portfolio projects** | Each roadmap includes 3 hands-on project ideas with difficulty ratings and validated skills. |
| 📅 **Study tracker** | Configure weekday vs weekend study hours and a role-specific tech stack. Every one of the 100 roles ships a tailored three-dimension stack (mobile, games, embedded, design, offensive security and more), and each choice maps onto syllabus topics with subtopics. Progress, remaining hours, and projected weeks are computed live. |
| ⚖️ **Side-by-side comparison** | Compare up to 3 roles on role responsibility, demand, competition, AI-future relevance, salary, must-have skills and top hiring firms. |
| 💬 **Roadmap Copilot** | A multi-turn Gemini chat pre-loaded with your profile, target role, and roadmap — replies stream in live. It sits **on the roadmap page itself**, beside the plan it is answering questions about, and the thread is remembered for the tab so stepping away and back does not lose it. |
| ⬇️ **Export & share** | Download any roadmap as a portable Markdown file. |
| 🔗 **Deep links** | Every view is its own URL (`/roles/backend_dev`, `/tracker/backend_dev`), so refreshing or sharing a link returns you to the same page. |
| 🔑 **Accounts & persistence** | Sign up / sign in (JWT bearer, SQLite-backed), saved profiles, and a **My Roadmaps** library of every plan you generate — each one recording the model and prompt version that produced it, and used to re-open a plan instantly instead of generating it again. |

### 💰 How the salary bands work

The bands are an **envelope**, not a survey of one employer tier: the low end is a typical
mid-market or services offer, the high end a strong product-company or GCC offer. They were
last reviewed in **October 2026** against independently collected sources, and each role page
links every one of them:

| Reference point | Source | What it measures |
|---|---|---|
| Market median | [Indeed India salary pages](https://in.indeed.com/career/salaries) | What Indian employers actually post, mass market included (samples of 5–10,900 postings per title) |
| Product-company median | [Levels.fyi India](https://www.levels.fyi) | What product companies and GCCs pay for the same title, from verified offer letters |
| Fresher direction | [TeamLease Digital Skills & Salary Primer FY2025-26](https://business.teamleasedigital.com/digital-skills-and-salary-primer-fy2025-26/) | Where the 2026 fresher market sits (AI/Cloud start at ₹7–8.5 LPA) |

Two honesty rules are enforced by tests: every role cites at least one market-wide source,
and any role whose reference points are borrowed from an adjacent role family says so on the
page instead of hiding it. Where the sources disagree — and they disagree by design, because
they sample different employers — the band spans them rather than picking a winner.
AmbitionBox and Glassdoor, which this project cited before, block automated access; they were
replaced with sources a reader can actually open.

---

## 🏗️ Architecture

A monorepo with a clean client/server split and a layered backend:

```
┌────────────────────────────────────────────────────────────┐
│  frontend/   React + TypeScript SPA (Vite + Tailwind)      │
│              React Router · TanStack Query · JWT context   │
└───────────────────────────┬────────────────────────────────┘
                            │  REST / JSON  (Bearer JWT)
┌───────────────────────────▼────────────────────────────────┐
│  backend/    FastAPI                                       │
│              app/routers/*  →  app/schemas.py              │
│              app/dependencies.py (JWT + AI quota)          │
│              app/security.py                               │
├────────────────────────────────────────────────────────────┤
│  service layer   services/ai_service.py       (Gemini)     │
│                  services/prompts.py          (wording)    │
│                  services/sanitize.py         (prompt I/O) │
│                  services/rate_limit.py       (AI quota)   │
│                  services/career_service.py   (matching)   │
│                  services/tracker_service.py  (syllabus)   │
│                  services/auth_service.py     (accounts)   │
├────────────────────────────────────────────────────────────┤
│  retrieval       services/vector_store.py  →  Qdrant       │
│                  services/embeddings.py    (Gemini/local)  │
│                  services/job_feed.py      (public boards) │
│                  scripts/ingest_roles.py · ingest_jobs.py  │
├────────────────────────────────────────────────────────────┤
│  data layer      database/db.py  →  SQLite                 │
│                  data/roles.json · data/stacks.json        │
└────────────────────────────────────────────────────────────┘
```

`legacy/` holds the original Streamlit application (UI + the same services), kept as a working
reference and design source.

### 🧠 How matching works (two stages)

1. **Recall** — `career_service.match_roles_smart()` searches a Qdrant index of every role's
   profile text (title, description, responsibilities, skills) using the candidate's interests,
   skills and free-text goal, plus the rest of the questionnaire — experience, preferred work setup
   and **preferred work hub**. The pool is the keyword-interest matches **plus** the nearest roles
   the index found that keywords missed.
2. **Score** — those candidates go through the unchanged, explainable scorer: 65% interest fit +
   35% skill fit, with the matched chips and suggested additions shown on every card.

Recall can only ever *add* candidates; it never changes a score, so the arithmetic a candidate
reads stays exactly reproducible. Vectors live in a collection named after their embedding space
(provider + model + width) and everything degrades to keyword-only matching when the index is
missing, stale or unreachable.

**Where you want to work.** The questionnaire's *Preferred Work Hub* offers the Indian hubs the
salary bands and hiring-company lists are built around, then the international hubs the live boards
actually publish into — London, Dublin, Berlin, Amsterdam, Zurich, Barcelona/Madrid, Stockholm,
Dubai, Singapore, Toronto/Vancouver, New York, the Bay Area and Sydney — and *Open to Relocating*
runs from "only my current city" to "anywhere in the world". The answer is a recall signal for
matching and part of the query behind `POST /jobs/for-role`, so naming a hub steers both the role
recall and that role's live openings.

**Which embeddings?** Gemini (`gemini-embedding-001`, Matryoshka-truncated to 768 dims) when
`GEMINI_API_KEY` is set, otherwise a deterministic offline embedder that needs no key, no network
and no model download — which is also what the test suite and CI run on. The provider that built
the index is recorded next to it, so the API always queries the collection that actually holds the
vectors.

### 📏 Does the index find the right role? (measured, not asserted)

"Offline embeddings are weaker, Gemini is better" is exactly the kind of claim that deserves
numbers, so recall is tuned against a labelled set rather than by reading a few examples.
`backend/evals/` holds **35 questionnaire profiles** — interests and skills drawn from the real
form, plus the career goal, so every profile is one a candidate could actually submit — each
labelled with the role(s) it means. The harness walks them through the real recall path and reports
what the current configuration does:

```bash
cd backend
.\.venv\Scripts\python.exe -m evals.retrieval_eval --provider both
```

The labels are strict about what counts as evidence: every expectation is classified at run time,
using the matcher's *own* keyword rule, as either **keyword-reachable** (the chip overlap would have
found it anyway) or **meaning-only** (only the vector index can get there) — because only the second
kind shows the index earning its place. Against the 100-role catalogue, at `k = 5`:

| Metric | Offline embedder | Gemini `gemini-embedding-001` |
| --- | --- | --- |
| hit@5 — an expected role among the 5 nearest | 85.7% | **97.1%** |
| recall@5 — share of the expected roles found | 81.4% | **97.1%** |
| MRR — how high the first expected role ranks | 0.571 | **0.789** |
| meaning-only hit@5 — the cases keywords cannot reach | 70.0% | **100%** |
| served — an expected role reached the scored results | 97.1% | **100%** |
| served@5 — an expected role reached the 5 ranked results | 45.7% | 45.7% |

Both embedders clear the bar that matters — an expected role reaches the scored results in 97–100%
of cases, against **71.4% with no index at all** — and Gemini is clearly better on the meaning-only
cases, which is the "offline embeddings are lexical" caveat with a figure behind it at last. The
harness also sweeps the similarity floor that gates meaning-only recall (`SEMANTIC_FLOOR`),
reporting meaning-only recall against how many extra neighbours per candidate the gate lets through,
with the configured value marked and the best-F1 point named. Three findings it makes visible:

- **The configured floors are more permissive than the labels justify.** For Gemini, `0.60` keeps
  every meaning-only label but passes essentially the entire 40-neighbour window (~39 extra
  neighbours per candidate), while `0.70` keeps the *same* recall for ~4. For the offline embedder
  the trade is genuine rather than free — `0.15` keeps 90.9% of the meaning-only labels, whereas
  `0.35` would keep only 36.4% — which is why the two providers carry different floors. (Those
  figures describe the *gate*; the page still caps meaning-only additions at
  `SEMANTIC_EXTRA_LIMIT = 10`.) Retuning a floor changes what candidates see, so it is recorded here
  as the next step rather than changed quietly.
- **The index adds reach, not rank.** `served@5` does not move at all: a role found on meaning alone
  earns a 0% interest score, so it sorts below the roles whose chips matched. That ordering is the
  transparent scorer doing its job, not the index failing — the index's contribution is the
  **+25.7pp** (offline) and **+28.6pp** (Gemini) of cases where the intended role reached the page at
  all instead of not existing for that candidate.
- **The sweep's precision is a lower bound.** It counts every role the labels do not mention as
  wrong, so read it *across* thresholds — it is a relative signal, not a verdict on the index's
  taste.

### 📥 Live job postings (`job_role`)

Alongside the curated catalog there is a second, independent collection holding **real, currently
open postings**, collected from public job-board APIs by `services/job_feed.py`. Each posting is
normalised into one shape — title, company, location, remote flag, employment type, seniority,
categories, salary, publication date, its own URL, the board it came from and the *board's own id*
for it (`source_job_id`, beside the namespaced `id` we key on) — with the HTML stripped so the text
can be embedded. Every board's terms are respected: a descriptive `User-Agent`, a pause between
pages, a documented page ceiling per source, and every record keeps its board name and original link.

**Adzuna leads**, because it is the only one of the three that publishes into India: `in` is one of
the markets its API documents, and it aggregates Indian boards and employers rather than being a
single one — so an India-first feed no longer depends on how deep a remote-first global board happens
to be read. It is keyed (`ADZUNA_APP_ID` / `ADZUNA_APP_KEY`, free from
`developer.adzuna.com/signup`) and its free tier is small — 25 hits a minute, 250 a day — so the
harvest is a *bounded plan* (`ADZUNA_QUERIES`) rather than "read everything Adzuna has": twelve pages
India-wide, two pages for each of six hubs, and one for `what=remote`, which is 1,250 adverts for 25
of the day's hits. The market is read whole *and* city by city because the newest postings nationally
are not the newest in Bangalore, and a hub query is the only way to see what a hub itself holds. The
daily allowance would afford a deeper read; the per-minute one is what stops it, because pages go out
back to back and a longer plan rate-limits itself part-way through and loses what it has not read yet.
Two of its terms are honoured in the UI: every displayed advert carries an **"Adzuna"** link back to
`adzuna.in` (see `JobCard`), and a candidate reaches an advertiser through Adzuna's own
`redirect_url` rather than around it. Nothing here scrapes `adzuna.in` itself — that site blocks
automated access, and the API is the permitted route to this data.

Two of its fields need care, and both are recorded as *derived* rather than falling back to a guess.
Adzuna publishes no remote flag and no experience level at all, so a remote marking on one of its
cards is read out of the advert's own words (`REMOTE_WORDS`) and the card says "(from the ad)"; the
experience filter falls back to the title, as it already did. And `salary_is_predicted` marks a
Jobsworth *estimate* rather than a figure the advertiser stated, so an estimated salary is dropped
instead of rendered as though it were disclosed — this app already publishes its own modelled bands,
and a candidate is owed the difference between a number someone offered and a number a model guessed.

The two boards that came first are kept as the **supplementary** sources they have become: Himalayas
is remote-first and global, Arbeitnow is German, and neither takes a country, a city or even a
keyword — Himalayas answers its ordinary newest-first feed to `country=India`, `location=India`,
`search=` and `q=` alike. Their page ceilings are now sized to that role (ten and one), because
the depth Himalayas used to be read at was bought to reach India, which Adzuna supplies properly.
They are also what an "abroad" answer falls back on. The harvest cap has to clear all three ceilings
together (2,100 for 1,750 raw rows), or the first source fills the run and the next is left with
nothing.

A harvest de-duplicates by title, company **and place** — the same opening, in the same place, is the
same opening. Title and company alone are not enough: a company advertising one title twice, in Pune
and again in Hyderabad, is advertising two vacancies, and only one row per key is ever indexed, so
collapsing them would delete a vacancy the boards had published. The cost is the mirror image and is
the direction to err in — the same opening written up by two boards in two places stays as two rows,
which is visible and names its board on the card, while a merged-away vacancy is simply gone. The
surviving records are embedded into `job_role` with the same embedder as the catalog. Each payload
keeps the text it embedded
(`search_text`) beside the 320-character `excerpt` a card displays, because the API answers its
keyword condition from the payload and a card's first paragraph is not what was ranked on. It also
keeps `published_ts` — the publication date as an epoch — which is the form the "posted within"
filter has to compare, and which is simply *absent* for a posting no board dated, so an undated
advert cannot pass a date filter on a technicality. The two
collections share one store but not one
fate: rebuilding either one leaves the other untouched. Because `job_role` is a plain, human-chosen
name, which embedding space it holds is recorded in a sidecar file (`<index>/job_role.space`) and
a later ingest in a different space is refused rather than silently mixing incomparable vectors —
`--rebuild` is the explicit opt-in to switch. The same run also creates the payload indexes the Jobs
page's filters read (`services.job_service.FILTER_INDEXES`); the embedded store ignores payload
indexes, but a deployment with `QDRANT_URL` set needs those text indexes (and the integer index the
date filter reads) before Qdrant will run a filter at all, so re-run the migration once after pulling
a change to the filter fields.

`GET /jobs/search?q=…` serves them, and the search box's words are a **filter**: a posting comes
back only when it *says* every one of them, matched as whole words anywhere in the posting, with the
payload's text fields as evidence — title, company, categories, tags, excerpt, and `search_text`, the
text the ingest embedded, so the condition is judged on the same words the ranking ran on. The rule
(`job_service.matches_token`) is deliberately wider than a substring test and narrower than a prefix
one: a plural counts ("developer" finds `developers`) and a compound the word introduces counts
("node" finds `node.js`), but a longer word that merely starts the same does not — "java" must not
answer with JavaScript, and "data" must not answer with databases. It is answered in Python over the
eligible payloads (`vector_store.scroll_payloads`) rather than by a store-side full-text clause,
because the rule belongs to the app and not to a tokenizer, and because the count has to cover the
whole collection: `matched` is what the words *and* the filters leave, alongside `count` (this page)
and `indexed` (the collection). When nothing says all of the words the search loosens to requiring
any of them and reports it (`relaxed: true`) — a goal sentence typed into the box must not empty the
page — so the request found less than it was asked for and the page says which words to drop rather
than silently answering a different question.

Ranking is then the store's cosine `similarity` plus a re-rank on the words the posting actually
says. The index ranks by meaning, and that is not enough for a search box: on the offline embedder a
query for "python" comes back with a German facilities-maintenance listing second, ahead of postings
that name the language. So the store ranks the postings that survived the words — restricted to
exactly those ids — over a window four times the page, and `job_service._rank` sorts it on three keys:
how many of the query's words the posting's *title* carries, how many it carries anywhere in its text,
then the cosine. Each result reports the title words it matched as `matched_terms`, so the order
explains itself on the card, and only the caller's own words are ever judged — an earlier version
ranked on the filter words too, so searching "java" in Amsterdam answered with postings whose titles
said "Amsterdam". A query no posting carries leaves every row in one tier, and the stable sort returns
the index's own order untouched.

The structured filters the page offers — `location`, `remote`, `experience` and
`employment_type` — are applied **in the
vector store**, as a Qdrant payload filter, rather than to the results afterwards, so they narrow the
whole collection as well. Location and experience are matched as whole words, so "Berlin" finds
`Berlin, Germany` while `Internal Tools Engineer` is not an internship. This is where a provider
that publishes less becomes visible rather than invisible: no board here publishes an experience
level or an employment *vocabulary*, so both filters are translations of what the boards wrote —
Adzuna splits how a job hires into `contract_time` and `contract_type`, so "full time, permanent"
answers two of the buckets and five buckets cover every board's wording. The endpoint also accepts a
date window (`posted_within_days`) and a `category`, and the page offers neither: a harvest holds
only the boards' newest postings, so its date windows answer identically, and `category` reads the
classifier's verdict, which exists for a small, on-demand share of the feed — on the page either
one would look like a filter that simply finds nothing. There is deliberately no
fallback here, because unlike the curated catalog the index is the *only* copy of this data: when the
index has not been built the endpoint still answers `200`, with `available: false` and no rows, so a
client hides the section instead of surfacing an error. The endpoint is public, like `/roles` — these
are public listings carrying no user data.

A feed can also be short for a reason worth stating, so the response carries a **`sources`** block:
what each provider contributed to the harvest that built the index, and — for one that could not be
read — the reason in wording a reader can act on ("Adzuna is not configured on this server:
ADZUNA_APP_ID and ADZUNA_APP_KEY must be set…"). That distinction is why the harvest records it at
all: the postings themselves cannot tell "never configured" from "had nothing new", and only the
harvest hears from a board that failed. The record is written into the artifact as well as beside
the collection, so an index built with `--from-file` reports the same thing a live harvest would
rather than only the boards its rows happen to name. A board that loaded and found nothing is
reported too, with `postings: 0` and no error — which is what a category tag a market does not
carry looks like. An index built before any of this was recorded answers an empty list, which a
client reads as "nothing to report" rather than as a silent all-clear.

A credential never appears in that reason. A board that refuses the request quotes back the whole
URL it was given, and the key is in that URL's query — so the phrase is redacted of the app id and
key both where the harvest records it and where this endpoint serves it, including out of an index
written before either was true.

`GET /jobs/locations` is the place vocabulary those filters accept: the boards' own wording, cut
into comma-separated segments and ranked by how often each appears ("Berlin", "Germany", "United
States", "Remote"), with the numbers **asked of the same store filter a search applies** — so the
count beside an option is the `matched` that search then reports. The Jobs page fills its location
suggestions from this instead of from the fifty postings the last search happened to return, which
on a fresh page was nothing at all. Candidates the store cannot match are dropped rather than
offered as dead ends: postcodes, numbered districts, and any "remote…" place, which the filter
widens to the boards' own remote flag and so would advertise the whole remote feed.

The same read carries a second list, `preferred`: the **Indian hubs this app is built around**
(`job_service.PREFERRED_JOB_LOCATIONS`), counted by that same filter but listed even when they
count nothing. The counts are live — Adzuna covers the Indian market, so the hubs it names are real
options and the ones nobody lists say *no live postings* rather than being dropped — and a page that
answered an empty hub with silence would be the least honest part of the feature. The hubs are
spelled out one city at a time rather than as the questionnaire's labels ("Mumbai / Pune"), because
the store's location filter requires *every* word it is handed: a hub name would ask the feed for a
posting naming both cities and return nothing. Adzuna's own place field is what makes this work at
all: its `area` list arrives country-first ("India", "Karnataka", "Bangalore") and is turned round
into `"Bangalore, Karnataka, India"`, because the country has to be a segment the page can name —
otherwise an advert naming only its city would not answer a search for India, and the one board that
covers the home market would count for nothing in it.

Live postings age, so the feed also carries its own **provenance**. The harvest is stamped when it is
pulled: `services/job_feed.save` writes `{"harvested_at", "postings"}` rather than a bare list (an
artifact from an older version still loads, with no date), and `scripts.ingest_jobs` copies that date
— plus the ingest time — into a sidecar beside the collection (`<index>/job_role.meta.json`, the same
mechanism the embedding-space guard uses). `GET /jobs/search` therefore reports a `freshness` block:
the harvest date, the whole days since it, and whether that has reached
`job_service.STALE_AFTER_DAYS` (14). The judgement is the backend's and the page renders it rather
than re-deciding, so it shows "Harvested on 2026‑09‑22 (25 days ago)" under the results and adds an
amber warning past the threshold — because a board goes on serving a listing after the job is filled,
so a posting's own date says when the *job* was posted, never when CareerCompass last looked. When
nothing recorded a date, the response says so instead of inventing one, which is the honest answer on
a `QDRANT_URL` deployment: the sidecar is written next to the ingest, and that is not necessarily the
machine answering requests. `/health` reports the same block, so a monitor can see a feed going stale
without running a search. Re-ingesting is still an explicit migration, but it now takes
`--if-stale DAYS`, which makes a frequent schedule a no-op while the feed is young (see SETUP §2.9).

`POST /jobs/for-role` is the other read over the same collection. Given a catalogued role id and the
candidate's questionnaire answers, it ranks the postings against that role's own index document *plus*
those answers (`vector_store.profile_query`), so the same role can come back in a different order for
two people — and an empty profile degrades to a plain search for the role rather than failing. It is
POST rather than GET because the profile travels with the request, it is what fills the **live
openings** list on each role card and on the role page, and it keeps `/jobs/search`'s honesty contract:
no index means `available: false` and no rows.

`POST /jobs/classify` is the one job endpoint that spends anything, and the only one that
*writes*. It reads a single listing's own advert — the description and requirements as far as
the payload holds them, not the title it was posted under — and answers with what the job
actually is: the canonical role family, the titles a candidate might search instead, the
**required** and the **preferred** skills kept apart, the minimum experience the advert
states, the seniority level, the work arrangement, a confidence, and a one-line explanation of
what in the advert said so. The reading is done by Gemini against a **declared vocabulary**
(`config.CANONICAL_ROLES`: 63 families across the 8 catalog categories) that is rendered into
the prompt from the same declaration the answer is validated against, so the list the model
chooses from and the list the code accepts cannot drift apart. `primary_category` is *derived*
from the chosen role through that vocabulary rather than taken from the model's own pairing —
the role is the finer claim, so the two stored fields can never contradict each other.

Three decisions keep it honest. Two roles are never merged because their skills overlap: SRE,
DevOps and Platform Engineer are three families, as are Generative AI Engineering and AI Agent
Engineering, while Java Backend Developer, Backend Engineer and Software Engineer I all land on
Backend Development — which is the point of classifying the advert rather than the title.
Mandatory and preferred requirements are separate fields, because "must have Java" and "nice to
have Docker" are not the same sentence to someone deciding whether to apply. And an advert that
does not say enough is reported as **Unclassified** with the reason (`unclassified_kind` /
`unclassified_reason`: too thin, no declared family fits, confidence under 0.55, an unreadable
answer, or no answer at all) instead of being filled in from what the title implies — a title-only
posting is never sent to the model at all, because an advert with nothing in it is not a
classification problem, it is an advert with nothing in it. The model's own sentence is kept for
the case where it declined to place a clear advert (a sales role, say), so "we could not place
this" never has to stand in for two different things.

The verdict is stored once per listing (`listing_classifications`, keyed on the listing id) and
read through three keys — the advert's content hash, the model id, and the prompt fingerprint —
so re-harvested text, a pinned model or edited prompt wording misses the store and is read
again, while an unchanged advert is served without touching the AI. That is what makes a page
view free, and it is why the endpoint charges its AI token *after* the store has answered:
reading a verdict somebody else already paid for, or an advert that says too little to classify,
spends nothing (`app/dependencies.spend_ai_quota`). A failure that is a fact about the moment —
a 429, a dropped connection, an unreadable answer — is reported as Unclassified and deliberately
**not** written down, so the next reader asks again rather than inheriting a verdict nothing
supports. `POST /jobs/search` decorates every row it returns with the stored verdict when there
is one and takes `category` as a filter over the classified part of the collection: a listing
nobody has read belongs to no category, and `Other / Unclassified` is a category the classifier
*chose*, not a bin for the leftovers.

`python -m scripts.classify_jobs` is the other half: it reads the harvest artifact the ingest
wrote and pre-fills the store in the background (`--limit`, `--source`, `--force`, `--delay`),
skipping listings that already have a verdict and stopping if the model stops answering. It is
how a freshly ingested feed becomes a feed whose listings can already say what they are — and it
reads the artifact rather than the index because the embedded Qdrant store is locked by
whichever process has it open, which is usually the API.

The React **Jobs** page is that endpoint's front end. It opens from the navbar, and every match card
carries an **Explore Jobs** action that deep-links to it with the role prefilled (`/jobs?role=…`), so
going from a match to that role's live openings is one click; the URL stays the committed search, so
the page is shareable and survives a refresh. When a profile exists, **✨ Use my profile** fills the
query from the same answers the semantic role match runs on — the goal first, then up to three
interests and three skills, capped at 120 characters — and searches immediately, so the boards are
queried with the questionnaire rather than a typed guess. It is deliberately short: that string is
the *ranking text*, and with the title-match re-rank above, a focused query gives a sharper page
than the whole skill list does. The form's five fields map one-to-one onto the endpoint: the role box
carries the words (which filter, and which rank), and location, experience, work arrangement and
employment type are the filters the backend applies to the whole collection.
The page therefore shows collection-wide numbers — "showing 12 of 87 postings matching your search ·
951 indexed" — and the search box is optional: a filter on its own is a valid search, in which case no
words are required and the filter terms stand in as the ranking text, with the response echoing
whichever text it used. When the search had to loosen its words, an info note above the results says
so and names the words. It also handles the three load-time realities honestly: a spinner while the
search runs, `available: false` as a "run the migration" note rather than an error, and an empty state
that distinguishes "these conditions match nothing in the collection" from "everything matched but
nothing ranked".

Two of the filters deserve a note each, because they are judgement calls rather than board fields.
**Experience**: only one of the three boards publishes a seniority at all, so filtering on the raw
label would hide almost everything; instead each of the three buckets matches the title, the seniority
label *and* the contract wording (`internship`, `entry`, `senior` — the rules are in
`services/job_service.py`). **Employment type**: no board publishes the vocabulary either, so the five
buckets are a translation of how each one words it, and "full time, permanent" answers both of its
buckets. "On-site / not stated" is worded that way on purpose too: a false remote flag means the
listing did not say, not that the job is office-based — and on an Adzuna card, which has no flag at
all, a remote marking says "(from the ad)" because that is what it is.

Finding a posting is only half of a job search, so the feed also keeps what a candidate decides to do
about it. **Save job** files the posting (`POST /applications`, private) and the **Applications** page
(`/applications`) groups those rows by the stages a search actually follows — Saved, Applied,
Interview, Offer, and Closed for the ones that went nowhere, because a tracker with no exit for dead
applications quietly fills up with rows that are no longer true. Each row carries a note, the date it
was filed and the date it was last moved, a stage selector, and a link back to the original listing.

Two decisions shape that table (`services/application_service.py`). It stores a **snapshot** of the
posting rather than a reference to it: the boards rotate, the harvest is refreshed, and the `job_role`
index is rebuilt from scratch on a re-ingest, so a row holding only a posting id would become a blank
line exactly when the candidate needs to know what they applied to. And saving is **idempotent** by
posting id — the insert conflicts and does nothing, so pressing Save again on a card cannot reset a
stage the candidate has already advanced, and the response reports whether the row was new (`201`) or
already there (`200`) rather than pretending either way. Every read and write is scoped to one user id,
and a row belonging to someone else answers `404` rather than `403`, the same way the study tracker does
it: whether a given application exists is itself private.

---

## 🧰 Tech Stack

| Layer | Technology |
|---|---|
| Backend language | Python 3.11+ (developed on 3.14) |
| API framework | FastAPI + Uvicorn |
| Validation | Pydantic v2 |
| Auth | PyJWT (HS256 bearer tokens) + PBKDF2-HMAC-SHA256 password hashing |
| AI | Google Gemini (`gemini-flash-lite-latest`) via `google-generativeai` |
| Frontend language | TypeScript |
| Frontend framework | React 18 |
| Build tool | Vite 5 |
| Styling | Tailwind CSS 3 |
| Routing / data | React Router 6 · TanStack Query 5 |
| Persistence | SQLite (embedded, zero-config) |
| Retrieval | Qdrant (`qdrant-client`, embedded local mode or a server) + Gemini / offline embeddings |
| External data | Adzuna (India-first, free key) · Himalayas · Arbeitnow public job-board APIs |
| Config | `python-dotenv` (backend) · Vite env vars (frontend) |
| CI | GitHub Actions |

---

## 📂 Project Structure

```
career-compass/
│
├── backend/
│   ├── app/
│   │   ├── main.py            ← FastAPI app, CORS, routers, /health
│   │   ├── config.py          ← env-driven settings
│   │   ├── schemas.py         ← Pydantic request/response models
│   │   ├── security.py        ← JWT create/decode
│   │   ├── dependencies.py    ← get_current_user / get_optional_user
│   │   └── routers/           ← auth · roles · jobs · applications · profile · match · roadmap · tracker · chat
│   ├── prompts/               ← system/ + user/ prompt templates, one pair per AI call (see its README)
│   ├── services/              ← ai · career · tracker · auth · applications · embeddings · vector_store · job_feed · prompts
│   ├── scripts/               ← ingest_roles.py · ingest_jobs.py (index migrations)
│   ├── evals/                 ← labels.json · retrieval_eval.py (labelled-profile recall harness)
│   ├── database/db.py         ← connection, schema, role-catalog sync
│   ├── data/                  ← roles.json · stacks.json · qdrant/ · job_postings.json (last two derived)
│   ├── tests/                 ← unittest: API integration + end-to-end journey
│   ├── requirements.txt
│   └── .env.example
│
├── frontend/
│   ├── src/
│   │   ├── api/               ← fetch client, typed endpoints, mirrored types
│   │   ├── components/        ← navbar, account menu, role & job cards, copilot panel, badges, alerts, layout…
│   │   ├── pages/             ← home · auth · profile · matches · directory · jobs
│   │   │                        role detail · compare · roadmap · roadmaps
│   │   │                        tracker · applications · chat
│   │   ├── state/             ← Auth · Profile · Compare · Roadmap contexts
│   │   └── lib/               ← option vocabularies, formatting, job filters, application stages, markdown export
│   ├── package.json
│   └── .env.example
│
├── legacy/                    ← original Streamlit app (UI/UX reference)
│
└── .github/workflows/ci.yml   ← backend tests + frontend type-check & build
```

---

## 🚀 Setup & Run Locally

Requires **Python 3.11+** and **Node 18+**. Run the backend and frontend in two terminals.

### 1. Clone

```bash
git clone https://github.com/YOUR_USERNAME/career-compass.git
cd career-compass
```

### 2. Backend (FastAPI)

```bash
cd backend
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env        # set JWT_SECRET (required); GEMINI + ADZUNA keys optional
python -m uvicorn app.main:app --reload
```

The API serves at <http://localhost:8000> (interactive docs at `/docs`). The SQLite database is
created automatically on first launch, and `backend/data/roles.json` — the catalog's source of
truth — is synced into it on every startup, so adding or editing a role there is picked up by the
next restart. Existing roles are updated in place and never deleted.

`backend/data/stacks.json` is the study-plan source of truth: it gives every role its
three-dimension stack selector (for example DevOps gets delivery pipelines and observability,
not "primary backend language"). `build_topics_from_choices()` turns the picked options into
syllabus topics — a fixed keyword map for the original roles, plus a block per newer
specialisation (mobile, games, embedded, design, offensive security, analytics engineering and
product/technical-programme tracks). Both live in `services/tracker_service.py`.

The semantic index is derived data: it is not committed and not built at startup, so run the
migration once — with the API stopped, because the embedded Qdrant locks its directory:

```bash
python -m scripts.ingest_roles --query "cloud infrastructure pipelines"
```

Re-run it whenever `backend/data/roles.json` changes (`--rebuild` drops the old collection
first). It embeds with Gemini when `GEMINI_API_KEY` is set, and with the deterministic offline
embedder otherwise; if Gemini is configured but unusable (quota, retired model, offline) it says
so and builds the offline index instead. Skip the migration entirely and matching stays
keyword-only — nothing else changes.

A second, independent collection holds **live job postings** rather than curated roles:

```bash
python -m scripts.ingest_jobs --limit 2100 --query "kubernetes platform engineer"
```

It collects postings from public job-board APIs (Adzuna, which needs a free app id and key, plus
Himalayas and Arbeitnow, which need none), normalises and
de-duplicates them, writes them to `backend/data/job_postings.json`, and embeds them into the
`job_role` collection — so the catalog index and the live feed share one store but not one fate.
Because `job_role` is a plain human-chosen name, the embedding space it holds is recorded in
`<index>/job_role.space` and a second ingest in a different space is refused rather than mixed;
pass `--rebuild` to switch. `--from-file` re-ingests the saved JSON with no network at all, and
the file carries the harvest's own board record beside its postings — so a server with no Adzuna
key still says so on the Jobs page after a file re-ingest, not just after a live one.

Then pre-fill what the listings *are*, so the Jobs page has classifications to show and filter
on from the first page view:

```bash
python -m scripts.classify_jobs --limit 100          # newest 100 without a verdict
python -m scripts.classify_jobs --force --limit 20   # re-read 20 existing verdicts
```

It reads the harvest artifact by default (so it can run while the API is up), spends one Gemini
call per listing with a `--delay` between them, skips anything already classified, and is safe to
re-run: run it again to carry on where it stopped. `--from-index` reads the live collection
instead, which needs the API stopped first. Nothing here is required — `/jobs/classify` will
classify a listing on demand too — but a feed that has been pre-filled answers instantly and
costs no quota to browse.

`JWT_SECRET` is required — generate one with
`python -c "import secrets; print(secrets.token_urlsafe(48))"`. The API refuses to start without it.

Get a free Gemini key at [aistudio.google.com](https://aistudio.google.com) → **Get API Key**.
AI features (roadmap, copilot, job classification) return `503` until `GEMINI_API_KEY` is set;
everything else works without it — including *reading* classifications that already exist.

### 3. Frontend (React)

```bash
cd frontend
npm install
cp .env.example .env        # VITE_API_BASE_URL=http://localhost:8000
npm run dev
```

Open <http://localhost:5173>. The backend's `CORS_ORIGINS` already allows the Vite dev origin.

### 4. Legacy Streamlit app (optional, reference)

```bash
cd legacy
pip install -r requirements.txt
streamlit run app.py        # http://localhost:8501
```

---

## 🔌 API Reference

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/health` | — | Service health, including semantic-index status (provider, collection, points) and job-feed freshness |
| `POST` | `/auth/signup` | — | Create an account, returns a JWT |
| `POST` | `/auth/login` | — | Authenticate, returns a JWT |
| `GET` | `/auth/me` | ✅ | Current user + profile |
| `GET` | `/roles` | — | Full role catalog, each role carrying its salary bands, review date and sources |
| `GET` | `/roles/categories` | — | The Category filter's vocabulary: the catalog's eight categories, then `Other / Unclassified` for a role the taxonomy cannot place |
| `GET` | `/roles/{role_id}` | — | Single role, including its salary provenance |
| `GET` | `/jobs/search?q=…&location=…&remote=…&experience=…&category=…&limit=…` | — | Live job postings: `q` is a condition (a posting must say every word, matched as whole words with plurals and compounds — the ones its title carries come back as `matched_terms`), `relaxed: true` when nothing said all of them and the search fell back to any of them, the other filters are applied by the store, `category` narrows to listings the classifier filed there (`400` for a label outside the taxonomy; a listing nobody has read matches no category), the response reports `count`/`matched`/`classified`/`indexed` and how old the data is (`freshness`), each row carrying its stored `classification` or `null`, and it says `available: false` until the `job_role` index is built |
| `POST` | `/jobs/classify` | — | What one listing actually is, read from its own advert: canonical role, related titles, required vs preferred skills, minimum experience, seniority, work arrangement, confidence. Per listing (one call = one AI token, charged only when the model is actually reached), answered from the store when it already has a verdict, `Unclassified` with a reason when the advert does not say enough, `404` for an unknown listing and `503` with no index or no key |
| `GET` | `/jobs/locations` | — | The places the postings actually name, commonest first, each with the count a search for it returns, plus the Indian hubs offered as preferences (`preferred`, count may be 0) — the Jobs page's location suggestions (`available: false` until the index is built) |
| `POST` | `/jobs/for-role` | — | Live job postings nearest to one catalogued role, ranked with the candidate's questionnaire answers (`available: false` until the index is built) |
| `GET` | `/applications` | ✅ | The candidate's saved postings and their stages, most recently touched first |
| `POST` | `/applications` | ✅ | Save a posting (the snapshot travels in the body). Idempotent by posting id: `201` when the row is new, `200` with the row already stored |
| `PATCH` | `/applications/{id}` | ✅ | Move a saved posting to another stage, edit its note, or both |
| `DELETE` | `/applications/{id}` | ✅ | Forget a saved posting |
| `GET` | `/profile` | ✅ | Saved profile |
| `PUT` | `/profile` | ✅ | Save profile |
| `POST` | `/match` | — | Ranked role matches with a score breakdown (+ optional AI explanation); the questionnaire's goal, experience, work setup and work hub feed the semantic recall stage only. Never fails on the AI budget — it drops the explanation |
| `POST` | `/roadmap` | optional | Generate an AI roadmap (saved when authenticated, with the model and prompt version that produced it) |
| `GET` | `/roadmaps` | ✅ | Saved roadmap library, each entry carrying its model + prompt version |
| `DELETE` | `/roadmaps/{id}` | ✅ | Delete a saved roadmap |
| `GET` | `/tracker/stack/{role_id}` | — | Specialization stack schema |
| `GET` | `/tracker/schedule/{role_id}` | optional | Study schedule |
| `PUT` | `/tracker/schedule` | optional | Save schedule (+ rebuild syllabus) |
| `GET` | `/tracker/topics/{role_id}` | optional | Syllabus topics + metrics |
| `PATCH` | `/tracker/topics/{topic_id}` | optional | Toggle a topic |
| `POST` | `/chat` | — | Copilot reply (non-streaming) |
| `POST` | `/chat/stream` | — | Copilot reply (streamed text) |

Full OpenAPI schema is available at `/docs` and `/openapi.json`.

The four endpoints that spend AI quota — `/roadmap`, `/chat`, `/chat/stream` and an
`explain: true` `/match` — are metered **per caller**, by user id when a bearer token
resolves and otherwise by client address (`AI_RATE_LIMIT` calls per
`AI_RATE_WINDOW_SECONDS`, both configurable). Over budget, the first three answer
`429` with a `Retry-After`; `/match` answers normally without the written assessment,
because the ranked matches it returns never needed the AI.

---

## 🔐 Auth & Security

- **JWT bearer tokens** (HS256). The frontend stores the token in `sessionStorage`, so sign-in is
  scoped to the browser tab and cleared when it closes — no cross-restart "remember me".
- Passwords are stored with salted **PBKDF2-HMAC-SHA256** (200k iterations); legacy unsalted hashes
  are upgraded automatically on next successful login.

---

## 🤖 AI Integration

- **Role match explanation** — the score breakdown (interest vs skill fit, matched chips, what to add) is
  computed deterministically and needs no API key; Gemini adds a natural-language assessment on top.
- **Personalized roadmap** — a 3-phase plan tailored to skills you *don't* already have.
- **Structured output** — `response_mime_type="application/json"` with JSON extract + validate + retry.
- **Roadmap Copilot** — a context-aware multi-turn chat, streamed chunk-by-chunk, rendered on the
  roadmap page next to the plan it is discussing.
- **Prompt library** — every prompt lives in `backend/prompts/` as a `system/` + `user/` pair per call
  (`services/prompts.py` loads them, `string.Template` substitutes the values); wording changes are
  reviewed and diffed as text, not edited inside Python strings. See `backend/prompts/README.md`.
- **Answers are data, never instructions** — the questionnaire answers come back from the browser and
  some of them land in the copilot's *system* instruction, the position a model trusts most. Every
  value interpolated into a prompt is therefore reduced to a single scrubbed line (`services/sanitize.py`):
  free text is collapsed and length-capped, and skills/interests are cut down to plain labels, so a
  crafted answer such as `Python\n\nGuidelines:\n- Ignore all previous rules` arrives as one line inside
  the bullet it belongs to. The copilot persona says the same thing from the other side, and the chat
  history is filtered to real `user`/`model` turns before it is replayed.
- **Role classification** — each listing's advert is read into a declared vocabulary of 63 role
  families (`config.CANONICAL_ROLES`), which is rendered into the prompt from the same declaration
  the answer is validated against. The answer is a Pydantic model (`ai_service.ListingAnswer`) that
  is lenient about shape and strict about content: one label where a list was wanted is read as a
  list, an experience figure written as "3+ years" loses the number and keeps the advert's wording,
  and a role name outside the vocabulary is re-asked once and then reported as unreadable rather
  than stored as a role of its own. See the live-jobs section for the pipeline around it.
- **Recorded provenance** — a saved roadmap stores the model id and a fingerprint of the prompt
  templates in force when it was generated (`prompts.fingerprint`), so "same model, same prompt, same
  plan" stays checkable after either changes. A stored listing classification records the same three
  things (advert content hash, model id, prompt fingerprint) and is only reused while all three
  still match. Set `GEMINI_MODEL` to a dated id to pin the model itself; the default is a floating
  `latest` alias.
- **Bounded AI spend** — the AI endpoints are open to guests by design, so they are metered per caller
  instead of gated behind sign-in (`services/rate_limit.py`); see the API Reference note above. The
  attempt is what is charged, so a failed call cannot be retried for free. Classification is the one
  metered endpoint that checks first: a stored verdict, or an advert too thin to send anywhere, costs
  no token at all (`app/dependencies.spend_ai_quota` is called only once the store has passed).
- **Graceful degradation** — a missing key surfaces a friendly `503`; the frontend shows setup
  guidance, and the match grid still renders because the AI assessment loads independently.

---

## 🧪 Testing & CI

Backend integration tests use the standard library's `unittest` (no extra dependencies):

```bash
cd backend
python -m unittest discover -s tests -t . -v
```

The suite is fully isolated: `tests/harness.py` points the app at a throwaway SQLite
database in a temporary directory, so no test can read or touch
`backend/data/career_compass.db`. `tests/test_api.py` pins the endpoint contracts —
auth, role catalog, matching, tracker, profiles and saved roadmaps, including that a
user can only ever reach their own records. `tests/test_roles_catalog.py` guards the
catalog itself: every role carries the full content contract, the salary bands rise
with seniority, every band cites dated, attributable sources (and explains itself when its
reference points are proxied from an adjacent role family), every role is reachable from a
real questionnaire answer, and an older database gains new roles — and the salary
provenance columns — on startup without losing saved work.
`tests/test_e2e_journey.py` walks the whole
candidate journey end to end: browse → register → sign in → profile → ranked matches →
role detail → study plan → tick off a topic → saved library, plus a check that progress
survives a new session. `tests/test_tracker_syllabus.py` guards the study plans: every
catalogued role has a tailored stack, every option maps onto real content, every
combination produces a usable plan, and the original roles' shipped plans are pinned so
adding content for newer roles cannot rewrite them. `tests/test_matching.py` guards the
transparency contract: the two component scores reproduce the published score, half-point
scores round the way a reader rounds them, and every suggested skill is a real chip that
cannot lower the match it was offered for. `tests/test_semantic_recall.py` guards the retrieval
layer, and is hermetic by construction: the harness forces the offline embedder and a throwaway
index directory, so no test ever calls Gemini or touches the developer's index. It pins that the
local embeddings are byte-identical across processes, that an absent index leaves matching
keyword-only, that recall can add candidates but never change a score, that meaning-only roles
still need real skills to score, and that the migration records the provider it actually used —
including when Gemini fails mid-run and the offline index is built instead. `tests/test_job_feed.py`
guards the live feed: every board's shape normalises into one record with its HTML stripped,
de-duplication collapses the same opening advertised twice, a board being down degrades the
harvest instead of failing it, and — the part worth pinning — the `job_role` collection refuses an
incompatible embedding space rather than mixing vectors, and rebuilding it leaves the curated role
index intact. Its network layer is replaced, so no test reaches a job board.
`tests/test_job_api.py` guards the read path over those postings: results never bleed in from the
catalog index sitting beside them in the same store, the nearest posting wins for a platform query,
the inputs are validated, and with no index built the endpoint answers `available: false` instead of
erroring. It also covers `/jobs/classify` and the classification-aware reads: the verdict is the
stored one whether or not the model was reached, a listing the classifier cannot place is answered
as `Unclassified` rather than failed, a missing key or index says so as a `503`, and the AI budget
is charged only when a model call is actually about to happen — reading a stored verdict, or an
advert too thin to classify, is free. `tests/test_classification.py` guards the pipeline itself, with
the model faked: the vocabulary the prompt offers is generated from the declaration the validator
checks against, the prompt documents every field the answer model requires, an advert containing a
command reaches the model as one flattened line, a hedged or unreadable answer is never dressed up as
a verdict, and the store is proven to miss on a changed advert, a changed model and changed prompt
wording (and to keep a thin verdict across a model change, because no model was involved in it). It
ends with the pre-fill script: an artifact of raw postings produces exactly the verdicts the API
would, under the ids the API looks up. `tests/test_rate_limit.py` guards the AI budget: the sliding window
allows exactly its quota, frees slots as they age, meters callers separately, and does not let a
rejected call push its own retry further away — then, at the endpoint level, that an over-budget
caller gets a `429` with a `Retry-After` from the copilot and the roadmap while `/match` still returns
its ranked answer. `tests/test_prompts.py` guards the prompt layer: every template exists on disk and
renders without a stray `$`, the values a caller passes actually reach the model, and — the part that
matters now that the copilot's context arrives from the browser — a crafted answer (a fake
`Guidelines:` block, a newline in a name, a malformed roadmap) cannot open a section of the system
instruction and is instead flattened into the data it belongs to.
`tests/test_retrieval_eval.py` guards the *instrument* rather than a score: the labelled set must be
well formed and realistic (every expected role id exists in the catalogue, every interest and every
skill is a real questionnaire option, ids are unique, and at least eight cases stay reachable only
by meaning — so the harness cannot quietly stop exercising the semantic path while still printing a
confident number), the metric arithmetic is right on ranked lists whose answer is known by hand, and
the whole path runs end to end against a real offline index. It also pins the honesty check that a
first draft of the harness failed: `semantic_search` is *designed* to swallow a provider failure and
return nothing, so an empty answer is probed and retried instead of being scored as a miss, and an
index that answers nothing at all is reported as a broken measurement rather than a fake recall
figure. The harness's own numbers are deliberately not asserted anywhere — they depend on the
provider, the catalogue and the network — so they come from running
`python -m evals.retrieval_eval` by hand and are recorded in the Architecture section above.

The frontend is checked with the TypeScript compiler and a production build:

```bash
cd frontend
npm run typecheck
npm run build
```

GitHub Actions runs both on every push and pull request (see `.github/workflows/ci.yml`).

---

## ⚠️ Known Limitations & Roadmap

- **AI SDK** — `google-generativeai` is deprecated by Google; migrating to `google-genai` is planned.
- **Offline embeddings are lexical** — the no-key fallback embedder is a signed hashing model over
  words and character 4-grams. It shortlists sensibly and keeps the app (and CI) hermetic, but
  Gemini embeddings are markedly better at pure paraphrase; configure a key and re-run the
  migration to use them. The evaluation harness above puts a figure on the gap: 70% versus 100% of
  the cases that keywords cannot reach.
- **The retrieval evaluation is a small, hand-written label set** — 35 profiles is enough to compare
  two embedders and to see where a similarity floor sits, and not enough to settle either question:
  each label is one person's judgement, the larger families (platform/SRE, backend, data) are
  represented by a handful of examples each, and the sweep's precision counts unlabelled roles as
  wrong, so it reads as a relative signal rather than an absolute quality. Measuring both spaces
  needs a quota-free Gemini key: a full run costs ~135 embed items, against a free-tier budget of
  1,000 per day for `gemini-embedding-001` (about seven runs), which is also why the harness is
  deliberately outside CI — its numbers depend on the provider, the catalogue and the network.
- **The live feed reflects its sources** — Adzuna is read as the Indian market and is the largest
  share of the harvest, but it is still one aggregator's view of that market, and the two
  supplementary boards skew towards remote and European/North-American postings, so `/jobs/search` is
  a window onto *those* sources rather than a complete picture of hiring anywhere. The two collections
  must be re-ingested separately when the embedding space changes. The postings are shown as the
  boards published them: Adzuna's are truncated to 500 characters by its API, salaries are not
  normalised across currencies, and de-duplication goes exactly as far as title, company and place.
- **The live feed is refreshed by hand** — nothing in the app re-harvests on its own. It does now
  *report* the harvest date (`freshness` on `/jobs/search`, `job_postings` on `/health`) and warns
  past two weeks, and the migration takes `--if-stale N` so a scheduled run can be a cheap no-op —
  but the schedule itself is a deployment decision (a cron entry, a systemd timer, a Task Scheduler
  job; see SETUP §2.9), and on the default embedded Qdrant it can only run while the API is stopped,
  because that index directory is locked by whichever process has it open. Until a schedule exists,
  the honest thing the app does is *say* the feed is old instead of implying it is current. The
  freshness sidecar is local-only, like the embedding-space one: a `QDRANT_URL` deployment that
  shares no volume with the ingest reports the date as "not recorded".
- **Job filters read the boards' own wording** — location, arrangement and experience are real
  payload filters now, applied to the whole `job_role` collection rather than to the 50 postings a
  search ranked, but they are only as good as what the boards publish. Most postings carry no
  `seniority`, so the experience buckets lean on the title and contract wording; a false remote flag
  means "not stated", not "office-based"; and location is matched as a word, so a candidate who types
  a city the boards spell differently gets nothing. The per-role **live openings** list is unchanged:
  it is the handful of postings closest to one role, not that role's total market.
- **Per-role openings are ranked, not curated** — `POST /jobs/for-role` orders postings by cosine
  similarity to the role document plus the questionnaire; a posting ranking first is a similarity
  result, not a claim that the candidate is qualified for it.
- **Classification covers what has actually been read, and a card says which** — the classifier reads
  one advert per request, on demand, so its verdicts cover a small share of the feed; `/jobs/search`
  reports `classified` alongside `matched` (a search can be "61 matching of 1,690 classified") instead
  of implying the whole feed was read, and that is also why the Jobs page shows the reading *on a
  card* rather than offering a category filter over it. Coverage grows as listings are classified
  (`scripts.classify_jobs` for the bulk,
  `POST /jobs/classify` for one at a time), and the store is shared, so it never has to be paid for
  twice. The model only reads what the payload kept — the description excerpt and the text that was
  embedded, and Adzuna truncates descriptions at 500 characters — so a terse advert legitimately
  comes back **Unclassified** rather than being padded out from its title. So does an advert that
  is perfectly clear but describes a job outside the declared families — a sales, marketing or
  support role — because the vocabulary is the app's scope rather than a guess at where those jobs
  "fit"; the model's own sentence says which of the two happened. A verdict under the 0.55
  confidence floor is deliberately pessimistic: it is stored as Unclassified and stays that way
  until something real changes (a different model, edited wording, or `--force`), because re-rolling
  for a friendlier answer is how a classifier starts inventing detail.
- **Application tracking needs an account, and is a tracker rather than a CRM** — saved jobs and their
  stages are per-user rows behind a bearer token, so the guest path (questionnaire, match, roadmap)
  cannot write them; the Jobs page says "Sign in to save" rather than offering a button that would
  `401`. Within it, each application carries one current stage and one note: there is no history per
  move, no reminders, no attachments, and no import or export, so it records where a search got to
  rather than replacing the spreadsheet a candidate may already keep.
- **Refresh tokens** — access tokens are long-lived for a demo; refresh-token rotation is future work.
- **The AI budget is per process** — the limiter is a counter in memory, so two uvicorn workers each
  allow the full limit, and every caller behind one address (a campus NAT, say) shares the guest
  allowance. It is enough to stop a single client draining the quota; a shared store would be the next
  step if the API ever ran behind more than one process. The limit is charged on the attempt, so a
  request that fails for an unrelated reason (a bad `role_id`) still costs the caller one —
  classification is the exception: it consults its store first, so a request it can answer for free
  is never charged at all.
- **Prompt scrubbing is defence in depth, not a guarantee** — flattening and label-capping remove the
  structure an injected instruction needs to read as a new section, but they cannot stop a model from
  being persuaded by a cleverly worded sentence inside a skill label. Sign-in is deliberately *not*
  required for AI features (guests can match and generate), so a real fix would mean either an account
  requirement or model-side guardrails.
- **Provenance covers saved roadmaps** — a guest's generated plan is never persisted, so the model and
  prompt version that produced it are not recorded anywhere. Sign in before generating if you want the
  plan (and its recipe) to outlive the tab.
- **The roadmap cache is per tab, not per user** — it lives in `sessionStorage` keyed by role, so signing
  out and into a different account in the same tab can still show the previous account's cached plan
  until it is regenerated. Scoping the cache by user is future work.
- **Theming** — a single polished light theme.

---

## 📄 License

MIT License — free to use, modify, and share.
