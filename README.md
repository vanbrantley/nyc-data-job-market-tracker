# NYC Data Job Market Tracker

A production data pipeline that tracks early-career data job postings in New York City twice a week — ingesting raw listings from three sources, enriching each one with a structured LLM pass, transforming with dbt, and surfacing insights through a live Streamlit dashboard.

**→ [View the Live Dashboard](https://nyc-data-job-market-tracker.streamlit.app)**

---

## What It Does

The NYC job market for data roles is noisy. Job titles are inflated, seniority labels are inconsistent, and raw postings bury the signal in walls of boilerplate. The lines between role types — particularly Analytics Engineer and Data Engineer — are often assumed to be blurry, with postings seemingly describing similar work under different names.

This pipeline cuts through that: it collects every relevant entry- and mid-level posting it can find, then sends each description through an LLM to extract structured, comparable metadata — actual tech stack, inferred seniority, role archetype, and AI awareness — and compares that against the posting's own title to see where the two actually agree or diverge. The result complicates the original assumption: once title-vs-content agreement is measured directly, the four roles turn out to be far more distinct in practice than their reputation for overlap suggests.

Targets four role archetypes across all postings: **Data Analyst**, **Analytics Engineer**, **Data Engineer**, and **Data Scientist**.

---

## Pipeline Architecture

```
INGESTION  (GitHub Actions cron — every Monday & Thursday)
├── JSearch (RapidAPI)       → cursor-paginated search, N queries × 6 pages
├── TheirStack               → two-stage free-sweep → paid-fetch (credit-budgeted)
└── Built In NYC             → two-stage crawl → scrape (BeautifulSoup, JSON-LD)
                                          ↓
SNOWFLAKE RAW               (strict ELT — VARIANT columns, no transformation at ingest)
    RAW.JSEARCH.SRC_POSTINGS
    RAW.THEIRSTACK.SRC_POSTINGS
    RAW.BUILTIN.SRC_POSTINGS
                                          ↓
ENRICHMENT                  (GPT-4o-mini, runs sequentially post-ingest)
    Pulls unenriched rows from all three raw tables
    Extracts: role_archetype · work_focus · tech_stack (required/preferred)
          paradigms · degree_requirement · salary · inferred_seniority (4-tier)
          acknowledges_ai · explicitly_encourages_applicants
    Validates with Pydantic before writing
    → ENRICHED.PUBLIC.JOB_ENRICHMENT
                                          ↓
dbt TRANSFORMATION          (runs after enrichment in same GitHub Actions job)
    staging/     → stg_jsearch, stg_theirstack, stg_builtin (views)
                    field extraction, type casting, HTML stripping, dedup within source
    intermediate/ → int_jobs_unioned (ephemeral)
                    UNION ALL, cross-source dedup by (title, company), enrichment join,
                    title_role_bucket classification (regex on job_title)
    marts/        → fct_job_postings (table)
                    final wide table powering the dashboard
                                          ↓
PRESENTATION                (Streamlit — live dashboard)
    Home · The Landscape · Under the Hood · Job Explorer · Pipeline Health
```

---

## Tech Stack

| Layer | Tools |
|---|---|
| Ingestion | Python, Requests, BeautifulSoup |
| Storage | Snowflake (VARIANT columns, schema-on-read) |
| Enrichment | OpenAI GPT-4o-mini, Pydantic |
| Transformation | dbt-core, dbt-snowflake |
| Orchestration | GitHub Actions (cron) |
| Dashboard | Streamlit, Plotly |

---

## Key Technical Decisions

### ELT over ETL — raw JSON stored as VARIANT
Every ingestion client writes three fields to Snowflake: `SOURCE`, `RAW_PAYLOAD` (the full raw JSON dict, untouched), and `INGESTED_AT`. No transformation happens at ingest time. dbt handles all field extraction downstream via Snowflake's dot-notation semi-structured access (`RAW_PAYLOAD:job_title::STRING`). This means ingestion bugs never corrupt data — the raw truth is always preserved and replayable.

### Credit-budgeted TheirStack two-stage architecture
TheirStack charges per job returned. To avoid burning the monthly credit budget on duplicates, the client runs a **free sweep** first — paginating through all matching jobs with `blur_company_data=True` (zero cost) to collect IDs. It then **deduplicates in memory** using a `(job_title, location, frozenset(technology_slugs))` fingerprint, then fetches only the top `N` unique IDs via the paid endpoint. Each role archetype gets its own cap so no single category crowds out the others.

### Cross-source deduplication at two layers
The same job posting often appears on multiple boards. Deduplication runs at two layers:
1. **Within-source** (staging models): `ROW_NUMBER() OVER (PARTITION BY job_id ORDER BY ingested_at DESC) = 1` — handles the same posting re-ingested across multiple runs.
2. **Cross-source** (intermediate model): `ROW_NUMBER() OVER (PARTITION BY LOWER(title) || ' | ' || LOWER(company))` — handles the same job appearing on JSearch, TheirStack, and Built In simultaneously. Source priority is `builtin > theirstack > jsearch` since Built In provides the richest structured payload.

### LLM enrichment with structured output + Pydantic validation
The enrichment pipeline sends each job title + description to GPT-4o-mini with a strict system prompt that requests a JSON object conforming to a predefined schema. The response is immediately validated through a Pydantic model (`JobEnrichmentSchema`) before writing — if validation fails, the row is retried up to 3 times before being skipped. Temperature is set to 0 for reproducibility. Fields extracted include: `role_archetype`, `work_focus`, `inferred_seniority`, `title_seniority_signal`, `tech_stack_required/preferred`, `paradigms_required/preferred`, `degree_requirement`, `years_required_min/max`, `acknowledges_ai`, `explicitly_encourages_applicants`, and `salary_min/max`.

### Listed title vs. LLM-assigned archetype
Every posting carries two independent labels for "what role is this": `title_role_bucket` (classified directly from the job title via regex) and `role_archetype` (what the LLM determined the role actually is, based on the full description). Comparing the two — rather than collapsing them into one — is what surfaces title inflation and role convergence. Note this is distinct from `ingestion_query` (the search term that originally surfaced the posting), which was found to mislabel a meaningful share of Analytics Engineer postings as Data Engineer due to one source's loose topical search matching — `ingestion_query` is retained for that specific reliability check, but isn't used as a role label anywhere in the analysis. This comparison is the core analytical mechanism behind the Under the Hood dashboard page.

### Early-career tier — a deliberately narrower seniority field
Only TheirStack and Built In provide a structured `listed_seniority` field; JSearch does not. Rather than backfill JSearch with a weaker proxy, `early_career_tier` is scoped to just the two sources that self-report seniority, collapsing `entry_level` + `junior` into one tier (since TheirStack's own API can't distinguish them) alongside `mid`. A `years_required_min` cutoff was tested as a JSearch substitute and rejected — junior and mid-level postings overlap too heavily in stated experience requirements to support a clean threshold. Computed directly in the dbt mart (`int_jobs_unioned.sql`), not at dashboard runtime.

### Salary: structured payload takes precedence over LLM estimate
Not all sources include structured salary fields. The mart model uses `COALESCE(structured_salary, llm_extracted_salary)` — structured payload values (from JSearch and Built In JSON-LD) are trusted first; LLM-extracted salary from description text fills gaps. This is surfaced as `final_salary_min` / `final_salary_max` in the fact table. Validation against structured-only coverage showed the LLM layer contributes roughly 30 percentage points of additional salary coverage.

### dbt materialization strategy
- **Staging models** → Views: no storage cost, always fresh off RAW
- **Intermediate models** → Ephemeral: compile-time CTEs, no intermediate Snowflake tables
- **Mart models** → Tables: the dashboard queries `fct_job_postings` as a physical table for fast cold-start reads

### Failure isolation
Each ingestion source runs independently. A failure in one source logs the error and lets the others continue. The pipeline exits with code 1 if any source fails (so GitHub Actions fires a notification), but a partial run still writes whatever data it collected. The enrichment step is similarly tolerant — individual job failures are logged and skipped without aborting the batch.

### API usage tracking
After each run, credit balance and usage stats for JSearch (from rate-limit response headers) and TheirStack (from their billing endpoint) are written to a `PIPELINE_API_USAGE` table in Snowflake. The Pipeline Health dashboard page reads this to show per-run burn rate, remaining credits with a health indicator, and a running forecast of how many runs remain before the monthly limit.

---

## Dashboard Pages

**Home** — The framing for the investigation: why this project exists, the four role types under examination, and how the data is collected.

**The Landscape** — What does the market look like right now? Posting volume by role type, cumulative frequency over time, work model split, seniority distribution, salary by role type, and experience/degree requirements broken out by role.

**Under the Hood** — What are these roles actually asking for? Tech stack and paradigm overlap heatmaps across role types, a confusion matrix comparing listed title against LLM-assigned archetype, a second confusion matrix comparing listed against LLM-inferred seniority, AI acknowledgment rate by role, and industry domain breakdown.

**Job Explorer** — Every posting, filterable by tech stack, role archetype, work model, employment type, source, degree requirement, salary range, and date posted. Selecting any row opens a detail panel showing the full LLM enrichment alongside the raw job description — the exact text the model extracted from, so you can validate the extraction.

**Pipeline Health** — Internal mechanics: ingestion cadence by source over time, LLM enrichment field fill rates, confidence score distribution, per-source health metrics, title classification health, search query reliability, API credit usage per run with a forecast, and a run history table with duration and jobs-per-credit efficiency.

---

## Repository Structure

```
nyc-data-job-market-tracker/
├── ingestion/
│   ├── jsearch_client.py       # JSearch API client — cursor pagination, retry/backoff
│   ├── theirstack_client.py    # TheirStack client — free sweep + paid fetch
│   ├── builtin_client.py       # Built In NYC scraper — crawl + scrape, JSON-LD extraction
│   └── run_ingestion.py        # Orchestrator — runs all sources, loads to Snowflake
├── enrichment/
│   ├── run_enrichment.py       # LLM enrichment pipeline
│   ├── prompts/job_extraction.txt   # System prompt
│   └── schemas/enrichment_schema.py # Pydantic validation schema
├── transformation/
│   └── models/
│       ├── staging/            # stg_jsearch, stg_theirstack, stg_builtin (views)
│       ├── intermediate/       # int_jobs_unioned (ephemeral)
│       └── marts/              # fct_job_postings (table)
├── presentation/
│   ├── app.py                  # Streamlit entry point
│   ├── data_loader.py          # Snowflake → DataFrame loader
│   └── pages/
│       ├── 00_home.py
│       ├── 01_landscape.py
│       ├── 02_under_the_hood.py
│       ├── 02_job_explorer.py
│       └── 04_pipeline_health.py
├── infra/
│   ├── snowflake_client.py     # SnowflakeLoader — routes rows to RAW tables
│   └── snowflake_setup.sql
└── .github/workflows/pipeline.yml   # GitHub Actions cron (Mon + Thu, 10am UTC)
```

---

## Running Locally

### Prerequisites

- Python 3.11+
- A Snowflake account with the RAW / ENRICHED / ANALYTICS_PROD databases set up
- API keys: RapidAPI (JSearch), TheirStack, OpenAI
- dbt-snowflake installed

### Setup

```bash
git clone https://github.com/vanbrantley/nyc-data-job-market-tracker
cd nyc-data-job-market-tracker
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file in the root:

```env
# Ingestion
RAPIDAPI_KEY=your_rapidapi_key
THEIRSTACK_KEY=your_theirstack_key

# Snowflake (shared across all steps)
SNOWFLAKE_ACCOUNT=your_account
SNOWFLAKE_USER=your_user
SNOWFLAKE_PASSWORD=your_password
SNOWFLAKE_ROLE=your_role
SNOWFLAKE_WAREHOUSE=your_warehouse
SNOWFLAKE_DATABASE=RAW

# Enrichment
OPENAI_KEY=your_openai_key
```

### Run the Pipeline

```bash
# Step 1: Ingest from all three sources → Snowflake RAW
python ingestion/run_ingestion.py

# Step 2: Enrich unenriched jobs with GPT-4o-mini
python enrichment/run_enrichment.py

# Step 3: Run dbt models (staging → intermediate → mart)
cd transformation
dbt run
dbt test
cd ..

# Step 4: Launch the dashboard
cd presentation
streamlit run app.py
```

### dbt profiles.yml

Create `~/.dbt/profiles.yml`:

```yaml
nyc_job_tracker:
  target: prod
  outputs:
    prod:
      type: snowflake
      account: your_account
      user: your_user
      password: your_password
      role: your_role
      warehouse: your_warehouse
      database: ANALYTICS_PROD
      schema: public
      threads: 4
```

---

## Automated Runs

The full pipeline (ingest → enrich → dbt run → dbt test) runs automatically via GitHub Actions every Monday and Thursday at 10am UTC. Secrets are stored as GitHub Actions repository secrets. A failure in any step fires a GitHub Actions notification but does not prevent subsequent steps from attempting to run — so a partial ingest still gets enriched and transformed.

---

## Author

Van Brantley — [github.com/vanbrantley](https://github.com/vanbrantley)