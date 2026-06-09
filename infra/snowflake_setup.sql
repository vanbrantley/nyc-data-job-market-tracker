---------------------------------------------------------
-- NYC JOB MARKET TRACKER: FULL INFRASTRUCTURE RUNBOOK
-- Fully qualified names throughout — safe to run from
-- any worksheet regardless of UI dropdown state.
--
-- IMPORTANT: Snowflake UI requires running each STEP
-- separately. Highlight each step block and run it
-- before moving to the next one.
---------------------------------------------------------

---------------------------------------------------------
-- STEP 1: Role and warehouse
---------------------------------------------------------
USE ROLE SYSADMIN;

CREATE WAREHOUSE IF NOT EXISTS nyc_job_tracker_wh
    WITH WAREHOUSE_SIZE = 'XSMALL'
    AUTO_SUSPEND = 60
    AUTO_RESUME = TRUE
    COMMENT = 'Dedicated compute warehouse for NYC Job Market Tracker pipeline';

USE WAREHOUSE nyc_job_tracker_wh;

---------------------------------------------------------
-- STEP 2: Create all databases
-- Run each CREATE DATABASE line individually —
-- the UI sometimes only executes the last statement
-- when multiple are selected together.
---------------------------------------------------------
CREATE DATABASE IF NOT EXISTS raw;

-- Run above, then run below separately:
CREATE DATABASE IF NOT EXISTS enriched;

-- Run above, then run below separately:
CREATE DATABASE IF NOT EXISTS analytics_dev;

-- Run above, then run below separately:
CREATE DATABASE IF NOT EXISTS analytics_prod;

---------------------------------------------------------
-- STEP 3: Create schemas
-- Safe to run all together once databases exist.
---------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS raw.jsearch;
CREATE SCHEMA IF NOT EXISTS raw.theirstack;
CREATE SCHEMA IF NOT EXISTS raw.builtin;
CREATE SCHEMA IF NOT EXISTS enriched.public;
CREATE SCHEMA IF NOT EXISTS analytics_dev.public;
CREATE SCHEMA IF NOT EXISTS analytics_prod.public;

---------------------------------------------------------
-- STEP 4: Create raw tables
-- Safe to run all together.
---------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.jsearch.src_postings (
    source       VARCHAR,
    raw_payload  VARIANT,
    ingested_at  TIMESTAMP_TZ
);

CREATE TABLE IF NOT EXISTS raw.theirstack.src_postings (
    source       VARCHAR,
    raw_payload  VARIANT,
    ingested_at  TIMESTAMP_TZ
);

CREATE TABLE IF NOT EXISTS raw.builtin.src_postings (
    source       VARCHAR,
    raw_payload  VARIANT,
    ingested_at  TIMESTAMP_TZ
);

---------------------------------------------------------
-- STEP 5: Create enrichment table
---------------------------------------------------------
CREATE TABLE IF NOT EXISTS enriched.public.job_enrichment (
    job_id               VARCHAR,
    source               VARCHAR,
    inferred_seniority   VARCHAR,
    is_title_inflated    BOOLEAN,
    inflation_reasoning  VARCHAR,
    role_archetype       VARCHAR,
    work_focus           VARCHAR,
    tech_stack_required  VARIANT,
    tech_stack_preferred VARIANT,
    paradigms_required   VARIANT,
    paradigms_preferred  VARIANT,
    degree_requirement   VARCHAR,
    years_required_min   INTEGER,
    years_required_max   INTEGER,
    salary_min           FLOAT,
    salary_max           FLOAT,
    confidence_score     FLOAT,
    enriched_at          TIMESTAMP_TZ,
    model_version        VARCHAR
);

-- Note: analytics_dev and analytics_prod need no table
-- definitions — dbt creates and manages all tables there
-- automatically on each run.

---------------------------------------------------------
-- STEP 6: Grants
-- Safe to run all together once databases exist.
---------------------------------------------------------
GRANT ALL PRIVILEGES ON DATABASE raw              TO ROLE SYSADMIN;
GRANT ALL PRIVILEGES ON DATABASE enriched         TO ROLE SYSADMIN;
GRANT ALL PRIVILEGES ON DATABASE analytics_dev    TO ROLE SYSADMIN;
GRANT ALL PRIVILEGES ON DATABASE analytics_prod   TO ROLE SYSADMIN;

GRANT ALL PRIVILEGES ON ALL SCHEMAS IN DATABASE raw              TO ROLE SYSADMIN;
GRANT ALL PRIVILEGES ON ALL SCHEMAS IN DATABASE enriched         TO ROLE SYSADMIN;
GRANT ALL PRIVILEGES ON ALL SCHEMAS IN DATABASE analytics_dev    TO ROLE SYSADMIN;
GRANT ALL PRIVILEGES ON ALL SCHEMAS IN DATABASE analytics_prod   TO ROLE SYSADMIN;

GRANT ALL PRIVILEGES ON ALL TABLES IN DATABASE raw               TO ROLE SYSADMIN;
GRANT ALL PRIVILEGES ON ALL TABLES IN DATABASE enriched          TO ROLE SYSADMIN;

---------------------------------------------------------
-- STEP 7: Create pipeline tracking tables
---------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS raw.pipeline;

CREATE TABLE IF NOT EXISTS raw.pipeline.runs (
    run_id              VARCHAR         NOT NULL,
    run_at              TIMESTAMP_TZ    NOT NULL,
    duration_seconds    FLOAT,
    status              VARCHAR,
    jsearch_rows        INTEGER,
    theirstack_rows     INTEGER,
    builtin_rows        INTEGER,
    total_rows          INTEGER
);

CREATE TABLE IF NOT EXISTS raw.pipeline.api_usage (
    run_id              VARCHAR         NOT NULL,
    run_at              TIMESTAMP_TZ    NOT NULL,
    source              VARCHAR         NOT NULL,
    credits_remaining   INTEGER,
    credits_limit       INTEGER,
    credits_used        INTEGER,
    reset_date          VARCHAR
);

GRANT ALL PRIVILEGES ON SCHEMA raw.pipeline TO ROLE SYSADMIN;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA raw.pipeline TO ROLE SYSADMIN;

-- Original version to create the warehouse and raw database tables

-- ---------------------------------------------------------
-- -- NYC JOB MARKET TRACKER: INGESTION LAYER SETUP RUNBOOK
-- ---------------------------------------------------------

-- -- 1. Create a dedicated, cost-conscious Compute Warehouse
-- CREATE WAREHOUSE IF NOT EXISTS nyc_job_tracker_wh
--     WITH WAREHOUSE_SIZE = 'XSMALL'
--     AUTO_SUSPEND = 60 -- Shuts down automatically after 60 seconds of idling
--     AUTO_RESUME = TRUE
--     COMMENT = 'Dedicated compute warehouse for NYC Job Market Tracker pipeline';

-- -- 2. Create the Raw Ingestion Layer Database
-- CREATE DATABASE IF NOT EXISTS raw;

-- -- 3. Create isolated schemas for each distinct data source
-- CREATE SCHEMA IF NOT EXISTS raw.jsearch;
-- CREATE SCHEMA IF NOT EXISTS raw.theirstack;
-- CREATE SCHEMA IF NOT EXISTS raw.builtin;

-- -- 4. Create the target landing tables with completely generic definitions.
-- -- No defaults here; Python will explicitly supply the SOURCE metadata string.
-- CREATE TABLE IF NOT EXISTS raw.jsearch.src_postings (
--     source VARCHAR,
--     raw_payload VARIANT,
--     ingested_at TIMESTAMP_TZ
-- );

-- CREATE TABLE IF NOT EXISTS raw.theirstack.src_postings (
--     source VARCHAR,
--     raw_payload VARIANT,
--     ingested_at TIMESTAMP_TZ
-- );

-- CREATE TABLE IF NOT EXISTS raw.builtin.src_postings (
--     source VARCHAR,
--     raw_payload VARIANT,
--     ingested_at TIMESTAMP_TZ
-- );