"""
pages/00_home.py
Home — framing, the question, the four roles, and how the data is collected.
"""

import sys
import os
import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from data_loader import load_fct_job_postings

# ── Load data for live stats ───────────────────────────────────────────────────
df = load_fct_job_postings()

# ── Page ──────────────────────────────────────────────────────────────────────
st.title("NYC Data Job Market Tracker")
st.markdown(
    "An ongoing investigation into the early-career data job market in New York City — "
    "built to answer a question I needed answered for myself."
)

st.divider()

# ── The Question ──────────────────────────────────────────────────────────────
st.markdown("#### The Question")
st.markdown(
    """
As someone entering the data job market, I found the landscape genuinely confusing.

There are several distinct job titles — Data Analyst, Data Engineer, Analytics Engineer, 
Data Scientist — each with their own supposed definition. But in practice, the lines between 
them are blurry. The tools overlap. The responsibilities overlap. And with AI reshaping how 
data work gets done, the roles themselves appear to be shifting in real time.

Rather than rely on secondhand takes, I built a pipeline to track it directly: 
ingesting live job postings from multiple sources, enriching them with an LLM to cut 
through title noise, and surfacing the patterns in this dashboard.

The goal isn't a definitive answer. It's a clearer picture.
"""
)

st.divider()

# ── The Four Roles ─────────────────────────────────────────────────────────────
st.markdown("#### The Roles Under Investigation")
st.caption(
    "Canonical definitions — what each role is supposed to be, before we look at what's actually being asked for."
)

st.markdown("<br>", unsafe_allow_html=True)

r1, r2, r3, r4 = st.columns(4)

with r1:
    st.markdown("**📊 Data Analyst**")
    st.markdown(
        "Turns data into decisions. Focused on querying, reporting, and communicating insights "
        "to business stakeholders. Primary tools: SQL, Excel, BI tools (Tableau, Power BI)."
    )

with r2:
    st.markdown("**⚙️ Data Engineer**")
    st.markdown(
        "Builds and maintains the infrastructure that moves and stores data. Focused on pipelines, "
        "warehouses, and reliability. Primary tools: Python, Spark, Airflow, cloud platforms."
    )

with r3:
    st.markdown("**🔧 Analytics Engineer**")
    st.markdown(
        "The bridge between engineering and analysis. Transforms raw data into clean, modeled "
        "datasets that analysts can use. Primary tools: dbt, SQL, Snowflake/BigQuery."
    )

with r4:
    st.markdown("**🧪 Data Scientist**")
    st.markdown(
        "Applies statistical modeling and machine learning to extract predictive insight. "
        "Focused on experimentation and model building. Primary tools: Python, scikit-learn, "
        "statsmodels, ML platforms."
    )

st.divider()

# ── How the Data Is Collected ──────────────────────────────────────────────────
st.markdown("#### How the Data Is Collected")

col_pipeline, col_stats = st.columns([1.6, 1])

with col_pipeline:
    st.markdown(
        """
**Three sources, one pipeline.**

Job postings are ingested from three sources on a scheduled pipeline that runs twice a week 
(Monday and Thursday via GitHub Actions):

- **Built In NYC** — a curated NYC-specific job board. Scraped directly. Highest quality 
  salary data and seniority labels.
- **TheirStack** — a tech-stack-focused job API with native seniority classification. 
  Useful for structured metadata.
- **JSearch** — a broad aggregator pulling from Indeed, LinkedIn, and others. 
  Widest coverage, least structured.

Each run fetches postings from the last 3 days, deduplicates across sources, and writes 
raw payloads to Snowflake.

**LLM enrichment layer.**

Every new posting is passed through GPT-4o-mini, which extracts structured metadata 
not present in the raw listing: role archetype, tech stack, paradigms, degree requirements, 
years of experience, whether AI is acknowledged, and more. This is the layer that lets us 
compare what a job is *called* versus what it *actually is*.

**dbt transformation.**

Enriched data is modeled in dbt into a single mart table — `fct_job_postings` — 
which powers every chart in this dashboard.
"""
    )

with col_stats:
    st.markdown("**Pipeline at a glance**")
    st.markdown("<br>", unsafe_allow_html=True)

    latest_run = df["ingested_at"].max()
    latest_str = latest_run.strftime("%b %d, %Y") if pd.notna(latest_run) else "—"

    stats = [
        ("Total Postings", len(df)),
        ("Companies", df["company_name"].nunique()),
        ("Role Types Tracked", df[df["title_role_bucket"] != "no_match"]["title_role_bucket"].nunique()),
        ("Sources", df["source"].nunique()),
        ("Last Ingestion", latest_str),
        ("With Salary Data", f"{df['final_salary_min'].notna().mean():.0%}"),
        ("LLM Enriched", f"{df['role_archetype'].notna().mean():.0%}"),
    ]

    for label, value in stats:
        st.markdown(
            f"<div style='display:flex; justify-content:space-between; "
            f"padding: 6px 0; border-bottom: 1px solid #1e293b;'>"
            f"<span style='color:#94a3b8; font-size:0.85rem;'>{label}</span>"
            f"<span style='color:#cbd5e1; font-size:0.85rem; font-weight:600;'>{value}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)
    st.caption(
        "Pipeline runs Monday and Thursday. Stats update as new postings are ingested. "
    )

st.divider()

# ── Navigation guide ───────────────────────────────────────────────────────────
st.markdown("#### What's in the Dashboard")

n1, n2, n3, n4 = st.columns(4)

with n1:
    st.markdown("**🗺️ The Landscape**")
    st.markdown(
        "Volume, frequency over time, work model split, seniority distribution, "
        "and salary by role type."
    )

with n2:
    st.markdown("**🔬 Under the Hood**")
    st.markdown(
        "Tech stack and paradigm overlap across roles, title vs. LLM archetype agreement, "
        "AI awareness, and experience requirements."
    )

with n3:
    st.markdown("**🔍 Job Explorer**")
    st.markdown(
        "Browse and filter every posting. Includes the full LLM-extracted metadata "
        "alongside the raw job description."
    )

with n4:
    st.markdown("**🛠 Pipeline Health**")
    st.markdown(
        "API credit usage, run history, and ingestion counts per source. "
        "Tracks the pipeline's operational status over time."
    )