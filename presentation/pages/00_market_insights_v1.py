"""
pages/01_market_insights.py
Market Insights — high-level snapshot of the NYC data job market.
Five charts based on EDA findings: skills, work model, seniority ladder,
title inflation by seniority, traditional vs modern stack salary comparison.
"""

import sys
import os
import pandas as pd
import plotly.graph_objects as go
from collections import Counter
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from data_loader import load_fct_job_postings

# ── Constants ─────────────────────────────────────────────────────────────────
MODERN_SKILLS  = {"dbt", "snowflake", "airflow", "spark", "kafka", "databricks"}
TRAD_SKILLS    = {"excel", "tableau", "power bi", "sql server", "access", "sas", "stata"}

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

SENIORITY_ORDER = ["entry", "mid", "senior"]
SENIORITY_LABELS = {"entry": "Entry", "mid": "Mid", "senior": "Senior"}

# ── Load ──────────────────────────────────────────────────────────────────────
df = load_fct_job_postings()

# ── Page header ───────────────────────────────────────────────────────────────
st.title("📊 Market Insights")
st.caption(
    f"Snapshot of **{len(df)}** NYC data job postings — "
    "what the market is asking for and what it pays."
)

# ── KPI strip ─────────────────────────────────────────────────────────────────
salary_df = df.dropna(subset=["final_salary_min", "final_salary_max"]).copy()
salary_df["salary_mid"] = (salary_df["final_salary_min"] + salary_df["final_salary_max"]) / 2

k1, k2, k3, k4 = st.columns(4)
k1.metric("Total Postings", len(df))
k2.metric("Salary Disclosed", f"{len(salary_df) / len(df):.0%}")

inflated_rate = df["is_title_inflated"].mean()
k3.metric("Title Inflation Rate", f"{inflated_rate:.0%}", help="% of postings where title implies higher seniority than requirements support")

remote_pct = (df["work_model"] == "remote").mean()
k4.metric("Remote Roles", f"{remote_pct:.0%}")

st.divider()

# ── Row 1: Top Skills + Work Model ────────────────────────────────────────────
col1, col2 = st.columns([1.6, 1])

with col1:
    st.markdown("#### Most In-Demand Skills")
    st.caption("Required tech stack across all postings")

    all_required = [s for row in df["tech_stack_required"] if isinstance(row, list) for s in row if isinstance(s, str)]
    counts = Counter(all_required)
    top = pd.DataFrame(counts.most_common(15), columns=["skill", "count"])
    top = top.sort_values("count")

    # Color modern/traditional skills differently
    bar_colors = []
    for s in top["skill"]:
        if s.lower() in MODERN_SKILLS:
            bar_colors.append(BLUE)
        elif s.lower() in TRAD_SKILLS:
            bar_colors.append(AMBER)
        else:
            bar_colors.append(MUTED)

    fig = go.Figure(go.Bar(
        x=top["count"],
        y=top["skill"],
        orientation="h",
        marker_color=bar_colors,
        hovertemplate="%{y}: %{x} postings<extra></extra>",
    ))
    fig.update_layout(
        **CHART_LAYOUT,
        height=420,
        xaxis=dict(title="# Postings", gridcolor="#1e293b", zeroline=False),
        yaxis=dict(tickfont=dict(size=11)),
        showlegend=False,
    )
    # Legend annotation
    fig.add_annotation(x=1, y=1.04, xref="paper", yref="paper", showarrow=False,
        text=f"<span style='color:{BLUE}'>■</span> Modern stack  "
             f"<span style='color:{AMBER}'>■</span> Traditional stack",
        font=dict(size=10, color="#94a3b8"), xanchor="right")

    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.markdown("#### Work Model")
    st.caption("Remote / hybrid / onsite split")

    wm = df["work_model"].value_counts().reset_index()
    wm.columns = ["model", "count"]

    COLORS = {"remote": GREEN, "hybrid": AMBER, "onsite": BLUE}
    wm["color"] = wm["model"].map(lambda x: COLORS.get(x, MUTED))

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
        **CHART_LAYOUT,
        height=420,
        showlegend=False,
        annotations=[dict(
            text=f"<b>{len(df)}</b><br>postings",
            x=0.5, y=0.5, font_size=13, showarrow=False,
            font=dict(color="#cbd5e1"),
        )],
    )
    st.plotly_chart(fig2, use_container_width=True)

st.divider()

# ── Row 2: Seniority Ladder ───────────────────────────────────────────────────
st.markdown("#### Seniority Ladder")
st.caption("Do experience requirements and compensation actually stratify by level?")

col3, col4 = st.columns(2)

with col3:
    # Years required by seniority
    sen_yrs = df.dropna(subset=["inferred_seniority", "years_required_min"])
    sen_yrs = sen_yrs[sen_yrs["inferred_seniority"].isin(SENIORITY_ORDER)]

    medians = (
        sen_yrs.groupby("inferred_seniority")["years_required_min"]
        .median()
        .reindex(SENIORITY_ORDER)
    )
    counts_sen = sen_yrs["inferred_seniority"].value_counts().reindex(SENIORITY_ORDER)

    fig3 = go.Figure(go.Bar(
        x=[SENIORITY_LABELS[s] for s in SENIORITY_ORDER],
        y=medians.values,
        marker_color=[GREEN, BLUE, AMBER],
        text=[f"{v:.1f} yrs" for v in medians.values],
        textposition="outside",
        hovertemplate="%{x}: %{y:.1f} yrs median<extra></extra>",
    ))
    fig3.update_layout(
        **CHART_LAYOUT,
        height=300,
        title=dict(text="Median Years Required", font=dict(size=13)),
        yaxis=dict(title="Years", gridcolor="#1e293b", zeroline=False),
        xaxis=dict(gridcolor="#1e293b"),
    )
    st.plotly_chart(fig3, use_container_width=True)

with col4:
    # Salary by seniority
    sal_sen = salary_df[salary_df["inferred_seniority"].isin(SENIORITY_ORDER)]
    sal_medians = (
        sal_sen.groupby("inferred_seniority")["salary_mid"]
        .median()
        .reindex(SENIORITY_ORDER)
    )

    fig4 = go.Figure(go.Bar(
        x=[SENIORITY_LABELS[s] for s in SENIORITY_ORDER],
        y=sal_medians.values,
        marker_color=[GREEN, BLUE, AMBER],
        text=[f"＄{v/1000:.0f}k" for v in sal_medians.values],
        textposition="outside",
        hovertemplate="%{x}: ＄%{y:,.0f}<extra></extra>",
    ))
    fig4.update_layout(
        **CHART_LAYOUT,
        height=300,
        title=dict(text="Median Salary (where disclosed)", font=dict(size=13)),
        yaxis=dict(
            title="Salary (＄)",
            gridcolor="#1e293b",
            zeroline=False,
            tickformat="$,.0f",
        ),
    )
    st.plotly_chart(fig4, use_container_width=True)

st.divider()

# ── Row 3: Title Inflation + Stack Salary ─────────────────────────────────────
col5, col6 = st.columns(2)

with col5:
    st.markdown("#### Title Inflation by Seniority")
    st.caption("% of postings where the title implies higher seniority than requirements support")

    inf_df = df[df["inferred_seniority"].isin(SENIORITY_ORDER)].copy()
    inf_grp = (
        inf_df.groupby("inferred_seniority")["is_title_inflated"]
        .agg(["sum", "count"])
        .reindex(SENIORITY_ORDER)
    )
    inf_grp["rate"] = inf_grp["sum"] / inf_grp["count"]

    bar_colors_inf = []
    for r in inf_grp["rate"]:
        if r >= 0.4:
            bar_colors_inf.append(RED)
        elif r >= 0.1:
            bar_colors_inf.append(AMBER)
        else:
            bar_colors_inf.append(GREEN)

    fig5 = go.Figure(go.Bar(
        x=[SENIORITY_LABELS[s] for s in SENIORITY_ORDER],
        y=inf_grp["rate"].values,
        marker_color=bar_colors_inf,
        text=[f"{r:.0%}" for r in inf_grp["rate"].values],
        textposition="outside",
        customdata=inf_grp[["sum", "count"]].values,
        hovertemplate="%{x}: %{text} inflated (%{customdata[0]:.0f} of %{customdata[1]:.0f})<extra></extra>",
    ))
    fig5.update_layout(
        **CHART_LAYOUT,
        height=320,
        yaxis=dict(
            title="Inflation Rate",
            gridcolor="#1e293b",
            zeroline=False,
            tickformat=".0%",
            range=[0, 0.75],
        ),
    )
    st.plotly_chart(fig5, use_container_width=True)

    senior_rate = inf_grp.loc["senior", "rate"] if "senior" in inf_grp.index else 0
    if senior_rate >= 0.4:
        st.info(
            f"**{senior_rate:.0%} of senior-titled postings** have requirements that "
            "only support mid-level seniority — the title is doing more work than the job.",
            icon="🚩",
        )

with col6:
    st.markdown("#### Traditional vs Modern Stack: Salary Gap")
    st.caption("Median salary for postings requiring traditional vs modern tooling")

    salary_df2 = salary_df.copy()
    salary_df2["stack_type"] = salary_df2["tech_stack_required"].apply(
        lambda skills: (
            "Modern Stack" if any(s.lower() in MODERN_SKILLS for s in skills)
            else "Traditional Stack" if any(s.lower() in TRAD_SKILLS for s in skills)
            else "Neither"
        ) if isinstance(skills, list) else "Neither"
    )

    stack_grp = (
        salary_df2[salary_df2["stack_type"] != "Neither"]
        .groupby("stack_type")["salary_mid"]
        .agg(["median", "count"])
        .reset_index()
    )
    stack_grp.columns = ["stack_type", "median", "count"]

    color_map = {"Modern Stack": BLUE, "Traditional Stack": AMBER}
    stack_grp["color"] = stack_grp["stack_type"].map(color_map)

    fig6 = go.Figure(go.Bar(
        x=stack_grp["stack_type"],
        y=stack_grp["median"],
        marker_color=stack_grp["color"].tolist(),
        text=[f"＄{v/1000:.0f}k" for v in stack_grp["median"]],
        textposition="outside",
        customdata=stack_grp["count"].values,
        hovertemplate="%{x}: ＄%{y:,.0f} median (n=%{customdata})<extra></extra>",
    ))
    fig6.update_layout(
        **CHART_LAYOUT,
        height=320,
        yaxis=dict(
            title="Median Salary (＄)",
            gridcolor="#1e293b",
            zeroline=False,
            tickformat="$,.0f",
        ),
    )
    st.plotly_chart(fig6, use_container_width=True)

    if len(stack_grp) == 2:
        mod_med  = stack_grp.loc[stack_grp["stack_type"] == "Modern Stack",    "median"].values
        trad_med = stack_grp.loc[stack_grp["stack_type"] == "Traditional Stack","median"].values
        if len(mod_med) and len(trad_med):
            delta = int(mod_med[0] - trad_med[0])
            direction = "higher" if delta > 0 else "lower"
            st.info(
                f"Modern stack roles pay **＄{abs(delta):,} {direction}** at the median "
                f"than traditional stack roles.",
                icon="💡",
            )
