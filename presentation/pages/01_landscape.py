"""
pages/01_landscape.py
The Landscape — volume, frequency, work model, seniority, and salary by role type.
"""

import sys
import os
import json
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from data_loader import load_fct_job_postings

# ── Constants ──────────────────────────────────────────────────────────────────
CHART_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#cbd5e1", family="Inter, sans-serif", size=12),
    margin=dict(l=16, r=16, t=36, b=16),
)

BLUE  = "#4a7ff0"
AMBER = "#f59e0b"
GREEN = "#22c55e"
RED   = "#ef4444"
MUTED = "#475569"
TEAL  = "#14b8a6"
PURPLE = "#a855f7"

SENIORITY_ORDER  = ["entry_or_junior", "mid"]
SENIORITY_LABELS = {"entry_or_junior": "Entry–Junior", "mid": "Mid"}
SENIORITY_COLORS = [GREEN, BLUE]

SOURCE_LABELS = {"builtin": "Built In NYC", "theirstack": "TheirStack", "jsearch": "JSearch"}
SOURCE_COLORS = {"builtin": BLUE, "theirstack": TEAL, "jsearch": AMBER}

WORK_COLORS = {"remote": GREEN, "hybrid": AMBER, "onsite": BLUE}

# ── Load & prep ────────────────────────────────────────────────────────────────
df = load_fct_job_postings()

salary_df = df.dropna(subset=["final_salary_min", "final_salary_max"]).copy()
salary_df["salary_mid"] = (salary_df["final_salary_min"] + salary_df["final_salary_max"]) / 2

# Consistent query order — sort by volume descending so charts feel stable
query_order = (
    df["ingestion_query"].value_counts().index.tolist()
)
# Assign a color per query deterministically
QUERY_COLOR_LIST = [BLUE, TEAL, AMBER, GREEN, PURPLE, RED]
query_colors = {q: QUERY_COLOR_LIST[i % len(QUERY_COLOR_LIST)] for i, q in enumerate(query_order)}

# ── Page header ────────────────────────────────────────────────────────────────
st.title("🗺️ The Landscape")
st.caption(
    f"A high-level view of the NYC early-career data job market across "
    f"**{len(df)}** postings from Built In NYC, TheirStack, and JSearch."
)

# ── KPI strip ──────────────────────────────────────────────────────────────────
k1, k2, k3, k4 = st.columns(4)
k1.metric("Total Postings", len(df))
k2.metric("Role Types", df["ingestion_query"].nunique())
k3.metric("Companies Hiring", df["company_name"].nunique())
k4.metric("Salary Disclosed", f"{len(salary_df) / len(df):.0%}")

st.divider()

# ── Row 1: Postings by Role Type + Work Model by Role ─────────────────────────
st.markdown("#### Postings by Role Type")
st.caption("Total postings per query across all sources")

col1, col2 = st.columns([1, 1.4])

with col1:
    role_counts = (
        df.groupby("ingestion_query")
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=True)
    )

    fig1 = go.Figure(go.Bar(
        x=role_counts["count"],
        y=role_counts["ingestion_query"],
        orientation="h",
        marker_color=[query_colors[q] for q in role_counts["ingestion_query"]],
        text=role_counts["count"],
        textposition="outside",
        hovertemplate="%{y}: %{x} postings<extra></extra>",
    ))
    fig1.update_layout(
        **CHART_LAYOUT, height=300,
        xaxis=dict(title="# Postings", gridcolor="#1e293b", zeroline=False),
        yaxis=dict(tickfont=dict(size=11)),
    )
    st.plotly_chart(fig1, use_container_width=True)

with col2:
    st.markdown("#### Work Model by Role Type")
    st.caption("Remote / hybrid / onsite split per query")

    wm_by_query = (
        df.groupby(["ingestion_query", "work_model"])
        .size()
        .reset_index(name="count")
    )

    fig2 = go.Figure()
    for wm in ["remote", "hybrid", "onsite"]:
        subset = wm_by_query[wm_by_query["work_model"] == wm]
        # align to query_order
        subset = subset.set_index("ingestion_query").reindex(query_order).reset_index()
        fig2.add_trace(go.Bar(
            name=wm.capitalize(),
            x=subset["ingestion_query"],
            y=subset["count"],
            marker_color=WORK_COLORS.get(wm, MUTED),
            hovertemplate=f"{wm.capitalize()}: %{{y}} postings<extra></extra>",
        ))
    fig2.update_layout(
        **CHART_LAYOUT, height=300,
        barmode="stack",
        xaxis=dict(gridcolor="#1e293b"),
        yaxis=dict(title="# Postings", gridcolor="#1e293b", zeroline=False),
        legend=dict(orientation="h", y=-0.25, font=dict(size=10)),
    )
    st.plotly_chart(fig2, use_container_width=True)

st.divider()

# ── Row 2: Job Frequency Over Time ─────────────────────────────────────────────
st.markdown("#### Job Frequency Over Time")

freq_col, ctrl_col = st.columns([3, 1])

with ctrl_col:
    st.markdown("<br>", unsafe_allow_html=True)
    time_axis = st.radio(
        "Date axis",
        options=["Date Posted", "Ingested At"],
        index=0,
        key="freq_time_axis",
        help=(
            "**Date Posted** shows when jobs entered the market.\n\n"
            "**Ingested At** shows when they entered this pipeline — "
            "useful for tracking pipeline activity over time."
        ),
    )
    source_filter = st.multiselect(
        "Filter by source",
        options=list(SOURCE_LABELS.keys()),
        format_func=lambda x: SOURCE_LABELS[x],
        default=[],
        placeholder="All sources",
        key="freq_source_filter",
    )

date_col = "date_posted" if time_axis == "Date Posted" else "ingested_at"
freq_df = df.copy()

if source_filter:
    freq_df = freq_df[freq_df["source"].isin(source_filter)]

# Normalize date to date only
freq_df["_date"] = pd.to_datetime(freq_df[date_col]).dt.date

freq_grouped = (
    freq_df.groupby(["_date", "ingestion_query"])
    .size()
    .reset_index(name="count")
)

# Make cumulative per query
freq_grouped = freq_grouped.sort_values("_date")
freq_grouped["cumulative"] = freq_grouped.groupby("ingestion_query")["count"].cumsum()

with freq_col:
    st.caption(
        f"Postings per query grouped by **{time_axis.lower()}** — "
        f"{'all sources' if not source_filter else ', '.join(SOURCE_LABELS[s] for s in source_filter)}"
    )

    fig3 = go.Figure()
    for query in query_order:
        subset = freq_grouped[freq_grouped["ingestion_query"] == query].sort_values("_date")
        fig3.add_trace(go.Scatter(
            x=subset["_date"],
            y=subset["cumulative"],
            mode="lines+markers",
            name=query,
            line=dict(color=query_colors[query], width=2),
            marker=dict(size=6),
            hovertemplate=f"{query}: %{{y}} total postings as of %{{x}}<extra></extra>",
        ))
    fig3.update_layout(
        **CHART_LAYOUT, height=320,
        xaxis=dict(title=time_axis, gridcolor="#1e293b", zeroline=False),
        yaxis=dict(title="Cumulative # Postings", gridcolor="#1e293b", zeroline=False),
        legend=dict(orientation="h", y=-0.25, font=dict(size=10)),
    )
    st.plotly_chart(fig3, use_container_width=True)

st.divider()

# ── Row 3: Seniority Distribution by Role ─────────────────────────────────────
st.markdown("#### Seniority Distribution by Role Type")

listed_df = df[df["early_career_tier"].isin(SENIORITY_ORDER)].copy()
st.caption(
    f"Based on source-labeled seniority from Built In NYC and TheirStack only "
    f"(JSearch has no structured seniority field). n={len(listed_df)}."
)

sen_by_query = (
        listed_df.groupby(["ingestion_query", "early_career_tier"])
        .size()
        .reset_index(name="count")
    )

col5, col6 = st.columns(2)

with col5:

    fig5 = go.Figure()
    for sen, label, color in zip(SENIORITY_ORDER, SENIORITY_LABELS.values(), SENIORITY_COLORS):
        subset = sen_by_query[sen_by_query["early_career_tier"] == sen]
        subset = subset.set_index("ingestion_query").reindex(query_order).reset_index()
        fig5.add_trace(go.Bar(
            name=label,
            x=subset["ingestion_query"],
            y=subset["count"],
            marker_color=color,
            hovertemplate=f"{label}: %{{y}} postings<extra></extra>",
        ))
    fig5.update_layout(
        **CHART_LAYOUT, height=320,
        barmode="stack",
        title=dict(text="Count by Seniority", font=dict(size=13)),
        xaxis=dict(gridcolor="#1e293b"),
        yaxis=dict(title="# Postings", gridcolor="#1e293b", zeroline=False),
        legend=dict(orientation="h", y=-0.25, font=dict(size=10)),
    )
    st.plotly_chart(fig5, use_container_width=True)

with col6:
    # Normalize to % within each query
    sen_pct = sen_by_query.copy()
    totals = sen_pct.groupby("ingestion_query")["count"].transform("sum")
    sen_pct["pct"] = sen_pct["count"] / totals

    fig6 = go.Figure()
    for sen, label, color in zip(SENIORITY_ORDER, SENIORITY_LABELS.values(), SENIORITY_COLORS):
        subset = sen_pct[sen_pct["early_career_tier"] == sen]
        subset = subset.set_index("ingestion_query").reindex(query_order).reset_index()
        fig6.add_trace(go.Bar(
            name=label,
            x=subset["ingestion_query"],
            y=subset["pct"],
            marker_color=color,
            hovertemplate=f"{label}: %{{customdata:.0%}} of labeled postings<extra></extra>",
            customdata=subset["pct"],
            text=[f"{v:.0%}" if pd.notna(v) else "" for v in subset["pct"]],
            textposition="inside",
        ))
    fig6.update_layout(
        **CHART_LAYOUT, height=320,
        barmode="stack",
        title=dict(text="% Share by Seniority", font=dict(size=13)),
        xaxis=dict(gridcolor="#1e293b"),
        yaxis=dict(title="% of Labeled Postings", gridcolor="#1e293b", zeroline=False, tickformat=".0%"),
        legend=dict(orientation="h", y=-0.25, font=dict(size=10)),
    )
    st.plotly_chart(fig6, use_container_width=True)

st.divider()

# ── Row 4: Salary by Role Type ────────────────────────────────────────────────
st.markdown("#### Salary by Role Type")
st.caption(
    f"Median salary where disclosed (n={len(salary_df)} of {len(df)} postings, "
    f"{len(salary_df)/len(df):.0%}). Hover for sample size per group."
)

col7, col8 = st.columns(2)

with col7:
    arch_sal = (
        salary_df.groupby("ingestion_query")["salary_mid"]
        .agg(["median", "count"])
        .reset_index()
    )
    arch_sal.columns = ["query", "median", "n"]
    arch_sal = arch_sal.sort_values("median", ascending=False)

    fig7 = go.Figure(go.Bar(
        x=arch_sal["query"],
        y=arch_sal["median"],
        marker_color=[query_colors[q] for q in arch_sal["query"]],
        text=[f"＄{v/1000:.0f}k" for v in arch_sal["median"]],
        textposition="outside",
        customdata=arch_sal["n"].values,
        hovertemplate="%{x}: ＄%{y:,.0f} median (n=%{customdata} with salary)<extra></extra>",
    ))
    fig7.update_layout(
        **CHART_LAYOUT, height=320,
        title=dict(text="Median by Role", font=dict(size=13)),
        yaxis=dict(title="Median Salary (＄)", gridcolor="#1e293b", zeroline=False, tickformat="$,.0f"),
    )
    st.plotly_chart(fig7, use_container_width=True)

with col8:
    # Salary by role x seniority — grouped bars
    sal_listed = salary_df[salary_df["early_career_tier"].isin(SENIORITY_ORDER)].copy()
    sal_by_role_sen = (
        sal_listed.groupby(["ingestion_query", "early_career_tier"])["salary_mid"]
        .agg(["median", "count"])
        .reset_index()
    )
    sal_by_role_sen.columns = ["query", "seniority", "median", "n"]

    fig8 = go.Figure()
    for sen, label, color in zip(SENIORITY_ORDER, SENIORITY_LABELS.values(), SENIORITY_COLORS):
        subset = sal_by_role_sen[sal_by_role_sen["seniority"] == sen]
        subset = subset.set_index("query").reindex(query_order).reset_index()
        fig8.add_trace(go.Bar(
            name=label,
            x=subset["query"],
            y=subset["median"],
            marker_color=color,
            customdata=subset["n"].values,
            hovertemplate=f"{label}: ＄%{{y:,.0f}} median (n=%{{customdata}} with salary)<extra></extra>",
        ))
    fig8.update_layout(
        **CHART_LAYOUT, height=320,
        barmode="group",
        title=dict(text="Median by Role × Seniority (labeled only)", font=dict(size=13)),
        xaxis=dict(gridcolor="#1e293b"),
        yaxis=dict(title="Median Salary (＄)", gridcolor="#1e293b", zeroline=False, tickformat="$,.0f"),
        legend=dict(orientation="h", y=-0.25, font=dict(size=10)),
    )
    st.plotly_chart(fig8, use_container_width=True)