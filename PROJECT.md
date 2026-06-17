# NYC Data Job Market Tracker — Project Context

> This document is the single source of truth for the project. Paste it at the start of each Claude session to restore full context without re-explaining the stack.

---

## Project Overview

A production data pipeline and dashboard that tracks early-career data job postings in NYC. Built as a primary portfolio piece to demonstrate end-to-end data engineering skills and land an early-career data analyst / analytics engineer / data engineer role.

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
│   │   ├── 01_market_insights.py
│   │   ├── 02_job_explorer.py
│   │   └── 03_pipeline_health.py
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
- **Queries:** "Data Analyst in New York", "Analytics Engineer in New York", "Data Engineer in New York"
- **Parameters:** `date_posted=3days`, `job_requirements=under_3_years_experience,no_experience`
- **Pagination:** Cursor-based, max 6 pages per query
- **Credit budget:** 200 credits/month, ~10 runs/month → 6 pages × 3 queries = 180 credits max
- **Limitations:** No structured seniority field. Uses `is_explicitly_entry_level` boolean flag as proxy (regex on job title).
- **Known issue:** Same job can appear across multiple queries. Deduped in `fetch_all()` by `job_id` before writing to Snowflake.

### 2. TheirStack (REST API)
- **Type:** REST API
- **What it provides:** Tech-stack-focused job listings with structured metadata
- **Credit budget:** 200 credits/month on free tier. Credits charged per job returned, not per request — limit is the main budget lever.
- **Free sweep strategy:** Run `blur_company_data=True` first across all pages at zero credit cost to collect all matching job IDs. Deduplicate in memory using `(title, location, frozenset(technology_slugs))`. Then fetch full records only for new jobs.
- **High-water mark:** Uses `discovered_at_gte` from Snowflake on each run — queries for jobs discovered after the latest `INGESTED_AT` in `RAW.THEIRSTACK.SRC_POSTINGS` to avoid re-fetching already-ingested jobs.
- **Credit math:** 10 credits/query × 3 queries × 10 runs = 300 theoretical max, but each window won't saturate all three caps. In practice well under 200/month. Monitor via Pipeline Health page.
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

### Seniority Fields (added v2)
| Field | Type | Description |
|---|---|---|
| `listed_seniority` | STRING | Seniority as labeled by source. Populated for TheirStack and Built In. NULL for JSearch. Values: `entry_level`, `junior`, `mid_level`. |
| `is_explicitly_entry_level` | BOOLEAN | Title regex flag across all sources: `entry\|junior\|jr\.?\|new.?grad\|early.?career` |

### LLM Enrichment Fields
| Field | Type | Description |
|---|---|---|
| `inferred_seniority` | STRING | GPT-4o-mini inferred seniority from description |
| `role_archetype` | STRING | `data_analyst`, `data_engineer`, `analytics_engineer`, etc. |
| `work_focus` | STRING | Primary focus area |
| `is_title_inflated` | BOOLEAN | LLM flag for inflated title relative to actual role |
| `inflation_reasoning` | STRING | LLM explanation. ~85% null. |
| `tech_stack_required` | VARIANT | Array of required technologies |
| `tech_stack_preferred` | VARIANT | Array of preferred technologies |
| `paradigms_required` | VARIANT | Array of required paradigms |
| `paradigms_preferred` | VARIANT | Array of preferred paradigms |
| `degree_requirement` | STRING | `none`, `bachelors`, `masters`, etc. |
| `years_required_min` | FLOAT | Min years experience |
| `years_required_max` | FLOAT | Max years experience |
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

## Streamlit Dashboard

**Pages:**
1. **Home** — overview and project context
2. **Market Insights** — charts and EDA findings
3. **Job Explorer** — filterable grid + expandable detail panel
4. **Pipeline Health** — API credit tracking, run history

**Key patterns:**
- `＄` (unicode fullwidth U+FF04) used for salary display — avoids Streamlit LaTeX parsing of `$`
- `pending_clear` flag pattern for filter resets (can't clear widget state directly)
- Dynamic `df_key` incrementing to force dataframe widget re-render on filter change
- `date_posted` kept as datetime in display dataframe, formatted via `st.column_config.DateColumn` — ensures correct click-to-sort behavior
- All data loaded via `load_fct_job_postings()` with 1-hour cache

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

---

## Known Issues & In-Progress Items

### In Progress
- **Built In backfill** — `backfill_builtin_seniority.ipynb` is ready with checkpoint saved. IP needs to cool down before resuming. Run in batches of ~10 with 8–15s delays.
- **Similar Jobs false positive** — inactive Built In listings show seniority from "Similar Jobs" section instead of returning `not_found`. Need to scope trophy icon search to main job container only, exclude Similar Jobs section.

### Known Bugs / Quirks
- `JOB_ENRICHMENT` table has duplicate `job_id` rows — mitigated by dedup in `int_jobs_unioned.sql` enrichment CTE
- Built In seniority not in JSON-LD — extracted from HTML, fragile if page structure changes
- JSearch `job_requirements` filter (`under_3_years_experience`) doesn't reliably exclude senior roles — senior title regex in staging is the real filter
- API credit tracking (credits_used_this_run) may be slightly overstated when manual 
JSearch API calls are made between pipeline runs — diff-based calculation picks up all usage not just pipeline usage

---