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
from data_loader import load_fct_job_postings, format_source, load_pipeline_runs, load_api_usage

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

# # ── Title inflation summary ───────────────────────────────────────────────────
# st.markdown("#### Title Inflation Detector")
# inf_col1, inf_col2 = st.columns([1, 2])

# with inf_col1:
#     fig_inf = go.Figure(go.Indicator(
#         mode="gauge+number",
#         value=inflation_rate * 100,
#         title={"text": "Inflation Rate"},
#         number={"suffix": "%", "font": {"size": 40}},
#         gauge={
#             "axis": {"range": [0, 50]},
#             "bar": {"color": "#ef4444"},
#             "steps": [
#                 {"range": [0, 10], "color": "#dcfce7"},
#                 {"range": [10, 25], "color": "#fef9c3"},
#                 {"range": [25, 50], "color": "#fee2e2"},
#             ],
#             "threshold": {
#                 "line": {"color": "#991b1b", "width": 3},
#                 "thickness": 0.75,
#                 "value": inflation_rate * 100,
#             },
#         },
#     ))
#     fig_inf.update_layout(height=260, margin=dict(l=20, r=20, t=40, b=0))
#     st.plotly_chart(fig_inf, use_container_width=True)
#     st.caption(f"{inflated_count} of {total_rows} postings flagged")

# with inf_col2:
#     inflated_df = df[df["is_title_inflated"] == True][
#         ["job_title", "company_name", "role_archetype", "inferred_seniority", "inflation_reasoning"]
#     ].copy()
#     inflated_df.columns = ["Title", "Company", "Archetype", "Seniority", "Reasoning"]
#     if len(inflated_df) > 0:
#         st.dataframe(inflated_df.reset_index(drop=True), use_container_width=True, height=220, hide_index=True)
#     else:
#         st.info("No title inflation detected in current dataset.")

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

# ── API Usage Tracking ────────────────────────────────────────────────────────
st.markdown("#### API Credit Usage")

try:
    runs_df = load_pipeline_runs()
    usage_df = load_api_usage()
    tracking_available = len(runs_df) > 0
except Exception as e:
    st.warning(f"Could not load pipeline tracking data: {e}")
    tracking_available = False

if tracking_available:

    # calculate per-run credits burned by diffing consecutive rows per source
    usage_df = usage_df.sort_values(["source", "run_at"]).reset_index(drop=True)
    usage_df["credits_this_run"] = usage_df.groupby("source")["credits_used"].diff()
    # for the first run of each source, diff() returns NaN — use credits_used directly
    usage_df["credits_this_run"] = usage_df["credits_this_run"].fillna(usage_df["credits_used"])

    # ── Current credit status ─────────────────────────────────────────────
    st.markdown("##### Current Credit Status")

    latest_usage = usage_df.sort_values("run_at").groupby("source").last().reset_index()

    SOURCE_COLORS = {"jsearch": "#3b82f6", "theirstack": "#10b981"}

    status_cols = st.columns(len(latest_usage))
    for i, (_, row) in enumerate(latest_usage.iterrows()):
        src = row["source"]
        remaining = row["credits_remaining"]
        limit = row["credits_limit"] or 200
        used = row["credits_used"]
        reset = row["reset_date"]
        pct_remaining = remaining / limit if limit else 0

        if pct_remaining > 0.5:
            health_color = "#22c55e"
            health_label = "Healthy"
        elif pct_remaining > 0.25:
            health_color = "#f59e0b"
            health_label = "Monitor"
        else:
            health_color = "#ef4444"
            health_label = "Low"

        with status_cols[i]:
            st.markdown(
                f"""
                <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px; padding:16px 20px;">
                    <div style="font-size:0.75rem; color:#64748b; text-transform:uppercase; letter-spacing:0.05em; margin-bottom:8px;">
                        {format_source(src)}
                    </div>
                    <div style="font-size:2rem; font-weight:700; color:#0f172a; line-height:1.1;">
                        {remaining}
                        <span style="font-size:1rem; color:#64748b; font-weight:400;">/ {limit}</span>
                    </div>
                    <div style="font-size:0.8rem; color:#64748b; margin-top:4px;">credits remaining</div>
                    <div style="background:#e2e8f0; border-radius:99px; height:6px; margin:10px 0;">
                        <div style="background:{SOURCE_COLORS.get(src, '#94a3b8')}; width:{pct_remaining*100:.0f}%; height:6px; border-radius:99px;"></div>
                    </div>
                    <div style="display:flex; justify-content:space-between; font-size:0.75rem;">
                        <span style="color:{health_color}; font-weight:600;">{health_label}</span>
                        <span style="color:#94a3b8;">Resets {reset}</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("")

    # ── Usage over time ───────────────────────────────────────────────────
    st.markdown("##### Usage & Jobs Per Run")
    usage_time_col1, usage_time_col2 = st.columns(2)

    with usage_time_col1:
        fig_credits = go.Figure()
        for src, color in SOURCE_COLORS.items():
            src_data = usage_df[usage_df["source"] == src].sort_values("run_at")
            if len(src_data) > 0:
                fig_credits.add_bar(
                    x=src_data["run_at"].dt.strftime("%b %d %H:%M"),
                    y=src_data["credits_this_run"],
                    name=format_source(src),
                    marker_color=color,
                )
        fig_credits.update_layout(
            title="Credits Used Per Run",
            barmode="group",
            margin=dict(l=0, r=0, t=40, b=0),
            height=280,
            plot_bgcolor="white",
            paper_bgcolor="white",
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            yaxis_title="Credits Used",
        )
        st.plotly_chart(fig_credits, use_container_width=True)

    with usage_time_col2:
        fig_jobs = go.Figure()
        for col, color, label in [
            ("jsearch_rows", "#3b82f6", "JSearch"),
            ("theirstack_rows", "#10b981", "TheirStack"),
            ("builtin_rows", "#f59e0b", "Built In NYC"),
        ]:
            fig_jobs.add_bar(
                x=runs_df["run_at"].dt.strftime("%b %d %H:%M"),
                y=runs_df[col],
                name=label,
                marker_color=color,
            )
        fig_jobs.update_layout(
            title="Jobs Collected Per Run",
            barmode="stack",
            margin=dict(l=0, r=0, t=40, b=0),
            height=280,
            plot_bgcolor="white",
            paper_bgcolor="white",
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            yaxis_title="Jobs",
        )
        st.plotly_chart(fig_jobs, use_container_width=True)

    # ── Efficiency table ──────────────────────────────────────────────────
    st.markdown("##### Run History & Efficiency")

    efficiency_rows = []
    for _, run_row in runs_df.iterrows():
        run_id = run_row["run_id"]
        run_usage = usage_df[usage_df["run_id"] == run_id]
        total_credits = run_usage["credits_this_run"].sum() if len(run_usage) > 0 else 0
        total_jobs = run_row["total_rows"]
        cpp = round(total_credits / total_jobs, 2) if total_jobs > 0 else None
        efficiency_rows.append({
            "Run": run_row["run_at"].strftime("%b %d, %Y %H:%M"),
            "Status": run_row["status"],
            "JSearch": run_row["jsearch_rows"],
            "TheirStack": run_row["theirstack_rows"],
            "Built In": run_row["builtin_rows"],
            "Total Jobs": total_jobs,
            "Credits Used": int(total_credits) if total_credits else "—",
            "Credits / Job": cpp if cpp else "—",
            "Duration (s)": round(run_row["duration_seconds"], 1),
        })

    st.dataframe(
        pd.DataFrame(efficiency_rows),
        use_container_width=True,
        hide_index=True,
    )

    # ── Forecast ──────────────────────────────────────────────────────────
    st.markdown("##### Credit Forecast")

    for src in ["jsearch", "theirstack"]:
        src_usage = usage_df[usage_df["source"] == src].sort_values("run_at")

        if len(src_usage) == 0:
            st.caption(f"{format_source(src)}: No usage data recorded yet.")
            continue

        latest = src_usage.iloc[-1]
        remaining = latest["credits_remaining"]
        reset = latest["reset_date"]

        # Filter to current window only — avoid diff() crossing a reset boundary
        # Window start = 1 month before reset date
        try:
            reset_dt = pd.to_datetime(reset)
            window_start = reset_dt - pd.DateOffset(months=1)
            src_usage_window = src_usage[src_usage["run_at"] >= window_start]
        except Exception:
            # If reset date parsing fails, use all data
            src_usage_window = src_usage

        if len(src_usage_window) < 2:
            st.caption(
                f"{format_source(src)}: Need at least 2 runs in the current window to forecast — "
                f"{len(src_usage_window)} run{'s' if len(src_usage_window) != 1 else ''} recorded so far."
            )
            continue

        src_usage_window = src_usage_window.copy()
        src_usage_window["credits_burned"] = src_usage_window["credits_used"].diff()
        avg_burn = src_usage_window["credits_burned"].dropna().mean()
        runs_left = int(remaining / avg_burn) if avg_burn > 0 else "∞"

        st.markdown(
            f"**{format_source(src)}** — {remaining} credits remaining, "
            f"avg burn {avg_burn:.1f} credits/run, "
            f"~{runs_left} runs until limit, resets {reset}"
        )

else:
    st.info("No pipeline tracking data yet — will populate after the next run.")