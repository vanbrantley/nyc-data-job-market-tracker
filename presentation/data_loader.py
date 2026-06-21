"""
data_loader.py
Snowflake connection and query utilities for the NYC Data Job Tracker dashboard.
"""

import os
import json
import pandas as pd
import snowflake.connector
from dotenv import load_dotenv
import streamlit as st

load_dotenv()

def get_secret(key: str) -> str:
    """Get secret from environment variable or Streamlit secrets."""
    value = os.getenv(key)
    if value:
        return value
    try:
        return st.secrets[key]
    except (KeyError, FileNotFoundError):
        raise ValueError(f"Secret '{key}' not found in environment or Streamlit secrets")

def get_connection():
    """Returns a cached Snowflake connection."""
    return snowflake.connector.connect(
        account=get_secret("SNOWFLAKE_ACCOUNT"),
        user=get_secret("SNOWFLAKE_USER"),
        password=get_secret("SNOWFLAKE_PASSWORD"),
        role=get_secret("SNOWFLAKE_ROLE"),
        warehouse=get_secret("SNOWFLAKE_WAREHOUSE"),
        database=get_secret("SNOWFLAKE_DATABASE"),
    )


def run_query(sql: str) -> pd.DataFrame:
    """Execute SQL and return a DataFrame. Creates a fresh connection each time."""
    # Note: fetch_pandas_all() is avoided here due to connector/pandas compatibility
    # issues in this environment. Manual cursor pattern is functionally equivalent.
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        cols = [desc[0] for desc in cur.description]
        cur.close()
        return pd.DataFrame(rows, columns=cols)
    finally:
        conn.close()


@st.cache_data(ttl=3600)
def load_fct_job_postings() -> pd.DataFrame:
    """
    Load and lightly post-process the full fct_job_postings mart table.
    Caches for 1 hour.
    """
    df = run_query("SELECT * FROM ANALYTICS_PROD.PUBLIC.FCT_JOB_POSTINGS")

    # Normalize column names to lowercase for consistent access
    df.columns = [c.lower() for c in df.columns]

    # Parse date columns
    for col in ["date_posted", "enriched_at", "ingested_at"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    # Parse VARIANT array columns from JSON strings
    array_cols = [
        "tech_stack_required",
        "tech_stack_preferred",
        "paradigms_required",
        "paradigms_preferred",
    ]
    for col in array_cols:
        if col in df.columns:
            df[col] = df[col].apply(_parse_variant_array)

    # Coerce numeric salary columns
    for col in ["final_salary_min", "final_salary_max"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Coerce years columns
    for col in ["years_required_min", "years_required_max"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Coerce confidence score
    if "confidence_score" in df.columns:
        df["confidence_score"] = pd.to_numeric(df["confidence_score"], errors="coerce")

    for bool_col in ["acknowledges_ai", "explicitly_encourages_applicants"]:
        if bool_col in df.columns:
            df[bool_col] = df[bool_col].apply(
                lambda x: True if str(x).strip().upper() in ("TRUE", "1", "YES") else False
            )

    return df

@st.cache_data(ttl=300)
def load_pipeline_runs() -> pd.DataFrame:
    """Load pipeline run history from RAW.PIPELINE.RUNS."""
    df = run_query("SELECT * FROM RAW.PIPELINE.RUNS ORDER BY RUN_AT")
    df.columns = [c.lower() for c in df.columns]
    df["run_at"] = pd.to_datetime(df["run_at"], errors="coerce")
    return df


@st.cache_data(ttl=300)
def load_api_usage() -> pd.DataFrame:
    """Load API usage history from RAW.PIPELINE.API_USAGE."""
    df = run_query("SELECT * FROM RAW.PIPELINE.API_USAGE ORDER BY RUN_AT, SOURCE")
    df.columns = [c.lower() for c in df.columns]
    df["run_at"] = pd.to_datetime(df["run_at"], errors="coerce")
    df["reset_date"] = df["reset_date"].apply(lambda x: str(x)[:10] if x else "—")
    return df


def _parse_variant_array(val) -> list:
    """Parse a Snowflake VARIANT column value into a Python list."""
    if val is None:
        return []
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, ValueError):
            return []
    return []

def format_source(val: str) -> str:
    overrides = {
        "builtin": "Built In NYC",
        "jsearch": "JSearch",
        "theirstack": "TheirStack",
    }
    return overrides.get(val, val) if val else val

def format_snake_case(val: str) -> str:
    return val.replace("_", " ") if val else val

def format_salary(min_val, max_val) -> str:
    """Format a salary range for display."""
    def fmt(v):
        if pd.isna(v):
            return None
        v = int(v)
        return f"＄{v:,}"  # unicode fullwidth dollar sign ＄ (U+FF04)

    lo, hi = fmt(min_val), fmt(max_val)
    if lo and hi:
        return f"{lo} - {hi}"
    if lo:
        return f"{lo}+"
    if hi:
        return f"up to {hi}"
    return "Not disclosed"