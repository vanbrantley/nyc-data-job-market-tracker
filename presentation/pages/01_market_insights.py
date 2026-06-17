"""
pages/01_market_insights.py
Market Insights — high-level snapshot of the NYC data job market.
"""

import sys
import os
import json
import pandas as pd
import plotly.graph_objects as go
from collections import Counter
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from data_loader import load_fct_job_postings

# ── Constants ─────────────────────────────────────────────────────────────────
MODERN_SKILLS = {"dbt", "snowflake", "airflow", "spark", "kafka", "databricks"}
TRAD_SKILLS   = {"excel", "tableau", "power bi", "sql server", "access", "sas", "stata"}

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

SENIORITY_ORDER  = ["entry_level", "junior", "mid_level"]
SENIORITY_LABELS = {"entry_level": "Entry Level", "junior": "Junior", "mid_level": "Mid Level"}
SENIORITY_COLORS = [GREEN, TEAL, BLUE]

ARCHETYPE_LABELS = {
    "data_analyst":        "Data Analyst",
    "analytics_engineer":  "Analytics Engineer",
    "data_engineer":       "Data Engineer",
    "hybrid":              "Hybrid",
}
ARCHETYPE_COLORS = {
    "data_analyst":       BLUE,
    "analytics_engineer": TEAL,
    "data_engineer":      AMBER,
    "hybrid":             MUTED,
}

TOP_DOMAINS = ["finance", "healthcare", "tech", "government", "media", "retail", "consulting"]

# ── Load & prep ───────────────────────────────────────────────────────────────
df = load_fct_job_postings()

def parse_variant(val):
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return []
    return []

for col in ["tech_stack_required", "tech_stack_preferred"]:
    df[col] = df[col].apply(parse_variant)

salary_df = df.dropna(subset=["final_salary_min", "final_salary_max"]).copy()
salary_df["salary_mid"] = (salary_df["final_salary_min"] + salary_df["final_salary_max"]) / 2

def classify_stack(skills):
    if not isinstance(skills, list):
        return "Neither"
    s = {x.lower() for x in skills}
    if s & MODERN_SKILLS:
        return "Modern Stack"
    if s & TRAD_SKILLS:
        return "Traditional Stack"
    return "Neither"

salary_df["stack_type"] = salary_df["tech_stack_required"].apply(classify_stack)

# ── Page header ───────────────────────────────────────────────────────────────
st.title("📊 Market Insights")
st.caption(
    f"Snapshot of **{len(df)}** NYC data job postings across data analyst, "
    "analytics engineer, and data engineer roles — what the market is asking for and what it pays."
)

# ── KPI strip ─────────────────────────────────────────────────────────────────
ai_pct     = df["acknowledges_ai"].mean()
salary_pct = len(salary_df) / len(df)
remote_pct = (df["work_model"] == "remote").mean()

stack_grp = (
    salary_df[salary_df["stack_type"] != "Neither"]
    .groupby("stack_type")["salary_mid"]
    .median()
)
stack_gap = int(stack_grp.get("Modern Stack", 0) - stack_grp.get("Traditional Stack", 0))

k1, k2, k3, k4 = st.columns(4)
k1.metric("Total Postings", len(df))
k2.metric("Salary Disclosed", f"{salary_pct:.0%}")
k3.metric("Acknowledges AI", f"{ai_pct:.0%}", help="% of postings that explicitly mention AI, LLMs, or related tools")
k4.metric("Modern Stack Premium", f"＄{stack_gap:,}", help="Median salary gap between modern and traditional stack roles")

st.divider()

# ── Row 1: Top Skills + Work Model ────────────────────────────────────────────
col1, col2 = st.columns([1.6, 1])

with col1:
    st.markdown("#### Most In-Demand Skills")
    st.caption("Required tech stack across all postings — colored by stack type")

    all_required = [
        s for row in df["tech_stack_required"]
        if isinstance(row, list)
        for s in row
        if isinstance(s, str)
    ]
    counts = Counter(all_required)
    top = pd.DataFrame(counts.most_common(15), columns=["skill", "count"]).sort_values("count")

    bar_colors = []
    for s in top["skill"]:
        if s.lower() in MODERN_SKILLS:
            bar_colors.append(BLUE)
        elif s.lower() in TRAD_SKILLS:
            bar_colors.append(AMBER)
        else:
            bar_colors.append(MUTED)

    fig1 = go.Figure(go.Bar(
        x=top["count"], y=top["skill"],
        orientation="h",
        marker_color=bar_colors,
        hovertemplate="%{y}: %{x} postings<extra></extra>",
    ))
    fig1.update_layout(
        **CHART_LAYOUT, height=420,
        xaxis=dict(title="# Postings", gridcolor="#1e293b", zeroline=False),
        yaxis=dict(tickfont=dict(size=11)),
        showlegend=False,
    )
    fig1.add_annotation(
        x=1, y=1.04, xref="paper", yref="paper", showarrow=False,
        text=f"<span style='color:{BLUE}'>■</span> Modern stack  "
             f"<span style='color:{AMBER}'>■</span> Traditional stack",
        font=dict(size=10, color="#94a3b8"), xanchor="right",
    )
    st.plotly_chart(fig1, use_container_width=True)

with col2:
    st.markdown("#### Work Model")
    st.caption("Remote / hybrid / onsite split")

    wm = df["work_model"].value_counts().reset_index()
    wm.columns = ["model", "count"]
    WORK_COLORS = {"remote": GREEN, "hybrid": AMBER, "onsite": BLUE}
    wm["color"] = wm["model"].map(lambda x: WORK_COLORS.get(x, MUTED))

    fig2 = go.Figure(go.Pie(
        labels=wm["model"].str.capitalize(),
        values=wm["count"],
        marker=dict(colors=wm["color"].tolist()),
        hole=0.55,
        textinfo="label+percent",
        textfont=dict(size=12),
        hovertemplate="%{label}: %{value} postings<extra></extra>",
    ))
    fig2.update_layout(
        **CHART_LAYOUT, height=420,
        showlegend=False,
        annotations=[dict(
            text=f"<b>{len(df)}</b><br>postings",
            x=0.5, y=0.5, font_size=13, showarrow=False,
            font=dict(color="#cbd5e1"),
        )],
    )
    st.plotly_chart(fig2, use_container_width=True)

st.divider()

st.divider()

# ── Row 2: Stack Salary Gap + AI Blind Spot ───────────────────────────────────
col_left, col_right = st.columns(2)

with col_left:
    st.markdown("#### The AI Blind Spot")
    st.caption("% of postings that explicitly mention AI, LLMs, or related tools — by role type")

    ai_by_query = (
        df.groupby("ingestion_query")["acknowledges_ai"]
        .agg(["mean", "sum", "count"])
        .reset_index()
        .sort_values("mean", ascending=True)
    )
    ai_by_query.columns = ["query", "rate", "yes", "total"]

    fig5 = go.Figure(go.Bar(
        x=ai_by_query["rate"],
        y=ai_by_query["query"],
        orientation="h",
        marker_color=[BLUE, TEAL, AMBER][:len(ai_by_query)],
        text=[f"{r:.0%}" for r in ai_by_query["rate"]],
        textposition="outside",
        customdata=ai_by_query[["yes", "total"]].values,
        hovertemplate="%{y}: %{text} (%{customdata[0]} of %{customdata[1]})<extra></extra>",
    ))
    fig5.update_layout(
        **CHART_LAYOUT, height=300,
        xaxis=dict(title="% Acknowledging AI", gridcolor="#1e293b", zeroline=False, tickformat=".0%", range=[0, 0.8]),
        yaxis=dict(tickfont=dict(size=12)),
    )
    st.plotly_chart(fig5, use_container_width=True)

    overall_ai = df["acknowledges_ai"].mean()
    ai_count = int(df["acknowledges_ai"].sum())
    st.info(
        f"**{overall_ai:.0%} of postings** ({ai_count} of {len(df)} total jobs) explicitly mention AI or LLMs.",
        icon="🤖",
    )

with col_right:
    st.markdown("#### The Stack Salary Gap")
    st.caption("Median salary for postings requiring traditional vs modern tooling")

    stack_plot = (
        salary_df[salary_df["stack_type"] != "Neither"]
        .groupby("stack_type")["salary_mid"]
        .agg(["median", "count"])
        .reset_index()
    )
    stack_plot.columns = ["stack_type", "median", "count"]
    stack_plot["color"] = stack_plot["stack_type"].map({"Modern Stack": BLUE, "Traditional Stack": AMBER})

    fig3 = go.Figure(go.Bar(
        x=stack_plot["stack_type"],
        y=stack_plot["median"],
        marker_color=stack_plot["color"].tolist(),
        text=[f"＄{v/1000:.0f}k" for v in stack_plot["median"]],
        textposition="outside",
        customdata=stack_plot["count"].values,
        hovertemplate="%{x}: ＄%{y:,.0f} median (n=%{customdata})<extra></extra>",
    ))
    fig3.update_layout(
        **CHART_LAYOUT, height=300,
        yaxis=dict(title="Median Salary (＄)", gridcolor="#1e293b", zeroline=False, tickformat="$,.0f"),
    )
    st.plotly_chart(fig3, use_container_width=True)

    if len(stack_plot) == 2:
        mod_med  = stack_plot.loc[stack_plot["stack_type"] == "Modern Stack",  "median"].values[0]
        trad_med = stack_plot.loc[stack_plot["stack_type"] == "Traditional Stack", "median"].values[0]
        delta = int(mod_med - trad_med)
        st.info(
            f"Postings requiring modern stack tooling (dbt, Snowflake, Airflow, Spark, Kafka, Databricks) "
            f"pay **＄{delta:,} more** at the median than those requiring traditional tools "
            f"(Excel, Tableau, Power BI, SQL Server, SAS).",
            icon="💡",
        )

    st.markdown("#### Salary by Role Type")
    st.caption("Median salary by role archetype — where disclosed")

    arch_sal = (
        salary_df.groupby("role_archetype")["salary_mid"]
        .agg(["median", "count"])
        .reset_index()
        .rename(columns={"role_archetype": "archetype", "median": "median", "count": "n"})
    )
    arch_sal = arch_sal[arch_sal["archetype"].isin(ARCHETYPE_LABELS)]
    arch_sal["label"] = arch_sal["archetype"].map(ARCHETYPE_LABELS)
    arch_sal["color"] = arch_sal["archetype"].map(ARCHETYPE_COLORS)
    arch_sal = arch_sal.sort_values("median", ascending=False)

    fig_arch_sal = go.Figure(go.Bar(
        x=arch_sal["label"],
        y=arch_sal["median"],
        marker_color=arch_sal["color"].tolist(),
        text=[f"＄{v/1000:.0f}k" for v in arch_sal["median"]],
        textposition="outside",
        customdata=arch_sal["n"].values,
        hovertemplate="%{x}: ＄%{y:,.0f} median (n=%{customdata} with salary)<extra></extra>",
    ))
    fig_arch_sal.update_layout(
        **CHART_LAYOUT, height=300,
        yaxis=dict(title="Median Salary (＄)", gridcolor="#1e293b", zeroline=False, tickformat="$,.0f"),
    )
    st.plotly_chart(fig_arch_sal, use_container_width=True)

    n_with_sal = len(salary_df)
    st.info(
        f"Based on **{n_with_sal} of {len(df)} postings** ({n_with_sal/len(df):.0%}) with salary data disclosed.",
        icon="💰",
    )

st.divider()

# ── Row 4: Seniority Ladder ───────────────────────────────────────────────────
st.markdown("#### The Seniority Ladder")
listed_df = df[df["listed_seniority"].isin(SENIORITY_ORDER)].copy()
st.caption(f"Do experience requirements and compensation actually stratify by level? Based on source-labeled seniority (n={len(listed_df)}, TheirStack + Built In only)")

col7, col8 = st.columns(2)

sal_listed = salary_df[salary_df["listed_seniority"].isin(SENIORITY_ORDER)].copy()
sal_listed["salary_mid"] = (sal_listed["final_salary_min"] + sal_listed["final_salary_max"]) / 2

with col7:
    yrs = (
        listed_df.dropna(subset=["years_required_min"])
        .groupby("listed_seniority")["years_required_min"]
        .median()
        .reindex(SENIORITY_ORDER)
    )

    fig7 = go.Figure(go.Bar(
        x=[SENIORITY_LABELS[s] for s in SENIORITY_ORDER],
        y=yrs.values,
        marker_color=SENIORITY_COLORS,
        text=[f"{v:.1f} yrs" if not pd.isna(v) else "N/A" for v in yrs.values],
        textposition="outside",
        hovertemplate="%{x}: %{y:.1f} yrs median<extra></extra>",
    ))
    fig7.update_layout(
        **CHART_LAYOUT, height=300,
        title=dict(text="Median Years Required", font=dict(size=13)),
        yaxis=dict(title="Years", gridcolor="#1e293b", zeroline=False),
    )
    st.plotly_chart(fig7, use_container_width=True)

with col8:
    sal = (
        sal_listed.groupby("listed_seniority")["salary_mid"]
        .median()
        .reindex(SENIORITY_ORDER)
    )

    fig8 = go.Figure(go.Bar(
        x=[SENIORITY_LABELS[s] for s in SENIORITY_ORDER],
        y=sal.values,
        marker_color=SENIORITY_COLORS,
        text=[f"＄{v/1000:.0f}k" if not pd.isna(v) else "N/A" for v in sal.values],
        textposition="outside",
        hovertemplate="%{x}: ＄%{y:,.0f} median<extra></extra>",
    ))
    fig8.update_layout(
        **CHART_LAYOUT, height=300,
        title=dict(text="Median Salary (where disclosed)", font=dict(size=13)),
        yaxis=dict(title="Salary (＄)", gridcolor="#1e293b", zeroline=False, tickformat="$,.0f"),
    )
    st.plotly_chart(fig8, use_container_width=True)

st.divider()

# ── Row 5: Where the Jobs Are ─────────────────────────────────────────────────
st.markdown("#### Where the Jobs Are")
st.caption("Industry distribution and role type breakdown across top domains")

col9, col10 = st.columns([1, 1.4])

with col9:
    domain_counts = (
        df["domain"].value_counts()
        .head(10)
        .reset_index()
    )
    domain_counts.columns = ["domain", "count"]
    domain_counts = domain_counts.sort_values("count")

    fig9 = go.Figure(go.Bar(
        x=domain_counts["count"],
        y=domain_counts["domain"].str.capitalize(),
        orientation="h",
        marker_color=BLUE,
        text=domain_counts["count"],
        textposition="outside",
        hovertemplate="%{y}: %{x} postings<extra></extra>",
    ))
    fig9.update_layout(
        **CHART_LAYOUT, height=380,
        xaxis=dict(title="# Postings", gridcolor="#1e293b", zeroline=False),
        yaxis=dict(tickfont=dict(size=11)),
        title=dict(text="Top 10 Industries Hiring", font=dict(size=13)),
    )
    st.plotly_chart(fig9, use_container_width=True)

with col10:
    domain_arch = (
        df[df["domain"].isin(TOP_DOMAINS)]
        .groupby(["domain", "role_archetype"])
        .size()
        .reset_index(name="count")
    )
    domain_arch = domain_arch[domain_arch["role_archetype"].isin(ARCHETYPE_LABELS)]
    domain_arch["domain"] = domain_arch["domain"].str.capitalize()
    domain_arch["role_label"] = domain_arch["role_archetype"].map(ARCHETYPE_LABELS)

    fig10 = go.Figure()
    for archetype, label in ARCHETYPE_LABELS.items():
        subset = domain_arch[domain_arch["role_archetype"] == archetype]
        fig10.add_trace(go.Bar(
            name=label,
            x=subset["domain"],
            y=subset["count"],
            marker_color=ARCHETYPE_COLORS[archetype],
            hovertemplate=f"{label}: %{{y}} postings<extra></extra>",
        ))
    fig10.update_layout(
        **CHART_LAYOUT, height=380,
        barmode="stack",
        title=dict(text="Role Type by Industry", font=dict(size=13)),
        xaxis=dict(gridcolor="#1e293b"),
        yaxis=dict(title="# Postings", gridcolor="#1e293b", zeroline=False),
        legend=dict(orientation="h", y=-0.2, font=dict(size=10)),
    )
    st.plotly_chart(fig10, use_container_width=True)