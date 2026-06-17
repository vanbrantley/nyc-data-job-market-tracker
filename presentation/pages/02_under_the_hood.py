"""
pages/02_under_the_hood.py
Under the Hood — stack overlap, title vs archetype matrix, AI blindspot, experience & degree requirements.
"""

import sys
import os
import json
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from data_loader import load_fct_job_postings

# ── Constants ──────────────────────────────────────────────────────────────────
CHART_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#cbd5e1", family="Inter, sans-serif", size=12),
    margin=dict(l=16, r=16, t=36, b=16),
)

BLUE   = "#4a7ff0"
AMBER  = "#f59e0b"
GREEN  = "#22c55e"
RED    = "#ef4444"
MUTED  = "#475569"
TEAL   = "#14b8a6"
PURPLE = "#a855f7"

SENIORITY_ORDER  = ["entry_level", "junior", "mid_level"]
SENIORITY_LABELS = {"entry_level": "Entry Level", "junior": "Junior", "mid_level": "Mid Level"}
SENIORITY_COLORS = [GREEN, TEAL, BLUE]

ARCHETYPE_LABELS = {
    "data_analyst":       "Data Analyst",
    "analytics_engineer": "Analytics Engineer",
    "data_engineer":      "Data Engineer",
    "data_scientist":     "Data Scientist",
    "hybrid":             "Hybrid",
}

DEGREE_LABELS = {
    "none":          "None",
    "bachelors":     "Bachelor's",
    "masters":       "Master's",
    "equivalent_ok": "Exp. Accepted",
}

# ── Load & prep ────────────────────────────────────────────────────────────────
df = load_fct_job_postings()

query_order = df["ingestion_query"].value_counts().index.tolist()
QUERY_COLOR_LIST = [BLUE, TEAL, AMBER, GREEN, PURPLE, RED]
query_colors = {q: QUERY_COLOR_LIST[i % len(QUERY_COLOR_LIST)] for i, q in enumerate(query_order)}

salary_df = df.dropna(subset=["final_salary_min", "final_salary_max"]).copy()
salary_df["salary_mid"] = (salary_df["final_salary_min"] + salary_df["final_salary_max"]) / 2
listed_df = df[df["effective_seniority"].isin(SENIORITY_ORDER)].copy()

# ── Page header ────────────────────────────────────────────────────────────────
st.title("🔬 Under the Hood")
st.caption(
    "What these roles are actually asking for — tech stack overlap, how job titles map to "
    "real role types, AI awareness, and experience requirements."
)

st.divider()

# ── Row 1: Tech Stack Heatmap ──────────────────────────────────────────────────
st.markdown("#### Tech Stack Overlap")
st.caption(
    "How often each tool appears in required or preferred tech stack across role types. "
    "Darker = more postings for that role mention that tool."
)

stack_type = st.radio(
    "Stack",
    options=["Required", "Preferred", "Required + Preferred"],
    index=2,
    horizontal=True,
    key="stack_heatmap_type",
)

# Build per-query tool frequency
heatmap_rows = []
for query in query_order:
    subset = df[df["ingestion_query"] == query]
    if stack_type == "Required":
        all_tools = [t for row in subset["tech_stack_required"] if isinstance(row, list) for t in row if isinstance(t, str)]
    elif stack_type == "Preferred":
        all_tools = [t for row in subset["tech_stack_preferred"] if isinstance(row, list) for t in row if isinstance(t, str)]
    else:
        all_tools = [
            t
            for row in subset["tech_stack_required"] + subset["tech_stack_preferred"]
            if isinstance(row, list)
            for t in row if isinstance(t, str)
        ]
    counts = Counter(all_tools)
    for tool, count in counts.items():
        heatmap_rows.append({"query": query, "tool": tool, "count": count})

heatmap_df = pd.DataFrame(heatmap_rows)

if not heatmap_df.empty:
    # Top N tools by total mentions across all queries
    top_tools = (
        heatmap_df.groupby("tool")["count"]
        .sum()
        .sort_values(ascending=False)
        .head(20)
        .index.tolist()
    )
    heatmap_df = heatmap_df[heatmap_df["tool"].isin(top_tools)]
    heatmap_pivot = heatmap_df.pivot_table(index="tool", columns="query", values="count", fill_value=0)
    heatmap_pivot = heatmap_pivot.reindex(columns=query_order, fill_value=0)
    # Sort tools by total descending
    heatmap_pivot = heatmap_pivot.loc[heatmap_pivot.sum(axis=1).sort_values(ascending=True).index]

    fig_heat = go.Figure(go.Heatmap(
        z=heatmap_pivot.values,
        x=heatmap_pivot.columns.tolist(),
        y=heatmap_pivot.index.tolist(),
        colorscale=[[0, "#0f172a"], [0.3, "#1e3a6e"], [0.7, "#3b6fd4"], [1.0, "#93c5fd"]],
        text=heatmap_pivot.values,
        texttemplate="%{text}",
        hovertemplate="%{y} in %{x}: %{z} postings<extra></extra>",
        showscale=True,
        colorbar=dict(
            tickfont=dict(color="#cbd5e1", size=10),
            thickness=12,
            len=0.8,
        ),
    ))
    fig_heat.update_layout(
        **{**CHART_LAYOUT, "margin": dict(l=120, r=40, t=60, b=16)},
        height=520,
        xaxis=dict(side="top", tickfont=dict(size=11)),
        yaxis=dict(tickfont=dict(size=11)),
    )
    st.plotly_chart(fig_heat, use_container_width=True)
else:
    st.info("Not enough tech stack data to render heatmap yet.")

st.divider()

# ── Row 2: Paradigms Heatmap ───────────────────────────────────────────────────
st.markdown("#### Paradigms & Methods Overlap")
st.caption(
    "How often each paradigm or methodology appears across role types — required or preferred."
)

para_rows = []
for query in query_order:
    subset = df[df["ingestion_query"] == query]
    all_paras = [
        t
        for row in subset["paradigms_required"] + subset["paradigms_preferred"]
        if isinstance(row, list)
        for t in row if isinstance(t, str)
    ]
    counts = Counter(all_paras)
    for para, count in counts.items():
        para_rows.append({"query": query, "paradigm": para, "count": count})

para_df = pd.DataFrame(para_rows)

if not para_df.empty:
    top_paras = (
        para_df.groupby("paradigm")["count"]
        .sum()
        .sort_values(ascending=False)
        .head(20)
        .index.tolist()
    )
    para_df = para_df[para_df["paradigm"].isin(top_paras)]
    para_pivot = para_df.pivot_table(index="paradigm", columns="query", values="count", fill_value=0)
    para_pivot = para_pivot.reindex(columns=query_order, fill_value=0)
    para_pivot = para_pivot.loc[para_pivot.sum(axis=1).sort_values(ascending=True).index]

    fig_para = go.Figure(go.Heatmap(
        z=para_pivot.values,
        x=para_pivot.columns.tolist(),
        y=para_pivot.index.tolist(),
        colorscale=[[0, "#0f172a"], [0.3, "#1a3a2e"], [0.7, "#16a34a"], [1.0, "#86efac"]],
        text=para_pivot.values,
        texttemplate="%{text}",
        hovertemplate="%{y} in %{x}: %{z} postings<extra></extra>",
        showscale=True,
        colorbar=dict(
            tickfont=dict(color="#cbd5e1", size=10),
            thickness=12,
            len=0.8,
        ),
    ))
    fig_para.update_layout(
        **{**CHART_LAYOUT, "margin": dict(l=160, r=40, t=60, b=16)},
        height=520,
        xaxis=dict(side="top", tickfont=dict(size=11)),
        yaxis=dict(tickfont=dict(size=11)),
    )
    st.plotly_chart(fig_para, use_container_width=True)
else:
    st.info("Not enough paradigm data to render heatmap yet.")

st.divider()

# ── Row 3: Title vs Archetype Confusion Matrix ─────────────────────────────────
st.markdown("#### Listed Title vs. LLM-Assigned Role Type")
st.caption(
    "**Ingestion query** (how the job was listed/searched) vs. **role archetype** "
    "(what the LLM determined the role actually is based on the description). "
    "Diagonal cells are agreements — off-diagonal are mismatches. "
    "Read across a row to see where a listed role type actually lands."
)

matrix_df = df.dropna(subset=["role_archetype"]).copy()
matrix_df = matrix_df[matrix_df["role_archetype"].isin(ARCHETYPE_LABELS)]

if not matrix_df.empty:
    confusion = (
        matrix_df.groupby(["ingestion_query", "role_archetype"])
        .size()
        .reset_index(name="count")
    )

    archetype_order = [a for a in ARCHETYPE_LABELS if a in matrix_df["role_archetype"].unique()]
    pivot = confusion.pivot_table(
        index="ingestion_query",
        columns="role_archetype",
        values="count",
        fill_value=0,
    )
    pivot = pivot.reindex(index=query_order, columns=archetype_order, fill_value=0)

    # Pct of each row
    row_totals = pivot.sum(axis=1)
    pivot_pct = pivot.div(row_totals, axis=0).fillna(0)

    # Text: show count + pct
    text_vals = [
        [
            f"{pivot.iloc[r, c]}<br>{pivot_pct.iloc[r, c]:.0%}"
            if pivot.iloc[r, c] > 0 else ""
            for c in range(pivot.shape[1])
        ]
        for r in range(pivot.shape[0])
    ]

    # Color by pct — diagonal emphasis handled naturally since agreement = high pct
    fig_matrix = go.Figure(go.Heatmap(
        z=pivot_pct.values,
        x=[ARCHETYPE_LABELS.get(a, a) for a in pivot_pct.columns],
        y=pivot_pct.index.tolist(),
        text=text_vals,
        texttemplate="%{text}",
        colorscale=[[0, "#0f172a"], [0.3, "#312e81"], [0.7, "#6366f1"], [1.0, "#c7d2fe"]],
        hovertemplate="Listed as %{y} → LLM says %{x}: %{z:.0%}<extra></extra>",
        showscale=True,
        colorbar=dict(
            tickformat=".0%",
            tickfont=dict(color="#cbd5e1", size=10),
            thickness=12,
            len=0.8,
        ),
    ))
    fig_matrix.update_layout(
        **{**CHART_LAYOUT, "margin": dict(l=160, r=40, t=80, b=16)},
        height=360,
        xaxis=dict(title="LLM Role Archetype", side="top", tickfont=dict(size=11)),
        yaxis=dict(title="Ingestion Query (Listed Title)", tickfont=dict(size=11)),
    )
    st.plotly_chart(fig_matrix, use_container_width=True)

    # Agreement rate summary
    total_enriched = matrix_df.shape[0]
    # Agreement = ingestion_query word matches role_archetype word (loose match)
    def queries_match(row):
        q = row["ingestion_query"].lower().replace(" ", "_").replace("-", "_")
        a = row["role_archetype"].lower()
        # check if the core words overlap
        q_words = set(q.split("_"))
        a_words = set(a.split("_"))
        return bool(q_words & a_words)

    agree_n = matrix_df.apply(queries_match, axis=1).sum()
    st.caption(
        f"Of {total_enriched} enriched postings, **{agree_n} ({agree_n/total_enriched:.0%})** "
        f"had an LLM archetype that matched the listed role type. "
        f"The remaining **{total_enriched - agree_n} ({(total_enriched - agree_n)/total_enriched:.0%})** "
        f"were classified differently."
    )
else:
    st.info("Not enough enriched data to render the matrix yet.")

st.divider()

# ── Row 4: AI Blindspot + Experience Requirements ──────────────────────────────
col_ai, col_exp = st.columns(2)

with col_ai:
    st.markdown("#### The AI Blind Spot")
    st.caption("% of postings that explicitly mention AI, LLMs, or related tools — by role type")

    ai_by_query = (
        df.groupby("ingestion_query")["acknowledges_ai"]
        .agg(["mean", "sum", "count"])
        .reset_index()
        .sort_values("mean", ascending=True)
    )
    ai_by_query.columns = ["query", "rate", "yes", "total"]

    fig_ai = go.Figure(go.Bar(
        x=ai_by_query["rate"],
        y=ai_by_query["query"],
        orientation="h",
        marker_color=[query_colors[q] for q in ai_by_query["query"]],
        text=[f"{r:.0%}" for r in ai_by_query["rate"]],
        textposition="outside",
        customdata=ai_by_query[["yes", "total"]].values,
        hovertemplate="%{y}: %{text} (%{customdata[0]} of %{customdata[1]})<extra></extra>",
    ))
    fig_ai.update_layout(
        **CHART_LAYOUT, height=300,
        xaxis=dict(title="% Acknowledging AI", gridcolor="#1e293b", zeroline=False, tickformat=".0%", range=[0, 1.0]),
        yaxis=dict(tickfont=dict(size=12)),
    )
    st.plotly_chart(fig_ai, use_container_width=True)

    overall_ai = df["acknowledges_ai"].mean()
    ai_count = int(df["acknowledges_ai"].sum())
    st.info(
        f"**{overall_ai:.0%} of postings** ({ai_count} of {len(df)} total jobs) explicitly mention AI or LLMs.",
        icon="🤖",
    )

with col_exp:
    st.markdown("#### Experience Requirements")
    st.caption("Median years of experience required by role type and seniority (where specified by the LLM)")

    yrs_df = df.dropna(subset=["years_required_min"]).copy()
    yrs_df = yrs_df[yrs_df["effective_seniority"].isin(SENIORITY_ORDER)]

    yrs_by_query_sen = (
        yrs_df.groupby(["ingestion_query", "effective_seniority"])["years_required_min"]
        .agg(["median", "count"])
        .reset_index()
    )
    yrs_by_query_sen.columns = ["query", "seniority", "median", "n"]

    fig_yrs = go.Figure()
    for sen, label, color in zip(SENIORITY_ORDER, SENIORITY_LABELS.values(), SENIORITY_COLORS):
        subset = yrs_by_query_sen[yrs_by_query_sen["seniority"] == sen]
        subset = subset.set_index("query").reindex(query_order).reset_index()
        fig_yrs.add_trace(go.Bar(
            name=label,
            x=subset["query"],
            y=subset["median"],
            marker_color=color,
            customdata=subset["n"].values,
            hovertemplate=f"{label}: %{{y:.1f}} yrs median (n=%{{customdata}})<extra></extra>",
        ))
    fig_yrs.update_layout(
        **CHART_LAYOUT, height=300,
        barmode="group",
        yaxis=dict(title="Median Years Required", gridcolor="#1e293b", zeroline=False),
        legend=dict(orientation="h", y=-0.3, font=dict(size=10)),
    )
    st.plotly_chart(fig_yrs, use_container_width=True)

    n_with_yrs = len(yrs_df)
    st.info(
        f"Based on **{n_with_yrs} of {len(df)} postings** ({n_with_yrs/len(df):.0%}) that specified experience requirements.",
        icon="📋",
    )

st.divider()

# ── Row 5: Degree Requirements ─────────────────────────────────────────────────
st.markdown("#### Degree Requirements by Role Type")
st.caption("Distribution of degree requirements across role types — where specified by the LLM")

degree_df = df.dropna(subset=["degree_requirement"]).copy()
degree_order = ["none", "bachelors", "masters", "equivalent_ok"]
degree_colors = [GREEN, BLUE, PURPLE, AMBER]

deg_by_query = (
    degree_df.groupby(["ingestion_query", "degree_requirement"])
    .size()
    .reset_index(name="count")
)

col_deg1, col_deg2 = st.columns(2)

with col_deg1:
    fig_deg = go.Figure()
    for deg, color in zip(degree_order, degree_colors):
        subset = deg_by_query[deg_by_query["degree_requirement"] == deg]
        subset = subset.set_index("ingestion_query").reindex(query_order).reset_index()
        fig_deg.add_trace(go.Bar(
            name=DEGREE_LABELS.get(deg, deg),
            x=subset["ingestion_query"],
            y=subset["count"],
            marker_color=color,
            hovertemplate=f"{DEGREE_LABELS.get(deg, deg)}: %{{y}} postings<extra></extra>",
        ))
    fig_deg.update_layout(
        **CHART_LAYOUT, height=320,
        barmode="stack",
        title=dict(text="Count by Degree Requirement", font=dict(size=13)),
        xaxis=dict(gridcolor="#1e293b"),
        yaxis=dict(title="# Postings", gridcolor="#1e293b", zeroline=False),
        legend=dict(orientation="h", y=-0.25, font=dict(size=10)),
    )
    st.plotly_chart(fig_deg, use_container_width=True)

with col_deg2:
    # Normalized %
    deg_pct = deg_by_query.copy()
    totals = deg_pct.groupby("ingestion_query")["count"].transform("sum")
    deg_pct["pct"] = deg_pct["count"] / totals

    fig_deg2 = go.Figure()
    for deg, color in zip(degree_order, degree_colors):
        subset = deg_pct[deg_pct["degree_requirement"] == deg]
        subset = subset.set_index("ingestion_query").reindex(query_order).reset_index()
        fig_deg2.add_trace(go.Bar(
            name=DEGREE_LABELS.get(deg, deg),
            x=subset["ingestion_query"],
            y=subset["pct"],
            marker_color=color,
            text=[f"{v:.0%}" if pd.notna(v) else "" for v in subset["pct"]],
            textposition="inside",
            customdata=subset["pct"],
            hovertemplate=f"{DEGREE_LABELS.get(deg, deg)}: %{{customdata:.0%}}<extra></extra>",
        ))
    fig_deg2.update_layout(
        **CHART_LAYOUT, height=320,
        barmode="stack",
        title=dict(text="% Share by Degree Requirement", font=dict(size=13)),
        xaxis=dict(gridcolor="#1e293b"),
        yaxis=dict(title="% of Postings", gridcolor="#1e293b", zeroline=False, tickformat=".0%"),
        legend=dict(orientation="h", y=-0.25, font=dict(size=10)),
    )
    st.plotly_chart(fig_deg2, use_container_width=True)