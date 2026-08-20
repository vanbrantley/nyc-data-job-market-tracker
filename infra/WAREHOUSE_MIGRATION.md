# Migrating to a new Snowflake trial account

Snowflake free trials expire (120 days). When that happens, use this runbook
to stand up a fresh trial account and move the pipeline over to it without
losing data. This was last done in August 2026, moving off account
`EMJDDUE-YCC74914` onto `XGVDJNQ-QX38930`.

Start this with at least a few days of runway before the old trial expires —
step 6 needs the old account to still be alive.

## 0. Prerequisites

- A new Snowflake trial account (can be signed up with a different email if
  the old one already used its one free trial).
- The new account's locator, username, and password.

## 1. Update `.env`

`.env` keeps two sets of Snowflake vars: the plain `SNOWFLAKE_*` names (what
all the code actually reads — see `infra/snowflake_client.py`,
`enrichment/run_enrichment.py`, `presentation/data_loader.py`) and an
`_OLD`-suffixed set used only by the migration scripts below.

1. Rename the *current* active block to `_OLD` (`SNOWFLAKE_ACCOUNT` →
   `SNOWFLAKE_ACCOUNT_OLD`, etc. — 6 vars total).
2. Add a new plain `SNOWFLAKE_*` block with the new account's credentials.
   `SNOWFLAKE_ROLE`, `SNOWFLAKE_WAREHOUSE`, and `SNOWFLAKE_DATABASE` almost
   certainly stay the same values (`SYSADMIN`, `nyc_job_tracker_wh`, `RAW`)
   since those are just naming choices, not account-specific — only
   `ACCOUNT`, `USER`, `PASSWORD` actually change.

## 2. Provision the new account

```bash
source venv/bin/activate
python infra/run_setup_sql.py
```

This runs `infra/snowflake_setup.sql` statement-by-statement against
whatever the plain `SNOWFLAKE_*` vars point at — creates the warehouse, the
4 databases (`raw`, `enriched`, `analytics_dev`, `analytics_prod`), schemas,
raw/enrichment/pipeline tables, and grants. All `CREATE ... IF NOT EXISTS`,
safe to re-run.

**If the enrichment schema or pipeline tables have changed since the last
migration** (new columns in `enrichment/schemas/enrichment_schema.py`,
changes to `INSERT_QUERY` in `enrichment/run_enrichment.py`, or to
`write_api_usage`/`write_pipeline_run` in `infra/snowflake_client.py`),
update `infra/snowflake_setup.sql`'s table DDL to match *first* — the two
are not automatically kept in sync, and this file already had that kind of
drift once (see git history on this file from the last migration).

## 3. Copy the data over

```bash
python infra/migrate_data.py
```

Copies all 6 data tables (`raw.jsearch.src_postings`,
`raw.theirstack.src_postings`, `raw.builtin.src_postings`,
`enriched.public.job_enrichment`, `raw.pipeline.runs`,
`raw.pipeline.api_usage`) from the `_OLD` account to the new one, and prints
an old-count vs. new-count check per table. It exits non-zero if any table's
counts don't match after the copy.

`analytics_dev`/`analytics_prod` are **not** copied here — they're
dbt-built, rebuilt in the next step from the raw + enriched data.

## 4. Point dbt at the new account and rebuild the marts

Edit `~/.dbt/profiles.yml` (outside this repo, local to your machine) — both
the `dev` and `prod` targets under the `nyc_job_tracker` profile need the
new `account`/`user`/`password`.

```bash
cd transformation
dbt run                 # rebuilds analytics_dev.public.fct_job_postings
dbt run --target prod   # rebuilds analytics_prod.public.fct_job_postings
cd ..
```

## 5. Recreate `vw_fuzzy_duplicate_candidates`

This view is hand-maintained in Snowsight, not dbt — see `PROJECT.md` for
what it does. `infra/vw_fuzzy_duplicate_candidates.sql` has its DDL as of
the last migration; if it hasn't changed since, just run that file's
`CREATE OR REPLACE VIEW` statement against the new account.

If you've since tweaked the view directly in Snowsight, pull the current
version from the *old* account first (do this before it expires):

```sql
SELECT GET_DDL('VIEW', 'ANALYTICS_PROD.PUBLIC.VW_FUZZY_DUPLICATE_CANDIDATES');
```

Save the result back into `infra/vw_fuzzy_duplicate_candidates.sql`, then run
it against the new account.

## 6. Verify

- Connection sanity check:
  `SELECT CURRENT_USER(), CURRENT_ROLE(), CURRENT_WAREHOUSE(), CURRENT_DATABASE()`
  against the new account.
- `cd presentation && streamlit run app.py` — click through Landscape and
  Pipeline Health, confirm charts and row counts look right.
- Row counts from step 3's output should match old vs. new for every table.
- Optional: insert-and-delete a dummy row using the literal `INSERT_QUERY`
  from `enrichment/run_enrichment.py` against the new `job_enrichment` table,
  to catch DDL mismatches without spending real OpenAI/API credits on a full
  pipeline run.

## 7. Cutover

- **GitHub Actions secrets** (repo Settings → Secrets and Actions): update
  `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, `SNOWFLAKE_PASSWORD`. Leave
  `SNOWFLAKE_ROLE`/`SNOWFLAKE_WAREHOUSE`/`SNOWFLAKE_DATABASE` alone unless
  those values actually changed too.
- **Streamlit Cloud** app secrets (for the live dashboard) — same 3 values.
- Manually trigger the GitHub Actions workflow (`workflow_dispatch` in the
  Actions tab) once to confirm the new secrets work end-to-end, including
  the dbt-profiles-generation step in `.github/workflows/pipeline.yml`.
- Reboot the Streamlit Cloud app if it doesn't pick up the new secrets on
  its own.
- Leave the old trial account alone — it expires on its own, nothing to
  clean up there.
