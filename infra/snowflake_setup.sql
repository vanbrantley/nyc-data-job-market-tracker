---------------------------------------------------------
-- NYC JOB MARKET TRACKER: FULL INFRASTRUCTURE RUNBOOK
-- Fully qualified names throughout — safe to run from
-- any worksheet regardless of UI dropdown state.
---------------------------------------------------------

USE ROLE SYSADMIN;
USE WAREHOUSE nyc_job_tracker_wh;

-- Compute Warehouse
CREATE WAREHOUSE IF NOT EXISTS nyc_job_tracker_wh
    WITH WAREHOUSE_SIZE = 'XSMALL'
    AUTO_SUSPEND = 60
    AUTO_RESUME = TRUE
    COMMENT = 'Dedicated compute warehouse for NYC Job Market Tracker pipeline';

---------------------------------------------------------
-- RAW DATABASE — Ingestion landing layer
---------------------------------------------------------
CREATE DATABASE IF NOT EXISTS raw;

CREATE SCHEMA IF NOT EXISTS raw.jsearch;
CREATE SCHEMA IF NOT EXISTS raw.theirstack;
CREATE SCHEMA IF NOT EXISTS raw.builtin;

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
-- ENRICHED DATABASE — LLM enrichment output layer
---------------------------------------------------------
CREATE DATABASE IF NOT EXISTS enriched;

CREATE SCHEMA IF NOT EXISTS enriched.public;

CREATE TABLE IF NOT EXISTS enriched.public.job_enrichment (
    job_id               VARCHAR,
    source               VARCHAR,
    years_required_min   INTEGER,
    years_required_max   INTEGER,
    inferred_seniority   VARCHAR,
    is_title_inflated    BOOLEAN,
    inflation_reasoning  VARCHAR,
    extracted_tech_stack VARIANT,
    stack_category       VARCHAR,
    confidence_score     FLOAT,
    enriched_at          TIMESTAMP_TZ,
    model_version        VARCHAR
);

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