# NYC Data Job Market Tracker — Project Context

> This document is the single source of truth for the project. Paste it at the start of each Claude session to restore full context without re-explaining the stack.

---

## Project Overview

A production data pipeline and dashboard that tracks early-career data job postings in NYC. Built as a primary portfolio piece to demonstrate end-to-end data engineering skills and land an early-career data analyst / analytics engineer / data engineer / data scientist role.

**Portfolio lens:** Every architectural decision should be explainable and defensible in an interview. Prefer clean, maintainable patterns over clever ones. Scope is deliberately controlled — shippable beats complete.

**Live dashboard:** Deployed on Streamlit Cloud.

---

## Repository Structure

```
nyc-data-job-market-tracker/
├── .github/
│   └── workflows/
│       └── pipeline.yml
├── enrichment/
│   ├── notebooks/
│   │   └── test_llm_enricher.ipynb
│   ├── prompts/
│   │   └── job_extraction.txt
│   ├── schemas/
│   │   └── enrichment_schema.py
│   ├── __init__.py
│   └── run_enrichment.py
├── infra/
│   ├── __init__.py
│   ├── snowflake_client.py
│   └── snowflake_setup.sql
├── ingestion/
│   ├── notebooks/
│   │   ├── cache/
│   │   └── *.ipynb
│   ├── __init__.py
│   ├── builtin_client.py
│   ├── jsearch_client.py
│   ├── theirstack_client.py
│   └── run_ingestion.py
├── presentation/
│   ├── .streamlit/
│   │   └── config.toml
│   ├── notebooks/
│   │   └── *.ipynb
│   ├── pages/
│   │   ├── 00_home.py
│   │   ├── 01_landscape.py
│   │   ├── 02_under_the_hood.py
│   │   ├── 03_job_explorer.py
│   │   └── 04_pipeline_health.py
│   ├── app.py
│   ├── data_loader.py
│   └── requirements.txt
├── transformation/
│   └── models/
│       ├── intermediate/
│       │   └── int_jobs_unioned.sql
│       ├── marts/
│       │   ├── _models.yml
│       │   └── fct_job_postings.sql
│       └── staging/
│           ├── _sources.yml
│           ├── stg_builtin.sql
│           ├── stg_jsearch.sql
│           └── stg_theirstack.sql
├── .gitignore
├── README.md
└── requirements.txt
├── PROJECT.md                    
└── .env                          
```

---

## Data Sources

### 1. JSearch (RapidAPI)
- **Type:** REST API
- **What it provides:** Broad job board aggregation (Indeed, LinkedIn, etc.)
- **Queries:** "Data Analyst in New York", "Analytics Engineer in New York", "Data Engineer in New York", "Data Scientist in New York"
- **Parameters:** `date_posted=3days`, `job_requirements=under_3_years_experience,no_experience`
- **Pagination:** Cursor-based, max 5 pages per query
- **Credit budget:** 200 credits/month, ~10 runs/month → 5 pages × 4 queries = 200 credits theoretical max. Real usage runs well under this since not every query hits the full page cap every run.
- **Limitations:** No structured seniority field. Uses `is_explicitly_entry_level` boolean flag as proxy (regex on job title).
- **Known issue:** Same job can appear across multiple queries. Deduped in `fetch_all()` by `job_id` before writing to Snowflake.

### 2. TheirStack (REST API)
- **Type:** REST API
- **What it provides:** Tech-stack-focused job listings with structured metadata
- **Credit budget:** 200 credits/month on free tier. Credits charged per job returned, not per request — limit is the main budget lever.
- **Free sweep strategy:** Run `blur_company_data=True` first across all pages at zero credit cost to collect all matching job IDs. Deduplicate in memory using `(title, location, frozenset(technology_slugs))`. Then fetch full records only for new jobs.
- **High-water mark:** Uses `discovered_at_gte` from Snowflake on each run — queries for jobs discovered after the latest `INGESTED_AT` in `RAW.THEIRSTACK.SRC_POSTINGS` to avoid re-fetching already-ingested jobs.
- **Credit math:** 10 credits/query × 4 queries × 10 runs = 400 theoretical max, but each window won't saturate all four caps. In practice well under 200/month. Monitor via Pipeline Health page.
- **Confirmed plan limits (API error E-020):** free-sweep pagination is capped at 5 pages total (page 5 — the 6th request — returns HTTP 403 with `"Your current plan allows to view up to 5 pages of results"`). Paid-fetch `limit` is capped at 25 results per request (`"Your current plan allows up to 25 results per page"`). The client enforces both: `_free_sweep` stops at `max_free_sweep_pages=5`, `_paid_fetch` batches requests at `PAID_FETCH_BATCH_SIZE=25`.
- **Notable:** Has native `seniority` field in payload (e.g. `mid_level`, `junior`). 100% fill rate.
- **Normalization:** `seniority` values lowercased and spaces replaced with underscores in staging (`REPLACE(LOWER(RAW_PAYLOAD:seniority::STRING), ' ', '_')`).

### 3. Built In NYC (Scraper)
- **Type:** Web scraper (BeautifulSoup)
- **What it provides:** NYC-specific curated job board, highest quality source, best salary data
- **URL pattern:** `https://www.builtinnyc.com/jobs/entry-level/junior/mid-level?search={term}&daysSinceUpdated=3`
- **Two-stage scrape:** Crawl index pages (JSON-LD ItemList) → scrape individual job pages (JSON-LD JobPosting)
- **Seniority:** Not in JSON-LD. Extracted from HTML by anchoring on `fa-trophy` icon wrapper div, then grabbing sibling span. Known values: `Entry level`, `Junior`, `Mid level`. Normalized to snake_case in staging.
- **Rate limiting:** Cloudflare bot detection. Soft blocks after ~22 requests in a session. DO NOT use `Accept-Encoding` header — causes compressed responses that look like bot challenge pages. Use plain `requests.get()` (not session) for job pages.

---

## Pipeline Schedule

GitHub Actions cron: **Monday and Thursday** (approximately every 3 days).

Each run:
1. Fetch from all 3 sources
2. Write raw payloads to Snowflake RAW tables
3. Run GPT-4o-mini enrichment on unenriched rows
4. Run `dbt run --target prod` to rebuild mart tables
5. Log run metadata to `RAW.PIPELINE.RUNS` and `RAW.PIPELINE.API_USAGE`

---

## Snowflake Architecture

### Databases & Schemas

| Database | Schema | Tables | Purpose |
|---|---|---|---|
| `RAW` | `JSEARCH` | `SRC_POSTINGS` | Raw JSearch payloads |
| `RAW` | `THEIRSTACK` | `SRC_POSTINGS` | Raw TheirStack payloads |
| `RAW` | `BUILTIN` | `SRC_POSTINGS` | Raw Built In payloads |
| `RAW` | `PIPELINE` | `RUNS`, `API_USAGE` | Pipeline metadata |
| `ENRICHED` | `PUBLIC` | `JOB_ENRICHMENT` | GPT-4o-mini enrichment output |
| `ANALYTICS_DEV` | `PUBLIC` | `FCT_JOB_POSTINGS` | Dev mart (dbt dev target) |
| `ANALYTICS_PROD` | `PUBLIC` | `FCT_JOB_POSTINGS` | Prod mart (dbt prod target) |

### Raw Table Schema
All three `SRC_POSTINGS` tables have the same 3-column structure:
```
SOURCE       VARCHAR    -- e.g. "jsearch:Data Analyst", "builtin:data-analyst", "theirstack:data-engineer"
RAW_PAYLOAD  VARIANT    -- complete raw API/scrape payload, untouched
INGESTED_AT  TIMESTAMP_TZ
```

---

## dbt Transformation Layer

**Profile:** `nyc_job_tracker`
**Run locally from:** `transformation/` directory
**Commands:** `dbt run` (dev), `dbt run --target prod` (prod), `dbt test`

### Materialization Strategy
- `staging` → **view**
- `intermediate` → **ephemeral**
- `marts` → **table**

### Staging Models
Each staging model follows this CTE pattern:
`source` → `extracted` → `deduped` → `filtered` → `select`

**Dedup pattern (all three staging models):**
```sql
qualify ROW_NUMBER() over (
    partition by job_id
    order by ingested_at desc, ingestion_query desc  -- tiebreaker prevents non-deterministic dedup
) = 1
```

**Senior title filter (all three staging models):**
```sql
and not REGEXP_LIKE(
    LOWER(job_title),
    '.*(senior|sr\.?|lead|principal|staff|manager|director|vp|vice president|avp|head of|architect|chief|svp|evp|gvp|president|officer|executive|leader).*'
)
```

### Intermediate: `int_jobs_unioned.sql`
- Unions all three staging models
- Cross-source dedup by `LOWER(TRIM(job_title)) || ' | ' || LOWER(TRIM(company_name))`, preferring builtin > theirstack > jsearch
- Left joins enrichment (with dedup: `qualify ROW_NUMBER() over (partition by job_id order by enriched_at desc) = 1`)
- Filters out `software_engineer` role archetype

### Mart: `fct_job_postings.sql`
Final select from `int_jobs_unioned`. No additional logic.

---

## Final Mart Fields

### Core Fields
| Field | Type | Description |
|---|---|---|
| `job_id` | STRING | Source API identifier |
| `source` | STRING | `jsearch`, `theirstack`, or `builtin` |
| `ingestion_query` | STRING | Query label that produced this row |
| `job_title` | STRING | Title as posted |
| `company_name` | STRING | Hiring company |
| `job_url` | STRING | Direct link to posting |
| `date_posted` | DATE | Posting date |
| `description` | STRING | Full job description (HTML stripped for Built In) |
| `city` | STRING | |
| `state` | STRING | |
| `country` | STRING | |
| `latitude` | FLOAT | |
| `longitude` | FLOAT | |
| `work_model` | STRING | `remote`, `hybrid`, `onsite` |
| `employment_type` | STRING | `full_time`, `part_time`, `contract`, `other` |
| `final_salary_min` | FLOAT | Prefers structured value, falls back to LLM |
| `final_salary_max` | FLOAT | Prefers structured value, falls back to LLM |

### Seniority Fields (redesigned v3, June 2026)
| Field | Type | Description |
|---|---|---|
| `listed_seniority` | STRING | Seniority as labeled by source. Populated for TheirStack and Built In. NULL for JSearch. Values: `entry_level`, `junior`, `mid_level`. Flawed by design — TheirStack's own API has no `entry_level` tier, so its `junior` value is structurally ambiguous between true entry-level and junior. Left as-is; the imperfection is itself part of what's being investigated. |
| `early_career_tier` | STRING | **Computed in `int_jobs_unioned.sql`** — collapses `listed_seniority`'s `entry_level` + `junior` into `entry_or_junior`, alongside `mid` (from `mid_level`). Scoped to `builtin`/`theirstack` only — `jsearch` is NULL, since it has no structured seniority field. A `years_required_min` cutoff was tested as a substitute for JSearch and rejected: `junior` (0–3 yrs) and `mid_level` (0–10 yrs) overlap too heavily to support a clean cutoff — itself a finding, not just a null result. Replaces the old runtime-computed `effective_seniority` (removed). |

`is_explicitly_entry_level` was removed — it was a title-regex proxy for "no experience required," made redundant once `years_required_min` (already extracted by the LLM) answers the same question more directly.

### Role Classification Field
| Field | Type | Description |
|---|---|---|
| `title_role_bucket` | STRING | **Computed in `int_jobs_unioned.sql`** — regex classification of `job_title` into one of four target roles (Data Analyst, Data Engineer, Analytics Engineer, Data Scientist). Distinct from `ingestion_query` (which search term surfaced the posting — found to mislabel ~36% of Analytics Engineer postings as Data Engineer due to JSearch's loose topical matching) and `role_archetype` (LLM-inferred from the full description). `title_role_bucket` answers only "what does this posting's title literally claim to be." Value is `no_match` when the title doesn't cleanly map to any of the four roles; these rows remain in the mart (visible on Pipeline Health) rather than being filtered out. Regex uses chained `ILIKE` wildcards (`%data%engineer%`, `%data%analyst%`, etc.) rather than word-boundary-anchored patterns, to catch compound titles ("Data Quality Analyst," "Data Migration Engineer") — validated against the full dataset with zero false positives at time of writing, though the looseness is a known theoretical risk (e.g. matched "Databricks" via the substring "data" + later "Engineer," correctly by coincidence rather than design).

### LLM Enrichment Fields
| Field | Type | Description |
|---|---|---|
| `inferred_seniority` | STRING | GPT-4o-mini inferred seniority from description. 4-tier scale as of June 2026: `entry` (0 yrs), `junior` (1–2 yrs), `mid` (3–5 yrs), `senior` (5+ yrs) — anchored to the minimum of any stated range. Previously 3-tier (entry/mid/senior only). |
| `role_archetype` | STRING | `data_analyst`, `data_engineer`, `analytics_engineer`, etc. |
| `work_focus` | STRING | Primary focus area |
| `tech_stack_required` | VARIANT | Array of required technologies |
| `tech_stack_preferred` | VARIANT | Array of preferred technologies |
| `paradigms_required` | VARIANT | Array of required paradigms |
| `paradigms_preferred` | VARIANT | Array of preferred paradigms |
| `degree_requirement` | STRING | `none`, `bachelors`, `masters`, `equivalent_ok` |
| `years_required_min` | FLOAT | Min years experience |
| `years_required_max` | FLOAT | Max years experience |
| `explicitly_encourages_applicants` | BOOLEAN | LLM flag — posting explicitly invites candidates who don't meet all requirements to apply anyway. Prompt tightened June 2026 with explicit EEO-boilerplate exclusions; true rate dropped from ~25% to ~8%. See Known Issues for residual false-positive rate. |
| `acknowledges_ai` | BOOLEAN | Whether posting explicitly mentions AI, LLMs, or related tools |
| `confidence_score` | FLOAT | LLM self-reported confidence (0–1) |
| `enriched_at` | TIMESTAMP | When enrichment was written |
| `ingested_at` | TIMESTAMP | When raw payload was written |

---

## Snowflake Query Pattern

**Always use manual cursor. Never use `fetch_pandas_all()` — it breaks in this environment.**

```python
def run_query(sql: str) -> pd.DataFrame:
    cur = conn.cursor()
    cur.execute(sql)
    rows = cur.fetchall()
    cols = [desc[0] for desc in cur.description]
    cur.close()
    return pd.DataFrame(rows, columns=cols)
```

**Updating a VARIANT field in Snowflake:**
```sql
UPDATE RAW.BUILTIN.SRC_POSTINGS
SET RAW_PAYLOAD = OBJECT_INSERT(RAW_PAYLOAD, 'seniority', 'mid_level', true)
WHERE RAW_PAYLOAD:source_url::STRING = '<url>'
```

---

## Jupyter Notebook Conventions

- Notebooks live in `ingestion/notebooks/`
- Each notebook defines its own `conn` and `run_query` using the same manual cursor pattern
- Cache files (`cache/*.json`) are gitignored — used for Built In crawl/scrape results to avoid re-hitting the site during development
- Backfill notebooks are one-off — run manually, not via cron

---

## Refreshing the Portfolio Write-up

The "Early Signals" section of the external portfolio write-up (not tracked in this repo — lives on the personal site, pasted in by hand) is built from stats computed against `FCT_JOB_POSTINGS`. Since the pipeline keeps accumulating postings, those numbers go stale and need periodic refreshing.

- `presentation/notebooks/findings_lib.py` — shared functions (one per stat: role/source breakdown, salary by role, title-vs-archetype self-consistency, AI acknowledgment, degree requirements, listed-vs-inferred seniority mismatch, etc.). Single source of truth used by both the notebook and the snapshot script below.
- `presentation/notebooks/findings.ipynb` — the interactive/exploratory notebook, now calling into `findings_lib` per cell. This is where to poke at anything unexpected before it becomes a headline number.
- `presentation/notebooks/generate_findings_snapshot.py` — run this to refresh: computes the headline metrics the write-up actually cites, writes a dated JSON snapshot to `presentation/notebooks/findings_snapshots/`, and prints a diff against the most recent prior snapshot so it's obvious what actually moved since the write-up was last updated. These snapshot JSONs are deliberately carved out of the blanket `*.json` gitignore rule (see `.gitignore`) so history is preserved.
- `/refresh-findings` (`.claude/commands/refresh-findings.md`) — the on-demand trigger: runs the snapshot script, reads the new numbers + diff, and drafts specific edits to the write-up's prose (pasted into the chat) reflecting what changed.

---

## Streamlit Dashboard

**Pages:**
1. **Home** (`00_home.py`) — framing, the question, the four roles, how the data is collected
2. **The Landscape** (`01_landscape.py`) — volume, frequency over time, work model, seniority distribution (% share), salary by role type, experience requirements, degree requirements
3. **Under the Hood** (`02_under_the_hood.py`) — tech stack and paradigm heatmaps, listed title vs. LLM archetype confusion matrix, listed vs. LLM-inferred seniority confusion matrix, the AI blind spot, industry domain breakdown (top 10 + role composition)
4. **Job Explorer** (`03_job_explorer.py`) — filterable grid + expandable detail panel
5. **Pipeline Health** (`04_pipeline_health.py`) — API credit tracking, run history, title classification health, search query reliability

**Page organizing principle:** Landscape covers baseline facts about a posting (what it is, who wants it, what it pays, what it takes to qualify). Under the Hood covers content and divergence — what's actually inside a posting, and where it diverges from what it claims to be (skills, methods, title-vs-reality, AI signal, industry concentration).

**Role grouping:** All role-grouped charts use `title_role_bucket` (regex-classified from `job_title`), not `ingestion_query` (which search term surfaced the posting). `ingestion_query` was found to mislabel ~36% of Analytics Engineer postings as Data Engineer due to JSearch's loose topical search matching — see Known Issues. `ingestion_query` is retained only on the Pipeline Health page, specifically to measure this search-reliability gap. Charts exclude `title_role_bucket = 'no_match'` rows (titles that didn't cleanly map to one of the four target roles); these rows remain in the mart and are visible on Pipeline Health.

**Key patterns:**
- `＄` (unicode fullwidth U+FF04) used for salary display — avoids Streamlit LaTeX parsing of `$`
- `pending_clear` flag pattern for filter resets (can't clear widget state directly)
- Dynamic `df_key` incrementing to force dataframe widget re-render on filter change
- `date_posted` kept as datetime in display dataframe, formatted via `st.column_config.DateColumn` — ensures correct click-to-sort behavior
- All data loaded via `load_fct_job_postings()` with 1-hour cache
- `early_career_tier` and `title_role_bucket` both computed in the dbt mart (`int_jobs_unioned.sql`) — derived fields live in the transformation layer, not at runtime in `data_loader.py`
- Stacked % share charts (seniority, degree, work model) call `.fillna(0)` on the percentage column after `reindex()` — a role with zero postings in a given category produces a `NaN`, not a `0`, after reindexing, which breaks Plotly's stack height in `barmode="stack"` and silently truncates the bar below 100%
- `format_seniority()` and `format_label()` (in `data_loader.py`) are the shared display-formatting functions — `format_seniority()` normalizes `listed_seniority`'s vocabulary (`entry_level`, `mid_level`, etc.) and `inferred_seniority`'s vocabulary (`entry`, `mid`, etc.) to the same display labels; `format_label()` handles generic snake_case → Title Case for everything else
- Job Explorer's "Date Posted" filter is a quick-preset radio (`All Time` / `Past 3 Days` / `Past Week` / `Past Month`), not a custom date range picker — sets the same underlying `date_range` filter logic, just via a fixed set of presets rather than open-ended input

---

## Hard-Won Technical Constraints

These are non-obvious rules that must be followed. Suggesting alternatives to these will break things.

| Constraint | Why |
|---|---|
| No `fetch_pandas_all()` | Breaks in this Snowflake connector environment |
| No `Accept-Encoding` header for Built In | Server returns compressed response that `requests` doesn't decompress — looks like a bot challenge page (~16k html_len vs ~88k for real page) |
| Plain `requests.get()` for Built In job pages | Session-based requests get flagged faster by Cloudflare |
| Built In crawl index pages can use session | Lower risk, works fine |
| Built In scrape delays: 4–8s minimum | Cloudflare soft-blocks after ~22 requests in a session |
| `＄` not `$` in Streamlit salary display | `$` triggers LaTeX rendering |
| `OBJECT_INSERT(..., true)` for VARIANT updates | The 4th arg `true` = upsert behavior |
| Enrichment table must be deduped before join | `JOB_ENRICHMENT` has duplicate `job_id` rows — left join fans out without dedup |

---

## Validation & Investigations

### LLM Salary Coverage Contribution (June 2026)
To measure how much the LLM enrichment layer actually contributes to salary coverage,
we compare structured salary coverage (from source payloads only) against final salary
coverage (post-COALESCE with LLM fallback) in the mart.

**Structured coverage** — union all three staging views in Snowflake UI:
```sql
SELECT
    COUNT(*)                                                AS total,
    COUNT(salary_min)                                       AS structured_coverage,
    ROUND(COUNT(salary_min) / COUNT(*)::FLOAT * 100, 1)    AS structured_pct
FROM (
    SELECT salary_min FROM ANALYTICS_PROD.PUBLIC.STG_JSEARCH
    UNION ALL
    SELECT salary_min FROM ANALYTICS_PROD.PUBLIC.STG_THEIRSTACK
    UNION ALL
    SELECT salary_min FROM ANALYTICS_PROD.PUBLIC.STG_BUILTIN
)
```

**Final coverage** — query the mart:
```sql
SELECT
    COUNT(*)                                                        AS total,
    COUNT(final_salary_min)                                         AS final_coverage,
    ROUND(COUNT(final_salary_min) / COUNT(*)::FLOAT * 100, 1)      AS final_pct
FROM ANALYTICS_PROD.PUBLIC.FCT_JOB_POSTINGS
```

**Result (June 2026, n=229):** structured coverage was 28.8% (66/229).
Final coverage after LLM enrichment was 59.5% (125/210). The LLM contributed roughly 30
percentage points of salary coverage — validating the resume bullet and justifying
keeping `salary_min`/`salary_max` in the enrichment prompt.

### Title Role Bucket — methodology correction (June 2026)
Original analysis used `ingestion_query` (the search term that surfaced a posting) as the "listed role" axis for comparing against LLM-inferred `role_archetype`. Investigating an obviously-mislabeled row (a "Data Analyst II" posting ingested under the Data Scientist query) led to measuring the actual reliability of `ingestion_query` as a role label, via a regex-bucketed comparison against the literal `job_title`.

**Finding:** Data Scientist (98%), Data Engineer (87%), and Data Analyst (77%, mostly explained by generic non-matching titles rather than true mislabeling) queries were reliable. **Analytics Engineer was only 47% reliable** — 36% of postings ingested under the "Analytics Engineer" query were titled "Data Engineer." This is a JSearch-specific search-recall problem (the underlying aggregator doesn't strictly gate results by query term), not a finding about how employers use the two titles.

**Fix:** added `title_role_bucket`, a regex classification of `job_title` (see Role Classification Field above), as the canonical "listed role" axis everywhere except Pipeline Health, where `ingestion_query` is retained specifically to keep measuring this search-reliability gap.

**Downstream effect:** re-running the title-vs-archetype agreement rate using `title_role_bucket` instead of `ingestion_query` raised overall agreement from a number consistent with the original ~44% AE self-consistency finding to **98%** (370 of 377 enriched postings). This significantly softens the project's original "roles are blurry" framing — once search-recall noise is removed, listed titles and LLM-inferred content agree the large majority of the time. The README's framing was updated accordingly to present this as a tested assumption rather than an asserted fact.

### Fuzzy Duplicate Detection (June 2026)
Exact-match cross-source dedup (`int_jobs_unioned.sql`) catches identical `title + company` strings but misses near-duplicates: legal suffixes ("Morgan & Morgan" vs. "Morgan & Morgan, P.A."), spacing/casing variants ("candidhealth" vs. "Candid Health"), or the same listing scraped twice with drifted metadata. Confirmed via manual review of two cases (Anthropic, Spotify) where `work_model` differed between duplicate rows but the full job description was identical — `work_model` is unreliable across re-scrapes of the same posting, not evidence of two distinct roles.

Investigated via a diagnostic self-join and found ~7 pairs out of ~370 postings (under 2%). Given the small scale, deliberately implemented as a **Snowflake view**, not automated dbt logic — tuned edit-distance thresholds, a tiebreak cascade, and edge cases (pairwise matching doesn't catch 3-way duplicate chains) were judged disproportionate complexity for a problem affecting a small, stable fraction of the data.

**`vw_fuzzy_duplicate_candidates`** — self-joins `fct_job_postings`, flagging pairs where title differs by ≤15% of its own length, company by ≤35% (both via `EDITDISTANCE()` normalized by string length — a flat distance ceiling let through false positives like two unrelated "Data Analyst" postings at different companies, since edit distance alone doesn't account for string length), and dates are within 3 days. Computes `loser_job_id` per pair via cascade: prefer the row with salary populated → prefer source priority (`builtin > theirstack > jsearch`) → deterministic fallback.

**Usage:** run `SELECT * FROM vw_fuzzy_duplicate_candidates` every few pipeline runs, manually review each pair (pull full descriptions for anything ambiguous — `work_model` mismatches are not sufficient evidence of distinct roles), then delete confirmed duplicates via an explicit, hand-typed `job_id` list. Deliberately not an automated delete straight off `loser_job_id`, to keep human review as the actual checkpoint.

---

## Known Issues & In-Progress Items

### Known Bugs / Quirks
- `JOB_ENRICHMENT` table has duplicate `job_id` rows — mitigated by dedup in `int_jobs_unioned.sql` enrichment CTE
- Built In seniority not in JSON-LD — extracted from HTML, fragile if page structure changes
- JSearch `job_requirements` filter (`under_3_years_experience`) doesn't reliably exclude senior roles — senior title regex in staging is the real filter
- API credit tracking (`credits_used_this_run`) may be slightly overstated when manual JSearch API calls are made between pipeline runs — diff-based calculation picks up all usage not just pipeline usage
- ~~Job Explorer filter reset bug~~ — **Resolved June 2026.** Root cause: the dataframe selection widget's re-render key was tied to filtered row *count*, not row *contents* — two different filtered sets with the same row count would incorrectly reuse the same widget state. Fixed by keying off a hash of the actual filtered `job_id`s instead.
- **`explicitly_encourages_applicants` has a residual false-positive rate** — the enrichment prompt explicitly excludes EEO/equal-opportunity boilerplate ("all qualified individuals are encouraged to apply") and generic enthusiasm language ("if you're passionate about this role, apply") with verbatim true/false examples, but GPT-4o-mini does not reliably apply these exclusions 100% of the time — confirmed by getting the model to state reasoning that directly contradicted its own explicit instructions on an example matching a listed false case almost word for word. In a manual spot-check of all postings flagged true after the prompt fix, 2 of 24 were still judged incorrect. Also observed run-to-run inconsistency on at least one borderline posting at `temperature=0`, indicating some inherent non-determinism beyond the exclusion-following issue. Not worth further prompt iteration — field is not used in any current dashboard page or write-up finding. If this field becomes load-bearing for analysis later, revisit with either a stronger model (GPT-4o) for this field specifically, or a two-step extract-then-classify approach (extract the literal evidence sentence first, then classify it in a separate pass).

### Backlog

---