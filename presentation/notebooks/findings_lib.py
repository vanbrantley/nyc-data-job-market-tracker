"""Shared computations behind the portfolio write-up's "Early Signals" numbers.

Ported directly from findings.ipynb's cells so the notebook (interactive
exploration) and generate_findings_snapshot.py (structured refresh) share one
source of truth instead of drifting apart across refresh cycles.
"""
import json
import os
from collections import Counter

import pandas as pd
import snowflake.connector
from dotenv import load_dotenv

EARLY_CAREER_ORDER = ["entry_or_junior", "mid"]


def connect():
    load_dotenv()
    return snowflake.connector.connect(
        user=os.getenv("SNOWFLAKE_USER"),
        password=os.getenv("SNOWFLAKE_PASSWORD"),
        account=os.getenv("SNOWFLAKE_ACCOUNT"),
        role=os.environ["SNOWFLAKE_ROLE"],
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE"),
        database="ANALYTICS_PROD",
        schema="PUBLIC",
    )


def run_query(conn, sql: str) -> pd.DataFrame:
    cur = conn.cursor()
    cur.execute(sql)
    rows = cur.fetchall()
    cols = [desc[0] for desc in cur.description]
    cur.close()
    return pd.DataFrame(rows, columns=cols)


def _parse_arr(val):
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return []
    return []


def load_mart(conn):
    """Load FCT_JOB_POSTINGS, clean columns, return (df, salary_df, n_no_match_excluded)."""
    df = run_query(conn, "SELECT * FROM ANALYTICS_PROD.PUBLIC.FCT_JOB_POSTINGS")
    df.columns = [c.lower() for c in df.columns]

    for col in ["tech_stack_required", "tech_stack_preferred", "paradigms_required", "paradigms_preferred"]:
        df[col] = df[col].apply(_parse_arr)

    for col in ["date_posted", "ingested_at", "enriched_at"]:
        df[col] = pd.to_datetime(df[col], errors="coerce")

    for col in ["final_salary_min", "final_salary_max", "years_required_min", "years_required_max", "confidence_score"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in ["acknowledges_ai", "explicitly_encourages_applicants"]:
        df[col] = df[col].apply(lambda x: True if str(x).strip().upper() in ("TRUE", "1", "YES") else False)

    # Role grouping: title_role_bucket (regex-classified from job_title) replaces
    # ingestion_query as the role axis. 'no_match' rows are excluded since every
    # role-grouped stat below needs a clean four-way split.
    n_before_match_filter = len(df)
    df = df[df["title_role_bucket"] != "no_match"].copy()
    n_no_match_excluded = n_before_match_filter - len(df)

    salary_df = df.dropna(subset=["final_salary_min", "final_salary_max"]).copy()
    salary_df["salary_mid"] = (salary_df["final_salary_min"] + salary_df["final_salary_max"]) / 2

    return df, salary_df, n_no_match_excluded


def top_level_snapshot(df, salary_df):
    return {
        "total_postings": len(df),
        "unique_companies": int(df["company_name"].nunique()),
        "role_types": int(df["title_role_bucket"].nunique()),
        "sources": int(df["source"].nunique()),
        "salary_disclosed_n": len(salary_df),
        "salary_disclosed_rate": len(salary_df) / len(df),
        "llm_enriched_n": int(df["role_archetype"].notna().sum()),
        "llm_enriched_rate": float(df["role_archetype"].notna().mean()),
        "date_min": str(df["date_posted"].min().date()),
        "date_max": str(df["date_posted"].max().date()),
        "last_ingested": str(df["ingested_at"].max().date()),
    }


def postings_by_role(df):
    return df["title_role_bucket"].value_counts()


def postings_by_source(df):
    return df["source"].value_counts()


def postings_by_role_source(df):
    return df.groupby(["title_role_bucket", "source"]).size().unstack(fill_value=0)


def work_model(df):
    overall = df["work_model"].value_counts()
    by_role = df.groupby(["title_role_bucket", "work_model"]).size().unstack(fill_value=0)
    return overall, by_role


def early_career_tier(df):
    overall = df["early_career_tier"].value_counts()
    by_role = df.groupby(["title_role_bucket", "early_career_tier"]).size().unstack(fill_value=0)
    return overall, by_role


def salary_by_role(df, salary_df):
    sal_by_role = (
        salary_df.groupby("title_role_bucket")["salary_mid"]
        .agg(["median", "count", "min", "max", "std"])
        .round(0)
    )
    sal_by_role.columns = ["median", "n", "min", "max", "std"]

    sal_tier = salary_df[salary_df["early_career_tier"].isin(EARLY_CAREER_ORDER)]
    sal_by_role_tier = (
        sal_tier.groupby(["title_role_bucket", "early_career_tier"])["salary_mid"]
        .agg(["median", "count"])
        .round(0)
    )
    return sal_by_role, sal_by_role_tier


def ai_acknowledgment(df):
    overall = {
        "yes": int(df["acknowledges_ai"].sum()),
        "total": len(df),
        "rate": float(df["acknowledges_ai"].mean()),
    }
    ai = df.groupby("title_role_bucket")["acknowledges_ai"].agg(["sum", "count", "mean"]).round(3)
    ai.columns = ["yes", "total", "rate"]
    return overall, ai


def _roles_match(row):
    # Exact normalized match, not word-overlap — see findings.ipynb cell 10 for
    # why the looser word-overlap check inflated the headline agreement rate.
    title_bucket = row["title_role_bucket"].lower().replace(" ", "_").replace("-", "_")
    archetype = row["role_archetype"].lower()
    return title_bucket == archetype


def title_vs_archetype(df):
    """Confusion matrix + agreement rate between listed title and the LLM's
    independently-classified role_archetype (the "self-consistency" stat)."""
    matrix_df = df.dropna(subset=["role_archetype"]).copy()
    pivot = matrix_df.groupby(["title_role_bucket", "role_archetype"]).size().unstack(fill_value=0)
    pivot_pct = pivot.div(pivot.sum(axis=1), axis=0).round(2)

    matrix_df["_match"] = matrix_df.apply(_roles_match, axis=1)
    overall_agree_n = int(matrix_df["_match"].sum())
    overall_agree_rate = overall_agree_n / len(matrix_df)
    by_role_rate = matrix_df.groupby("title_role_bucket")["_match"].mean()

    return {
        "pivot_counts": pivot,
        "pivot_pct": pivot_pct,
        "overall_agree_n": overall_agree_n,
        "overall_agree_total": len(matrix_df),
        "overall_agree_rate": overall_agree_rate,
        "by_role_rate": by_role_rate,
    }


def top_skills(df, overall_n=20, per_role_n=10):
    all_req = [t for row in df["tech_stack_required"] if isinstance(row, list) for t in row if isinstance(t, str)]
    overall = pd.Series(Counter(all_req)).sort_values(ascending=False).head(overall_n)

    by_role = {}
    for role in df["title_role_bucket"].unique():
        subset = df[df["title_role_bucket"] == role]
        tools = [t for row in subset["tech_stack_required"] if isinstance(row, list) for t in row if isinstance(t, str)]
        by_role[role] = pd.Series(Counter(tools)).sort_values(ascending=False).head(per_role_n)

    return overall, by_role


def top_paradigms(df, per_role_n=10):
    by_role = {}
    for role in df["title_role_bucket"].unique():
        subset = df[df["title_role_bucket"] == role]
        paras = [
            t
            for req, pref in zip(subset["paradigms_required"], subset["paradigms_preferred"])
            for row in [req, pref] if isinstance(row, list)
            for t in row if isinstance(t, str)
        ]
        by_role[role] = pd.Series(Counter(paras)).sort_values(ascending=False).head(per_role_n)
    return by_role


def years_required(df):
    yrs = df.dropna(subset=["years_required_min"])
    by_role = yrs.groupby("title_role_bucket")["years_required_min"].agg(["median", "count"]).round(1)

    yrs_tier = yrs[yrs["early_career_tier"].isin(EARLY_CAREER_ORDER)]
    by_role_tier = (
        yrs_tier.groupby(["title_role_bucket", "early_career_tier"])["years_required_min"]
        .agg(["median", "count"])
        .round(1)
    )
    return by_role, by_role_tier


def degree_requirements(df):
    deg = df.dropna(subset=["degree_requirement"])
    counts = deg.groupby(["title_role_bucket", "degree_requirement"]).size().unstack(fill_value=0)
    pct = counts.div(counts.sum(axis=1), axis=0).round(3)
    return counts, pct


def encourages_applicants(df):
    overall = {
        "yes": int(df["explicitly_encourages_applicants"].sum()),
        "total": len(df),
        "rate": float(df["explicitly_encourages_applicants"].mean()),
    }
    enc = df.groupby("title_role_bucket")["explicitly_encourages_applicants"].agg(["sum", "count", "mean"]).round(3)
    enc.columns = ["yes", "total", "rate"]
    return overall, enc


def seniority_mismatch(df):
    mismatch_df = df.dropna(subset=["listed_seniority", "inferred_seniority"]).copy()
    pivot = mismatch_df.groupby(["listed_seniority", "inferred_seniority"]).size().unstack(fill_value=0)
    pivot_pct = pivot.div(pivot.sum(axis=1), axis=0).round(2)

    yrs_listed = df.dropna(subset=["years_required_min", "listed_seniority"])
    yrs_by_listed = (
        yrs_listed.groupby("listed_seniority")["years_required_min"]
        .agg(["median", "min", "max", "count"])
        .round(1)
    )

    return {
        "pivot_counts": pivot,
        "pivot_pct": pivot_pct,
        "n_both_populated": len(mismatch_df),
        "years_by_listed_seniority": yrs_by_listed,
    }
