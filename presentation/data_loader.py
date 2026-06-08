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


@st.cache_resource
def get_connection():
    """Returns a cached Snowflake connection."""
    return snowflake.connector.connect(
        account=os.getenv("SNOWFLAKE_ACCOUNT"),
        user=os.getenv("SNOWFLAKE_USER"),
        password=os.getenv("SNOWFLAKE_PASSWORD"),
        role=os.getenv("SNOWFLAKE_ROLE"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE"),
        database=os.getenv("SNOWFLAKE_DATABASE"),
    )


def run_query(sql: str) -> pd.DataFrame:
    """Execute SQL and return a DataFrame using the manual cursor pattern."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(sql)
    rows = cur.fetchall()
    cols = [desc[0] for desc in cur.description]
    cur.close()
    return pd.DataFrame(rows, columns=cols)


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

    # Normalize boolean
    if "is_title_inflated" in df.columns:
        df["is_title_inflated"] = df["is_title_inflated"].apply(
            lambda x: True if str(x).strip().upper() in ("TRUE", "1", "YES") else False
        )

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