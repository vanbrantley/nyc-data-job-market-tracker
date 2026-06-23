"""
pages/02_under_the_hood.py
Under the Hood — stack overlap, title vs archetype matrix, AI blindspot, experience & degree requirements.
"""

import sys
import os
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

SENIORITY_ORDER  = ["entry_or_junior", "mid"]
SENIORITY_LABELS = {"entry_or_junior": "Entry–Junior", "mid": "Mid"}
SENIORITY_COLORS = [GREEN, BLUE]

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

# Exclude postings whose title didn't cleanly map to one of the four target
# roles — every chart on this page groups by role, and a no_match bucket would
# just be noise alongside the real four. See Pipeline Health for the breakdown.
df = df[df["title_role_bucket"] != "no_match"]

role_order = df["title_role_bucket"].value_counts().index.tolist()
ROLE_COLOR_LIST = [BLUE, TEAL, AMBER, GREEN, PURPLE, RED]
role_colors = {r: ROLE_COLOR_LIST[i % len(ROLE_COLOR_LIST)] for i, r in enumerate(role_order)}

salary_df = df.dropna(subset=["final_salary_min", "final_salary_max"]).copy()
salary_df["salary_mid"] = (salary_df["final_salary_min"] + salary_df["final_salary_max"]) / 2

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
    "Lighter = more postings for that role mention that tool."
)

stack_type = st.radio(
    "Stack",
    options=["Required", "Preferred", "Required + Preferred"],
    index=2,
    horizontal=True,
    key="stack_heatmap_type",
)

# Build per-role tool frequency
heatmap_rows = []
for role in role_order:
    subset = df[df["title_role_bucket"] == role]
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
        heatmap_rows.append({"role": role, "tool": tool, "count": count})

heatmap_df = pd.DataFrame(heatmap_rows)

if not heatmap_df.empty:
    # Top N tools by total mentions across all roles
    top_tools = (
        heatmap_df.groupby("tool")["count"]
        .sum()
        .sort_values(ascending=False)
        .head(20)
        .index.tolist()
    )
    heatmap_df = heatmap_df[heatmap_df["tool"].isin(top_tools)]
    heatmap_pivot = heatmap_df.pivot_table(index="tool", columns="role", values="count", fill_value=0)
    heatmap_pivot = heatmap_pivot.reindex(columns=role_order, fill_value=0)
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
for role in role_order:
    subset = df[df["title_role_bucket"] == role]
    all_paras = [
        t
        for row in subset["paradigms_required"] + subset["paradigms_preferred"]
        if isinstance(row, list)
        for t in row if isinstance(t, str)
    ]
    counts = Counter(all_paras)
    for para, count in counts.items():
        para_rows.append({"role": role, "paradigm": para, "count": count})

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
    para_pivot = para_df.pivot_table(index="paradigm", columns="role", values="count", fill_value=0)
    para_pivot = para_pivot.reindex(columns=role_order, fill_value=0)
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
    "**Listed role** (classified directly from the posting's job title) vs. **role archetype** "
    "(what the LLM determined the role actually is, based on the full description). "
    "Diagonal cells are agreements — off-diagonal are mismatches. "
    "Read across a row to see where a listed role type actually lands."
)

matrix_df = df.dropna(subset=["role_archetype"]).copy()
matrix_df = matrix_df[matrix_df["role_archetype"].isin(ARCHETYPE_LABELS)]

if not matrix_df.empty:
    confusion = (
        matrix_df.groupby(["title_role_bucket", "role_archetype"])
        .size()
        .reset_index(name="count")
    )

    archetype_order = [a for a in ARCHETYPE_LABELS if a in matrix_df["role_archetype"].unique()]
    pivot = confusion.pivot_table(
        index="title_role_bucket",
        columns="role_archetype",
        values="count",
        fill_value=0,
    )
    pivot = pivot.reindex(index=role_order, columns=archetype_order, fill_value=0)

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
        yaxis=dict(title="Listed Title (Role Bucket)", tickfont=dict(size=11)),
    )
    st.plotly_chart(fig_matrix, use_container_width=True)

    # Agreement rate summary
    total_enriched = matrix_df.shape[0]
    # Agreement = title_role_bucket word matches role_archetype word (loose match)
    def roles_match(row):
        listed = row["title_role_bucket"].lower().replace(" ", "_").replace("-", "_")
        archetype = row["role_archetype"].lower()
        # check if the core words overlap
        listed_words = set(listed.split("_"))
        archetype_words = set(archetype.split("_"))
        return bool(listed_words & archetype_words)

    agree_n = matrix_df.apply(roles_match, axis=1).sum()
    st.caption(
        f"Of {total_enriched} enriched postings, **{agree_n} ({agree_n/total_enriched:.0%})** "
        f"had an LLM archetype that matched the listed title. "
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

    ai_by_role = (
        df.groupby("title_role_bucket")["acknowledges_ai"]
        .agg(["mean", "sum", "count"])
        .reset_index()
        .sort_values("mean", ascending=True)
    )
    ai_by_role.columns = ["role", "rate", "yes", "total"]

    fig_ai = go.Figure(go.Bar(
        x=ai_by_role["rate"],
        y=ai_by_role["role"],
        orientation="h",
        marker_color=[role_colors[r] for r in ai_by_role["role"]],
        text=[f"{r:.0%}" for r in ai_by_role["rate"]],
        textposition="outside",
        customdata=ai_by_role[["yes", "total"]].values,
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
    st.caption(
        "Built In NYC and TheirStack only, since they're the only sources that list "
        "seniority — shown where years of experience and seniority were both specified."
    )

    yrs_df = df.dropna(subset=["years_required_min"]).copy()
    yrs_df = yrs_df[yrs_df["early_career_tier"].isin(SENIORITY_ORDER)]

    yrs_by_role_sen = (
        yrs_df.groupby(["title_role_bucket", "early_career_tier"])["years_required_min"]
        .agg(["median", "count"])
        .reset_index()
    )
    yrs_by_role_sen.columns = ["role", "seniority", "median", "n"]

    fig_yrs = go.Figure()
    for sen, label, color in zip(SENIORITY_ORDER, SENIORITY_LABELS.values(), SENIORITY_COLORS):
        subset = yrs_by_role_sen[yrs_by_role_sen["seniority"] == sen]
        subset = subset.set_index("role").reindex(role_order).reset_index()
        fig_yrs.add_trace(go.Bar(
            name=label,
            x=subset["role"],
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

deg_by_role = (
    degree_df.groupby(["title_role_bucket", "degree_requirement"])
    .size()
    .reset_index(name="count")
)

col_deg1, col_deg2 = st.columns(2)

with col_deg1:
    fig_deg = go.Figure()
    for deg, color in zip(degree_order, degree_colors):
        subset = deg_by_role[deg_by_role["degree_requirement"] == deg]
        subset = subset.set_index("title_role_bucket").reindex(role_order).reset_index()
        fig_deg.add_trace(go.Bar(
            name=DEGREE_LABELS.get(deg, deg),
            x=subset["title_role_bucket"],
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
    deg_pct = deg_by_role.copy()
    totals = deg_pct.groupby("title_role_bucket")["count"].transform("sum")
    deg_pct["pct"] = deg_pct["count"] / totals

    fig_deg2 = go.Figure()
    for deg, color in zip(degree_order, degree_colors):
        subset = deg_pct[deg_pct["degree_requirement"] == deg]
        subset = subset.set_index("title_role_bucket").reindex(role_order).reset_index()
        fig_deg2.add_trace(go.Bar(
            name=DEGREE_LABELS.get(deg, deg),
            x=subset["title_role_bucket"],
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