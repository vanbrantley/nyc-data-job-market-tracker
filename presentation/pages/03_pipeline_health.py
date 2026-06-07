"""
pages/03_pipeline_health.py
Pipeline Health & Metadata — the "clencher" page.
Shows internal pipeline mechanics: ingestion trends, LLM enrichment quality, architecture.
"""

import sys
import os
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from data_loader import load_fct_job_postings, run_query

# ── Load data ─────────────────────────────────────────────────────────────────
df = load_fct_job_postings()

st.title("🛠 Pipeline Health")
st.caption(
    "Internal mechanics: ingestion cadence, LLM enrichment quality, and system architecture. "
)

# ── Top-level health metrics ──────────────────────────────────────────────────
total_rows = len(df)
sources_active = df["source"].nunique()
enriched_rows = df["enriched_at"].notna().sum()
enrichment_rate = enriched_rows / total_rows if total_rows else 0
salary_populated = df["final_salary_min"].notna().sum()
salary_rate = salary_populated / total_rows if total_rows else 0
tech_stack_populated = df["tech_stack_required"].apply(lambda x: len(x) > 0 if isinstance(x, list) else False).sum()
tech_stack_rate = tech_stack_populated / total_rows if total_rows else 0
inflated_count = (df["is_title_inflated"] == True).sum()
inflation_rate = inflated_count / total_rows if total_rows else 0

latest_ingestion = df["ingested_at"].max()
latest_str = latest_ingestion.strftime("%b %d, %Y %H:%M UTC") if pd.notna(latest_ingestion) else "—"

st.markdown("#### System Status")
m1, m2, m3, m4, m5 = st.columns(5)

with m1:
    st.markdown(
        f'<div class="metric-card"><div class="metric-val">{total_rows}</div>'
        f'<div class="metric-label">Total Postings</div></div>',
        unsafe_allow_html=True,
    )
with m2:
    st.markdown(
        f'<div class="metric-card"><div class="metric-val">{enrichment_rate:.0%}</div>'
        f'<div class="metric-label">LLM Enriched</div></div>',
        unsafe_allow_html=True,
    )
with m3:
    st.markdown(
        f'<div class="metric-card"><div class="metric-val">{salary_rate:.0%}</div>'
        f'<div class="metric-label">Salary Populated</div></div>',
        unsafe_allow_html=True,
    )
with m4:
    st.markdown(
        f'<div class="metric-card"><div class="metric-val">{tech_stack_rate:.0%}</div>'
        f'<div class="metric-label">Tech Stack Extracted</div></div>',
        unsafe_allow_html=True,
    )
with m5:
    st.markdown(
        f'<div class="metric-card"><div class="metric-val">{latest_str}</div>'
        f'<div class="metric-label">Last Pipeline Run</div></div>',
        unsafe_allow_html=True,
    )

st.markdown("")

# ── Charts row 1: Ingestion over time + source breakdown ─────────────────────
st.markdown("#### Ingestion Trends")
chart_col1, chart_col2 = st.columns([2, 1])

with chart_col1:
    # Cumulative rows over time by ingested_at date
    if df["ingested_at"].notna().any():
        ingestion_df = (
            df[df["ingested_at"].notna()]
            .groupby(df["ingested_at"].dt.date)
            .size()
            .reset_index(name="new_rows")
            .sort_values("ingested_at")
        )
        ingestion_df["cumulative"] = ingestion_df["new_rows"].cumsum()

        fig_trend = go.Figure()
        fig_trend.add_bar(
            x=ingestion_df["ingested_at"],
            y=ingestion_df["new_rows"],
            name="New rows",
            marker_color="#94a3b8",
        )
        fig_trend.add_scatter(
            x=ingestion_df["ingested_at"],
            y=ingestion_df["cumulative"],
            mode="lines+markers",
            name="Cumulative",
            line=dict(color="#2563eb", width=2),
            yaxis="y2",
        )
        fig_trend.update_layout(
            title="Rows Ingested Over Time",
            xaxis_title="Date",
            yaxis_title="New Rows",
            yaxis2=dict(
                title="Cumulative",
                overlaying="y",
                side="right",
                showgrid=False,
            ),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            margin=dict(l=0, r=0, t=40, b=0),
            height=300,
            plot_bgcolor="white",
            paper_bgcolor="white",
        )
        st.plotly_chart(fig_trend, use_container_width=True)
    else:
        st.info("No ingested_at timestamps available yet.")

with chart_col2:
    source_counts = df["source"].value_counts().reset_index()
    source_counts.columns = ["source", "count"]
    colors = {"jsearch": "#3b82f6", "theirstack": "#10b981", "builtin": "#f59e0b"}
    bar_colors = [colors.get(s, "#94a3b8") for s in source_counts["source"]]

    fig_src = go.Figure(go.Bar(
        x=source_counts["source"],
        y=source_counts["count"],
        marker_color=bar_colors,
        text=source_counts["count"],
        textposition="outside",
    ))
    fig_src.update_layout(
        title="Postings by Source",
        margin=dict(l=0, r=0, t=40, b=0),
        height=300,
        plot_bgcolor="white",
        paper_bgcolor="white",
        yaxis_title="Count",
        xaxis_title="",
        showlegend=False,
    )
    st.plotly_chart(fig_src, use_container_width=True)

# ── Charts row 2: LLM enrichment quality ─────────────────────────────────────
st.markdown("#### LLM Enrichment Quality")
eq_col1, eq_col2 = st.columns(2)

with eq_col1:
    # Fill rate breakdown as a horizontal bar chart
    fill_metrics = {
        "Salary extracted": salary_rate,
        "Tech stack (required)": tech_stack_rate,
        "Role archetype": df["role_archetype"].notna().mean(),
        "Work focus": df["work_focus"].notna().mean(),
        "Inferred seniority": df["inferred_seniority"].notna().mean(),
        "Degree requirement": df["degree_requirement"].notna().mean(),
        "YoE (min)": df["years_required_min"].notna().mean(),
        "Paradigms (required)": df["paradigms_required"].apply(
            lambda x: len(x) > 0 if isinstance(x, list) else False
        ).mean(),
    }

    fill_df = (
        pd.DataFrame.from_dict(fill_metrics, orient="index", columns=["fill_rate"])
        .sort_values("fill_rate")
        .reset_index()
    )
    fill_df.columns = ["field", "fill_rate"]

    fig_fill = go.Figure(go.Bar(
        x=fill_df["fill_rate"],
        y=fill_df["field"],
        orientation="h",
        marker=dict(
            color=fill_df["fill_rate"],
            colorscale=[[0, "#fecaca"], [0.5, "#fcd34d"], [1, "#86efac"]],
            showscale=False,
        ),
        text=[f"{v:.0%}" for v in fill_df["fill_rate"]],
        textposition="outside",
    ))
    fig_fill.update_layout(
        title="Enrichment Field Fill Rates",
        margin=dict(l=0, r=60, t=40, b=0),
        height=320,
        plot_bgcolor="white",
        paper_bgcolor="white",
        xaxis=dict(tickformat=".0%", range=[0, 1.1]),
        xaxis_title="",
        yaxis_title="",
    )
    st.plotly_chart(fig_fill, use_container_width=True)

with eq_col2:
    # Confidence score distribution
    conf_df = df["confidence_score"].dropna()
    if len(conf_df) > 0:
        fig_conf = px.histogram(
            conf_df,
            nbins=20,
            title="LLM Confidence Score Distribution",
            color_discrete_sequence=["#6366f1"],
            labels={"value": "Confidence Score", "count": "# Postings"},
        )
        fig_conf.update_layout(
            margin=dict(l=0, r=0, t=40, b=0),
            height=320,
            plot_bgcolor="white",
            paper_bgcolor="white",
            showlegend=False,
            bargap=0.05,
        )
        st.plotly_chart(fig_conf, use_container_width=True)
    else:
        st.info("No confidence scores available yet.")

# ── Title inflation summary ───────────────────────────────────────────────────
st.markdown("#### Title Inflation Detector")
inf_col1, inf_col2 = st.columns([1, 2])

with inf_col1:
    fig_inf = go.Figure(go.Indicator(
        mode="gauge+number",
        value=inflation_rate * 100,
        title={"text": "Inflation Rate"},
        number={"suffix": "%", "font": {"size": 40}},
        gauge={
            "axis": {"range": [0, 50]},
            "bar": {"color": "#ef4444"},
            "steps": [
                {"range": [0, 10], "color": "#dcfce7"},
                {"range": [10, 25], "color": "#fef9c3"},
                {"range": [25, 50], "color": "#fee2e2"},
            ],
            "threshold": {
                "line": {"color": "#991b1b", "width": 3},
                "thickness": 0.75,
                "value": inflation_rate * 100,
            },
        },
    ))
    fig_inf.update_layout(height=260, margin=dict(l=20, r=20, t=40, b=0))
    st.plotly_chart(fig_inf, use_container_width=True)
    st.caption(f"{inflated_count} of {total_rows} postings flagged")

with inf_col2:
    inflated_df = df[df["is_title_inflated"] == True][
        ["job_title", "company_name", "role_archetype", "inferred_seniority", "inflation_reasoning"]
    ].copy()
    inflated_df.columns = ["Title", "Company", "Archetype", "Seniority", "Reasoning"]
    if len(inflated_df) > 0:
        st.dataframe(inflated_df.reset_index(drop=True), use_container_width=True, height=220, hide_index=True)
    else:
        st.info("No title inflation detected in current dataset.")

# ── Source health breakdown ───────────────────────────────────────────────────
st.markdown("#### Source-Level Health")

source_health = []
for src in df["source"].dropna().unique():
    src_df = df[df["source"] == src]
    n = len(src_df)
    source_health.append({
        "Source": src,
        "Postings": n,
        "% Enriched": f"{src_df['enriched_at'].notna().mean():.0%}",
        "% Salary": f"{src_df['final_salary_min'].notna().mean():.0%}",
        "% Tech Stack": f"{src_df['tech_stack_required'].apply(lambda x: len(x) > 0 if isinstance(x, list) else False).mean():.0%}",
        "Avg Confidence": f"{src_df['confidence_score'].mean():.2f}" if src_df['confidence_score'].notna().any() else "—",
        "Latest Ingestion": src_df["ingested_at"].max().strftime("%b %d, %Y") if src_df["ingested_at"].notna().any() else "—",
    })

st.dataframe(
    pd.DataFrame(source_health),
    use_container_width=True,
    hide_index=True,
)

# ── Architecture diagram ──────────────────────────────────────────────────────
st.markdown("#### Pipeline Architecture")
st.markdown(
    """
    <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:12px; padding:24px 28px; font-family:monospace; font-size:0.85rem; line-height:1.9; color:#334155;">

    <div style="font-family:sans-serif; font-weight:700; font-size:1rem; color:#0f172a; margin-bottom:12px;">
        NYC Data Job Market Tracker — End-to-End Pipeline
    </div>

    <b>INGESTION</b> (GitHub Actions cron · Mon/Thu)<br>
    ├── <b>JSearch</b> (RapidAPI) → cursor-based pagination → raw VARIANT rows<br>
    ├── <b>TheirStack</b> → two-stage free-sweep / paid-fetch → raw VARIANT rows<br>
    └── <b>Built In NYC</b> → BeautifulSoup scraper → HTML-stripped descriptions<br>
    &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;↓<br>
    <b>SNOWFLAKE RAW</b> (strict ELT — no transformation at ingest)<br>
    &nbsp;&nbsp;&nbsp;&nbsp;RAW.JSEARCH_RAW · RAW.THEIRSTACK_RAW · RAW.BUILTIN_RAW<br>
    &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;↓<br>
    <b>ENRICHMENT</b> (GPT-4o-mini · runs post-ingest)<br>
    &nbsp;&nbsp;&nbsp;&nbsp;Structured metadata extraction: role_archetype, work_focus,<br>
    &nbsp;&nbsp;&nbsp;&nbsp;tech_stack, paradigms, salary (from description text),<br>
    &nbsp;&nbsp;&nbsp;&nbsp;seniority inference, title inflation flag + reasoning<br>
    &nbsp;&nbsp;&nbsp;&nbsp;→ writes to ENRICHED.JOB_ENRICHMENT<br>
    &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;↓<br>
    <b>dbt TRANSFORMATION</b> (runs in CI after ingest + enrich)<br>
    &nbsp;&nbsp;&nbsp;&nbsp;stg_jsearch · stg_theirstack · stg_builtin (views)<br>
    &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;↓ int_jobs_unioned · int_jobs_deduped · int_jobs_enriched (ephemeral)<br>
    &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;↓ fct_job_postings (table · ANALYTICS_PROD.PUBLIC)<br>
    &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;↓<br>
    <b>PRESENTATION</b> (this dashboard · Streamlit)<br>
    &nbsp;&nbsp;&nbsp;&nbsp;Market Insights · Job Explorer · Pipeline Health<br>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown("")
st.markdown(
    """
    **Key design decisions:**
    - **VARIANT columns** for raw JSON storage — schema-on-read, no ingest-time transformation
    - **ELT over ETL** — all transformation happens in dbt, not Python
    - **Ephemeral intermediates** — no intermediate table storage, only staging views and the final mart table hit Snowflake storage
    - **Cross-source deduplication** via URL normalization before unioning
    - **COALESCE salary logic** — structured payload salary takes precedence over LLM-extracted salary from description text
    - **POSIX ERE regex** for seniority filtering (Snowflake-compatible word boundary handling)
    """,
)