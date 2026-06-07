"""
pages/02_job_explorer.py
Job Explorer — filterable grid + expandable row detail panel.
The "Job Truth-Finder": shows raw job postings alongside the LLM-enriched metadata.
"""

import sys
import os
import json
import pandas as pd
import streamlit as st
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from data_loader import load_fct_job_postings, format_salary

# ── Load data ─────────────────────────────────────────────────────────────────
df_full = load_fct_job_postings()

st.title("🔍 Job Explorer")
st.caption(
    "Filter, search, and inspect every posting — including the AI-extracted metadata "
    "layered on top of each raw description."
)

# ── Sidebar filters ───────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Filters")

    # Tech stacks
    tech_counts = Counter(
        t for row in df_full["tech_stack_required"] + df_full["tech_stack_preferred"]
        if isinstance(row, list)
        for t in row
        if isinstance(t, str)
    )
    all_techs = [tech for tech, _ in tech_counts.most_common()]
    sel_techs = st.multiselect(
        "Tech Stack",
        options=all_techs,
        default=[],
        placeholder="Any technology",
    )

    # Role archetype
    def fmt_snake_case(val: str) -> str:
        return val.replace("_", " ") if val else val

    raw_archetypes = sorted(df_full["role_archetype"].dropna().unique().tolist())
    sel_archetypes = st.multiselect(
        "Role Archetype",
        options=raw_archetypes,
        format_func=fmt_snake_case,
        default=[],
        placeholder="All archetypes",
    )

    # Work model
    work_models = sorted(df_full["work_model"].dropna().unique().tolist())
    sel_work_models = st.multiselect(
        "Work Model",
        options=work_models,
        default=[],
        placeholder="All models",
    )

    # Employment type
    emp_types = sorted(df_full["employment_type"].dropna().unique().tolist())
    sel_emp_types = st.multiselect(
        "Employment Type",
        options=emp_types,
        default=[],
        placeholder="All types",
    )

    # Source
    def fmt_source(val: str) -> str:
        overrides = {
            "builtin": "Built In NYC",
            "jsearch": "JSearch",
            "theirstack": "TheirStack",
        }
        return overrides.get(val, val) if val else val
    sources = sorted(df_full["source"].dropna().unique().tolist())
    sel_sources = st.multiselect(
        "Source",
        options=sources,
        format_func=fmt_source,
        default=[],
        placeholder="All sources",
    )

    degree_opts = sorted(df_full["degree_requirement"].dropna().unique().tolist())
    sel_degrees = st.multiselect(
        "Degree Requirement",
        options=degree_opts,
        format_func=fmt_snake_case,
        default=[],
        placeholder="Any requirement",
    )

    # Salary slider — only over rows that have salary data
    salary_df = df_full.dropna(subset=["final_salary_min", "final_salary_max"])
    # Cap at 300k to avoid outlier distortion on the slider
    sal_min_overall = int(salary_df["final_salary_min"].min()) if len(salary_df) else 0
    sal_max_overall = min(int(salary_df["final_salary_max"].max()), 300_000) if len(salary_df) else 300_000

    salary_range = st.slider(
        "Salary Range (where disclosed)",
        min_value=sal_min_overall,
        max_value=sal_max_overall,
        value=(sal_min_overall, sal_max_overall),
        step=5_000,
        format="$%d",
    )

    # Date posted range
    if df_full["date_posted"].notna().any():
        date_min = df_full["date_posted"].min().date()
        date_max = df_full["date_posted"].max().date()
        date_range = st.date_input(
            "Date Posted",
            value=(date_min, date_max),
            min_value=date_min,
            max_value=date_max,
        )
    else:
        date_range = None

    # Title search
    title_search = st.text_input(
        "Search Title / Company",
        placeholder="e.g. analyst, Stripe",
    ).strip().lower()

    # Title inflation flag
    show_inflated_only = st.checkbox("Show inflated titles only")

    st.divider()
    # if st.button("Clear all filters", use_container_width=True):
    #     st.rerun()
    if st.button("Clear all filters", use_container_width=True):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

# ── Apply filters ─────────────────────────────────────────────────────────────
df = df_full.copy()

if sel_archetypes:
    df = df[df["role_archetype"].isin(sel_archetypes)]
if sel_work_models:
    df = df[df["work_model"].isin(sel_work_models)]
if sel_emp_types:
    df = df[df["employment_type"].isin(sel_emp_types)]
if sel_sources:
    df = df[df["source"].isin(sel_sources)]
if sel_degrees:
    df = df[df["degree_requirement"].isin(sel_degrees)]

# Salary filter — only restrict rows that have salary data; pass through nulls
salary_filter_active = (
    salary_range[0] > sal_min_overall or salary_range[1] < sal_max_overall
)
if salary_filter_active:
    has_salary = df["final_salary_min"].notna() & df["final_salary_max"].notna()
    in_salary_range = (
        (df["final_salary_min"] >= salary_range[0]) &
        (df["final_salary_max"] <= salary_range[1])
    )
    df = df[~has_salary | in_salary_range]

# Date filter
if date_range and len(date_range) == 2:
    date_start = pd.Timestamp(date_range[0])
    date_end = pd.Timestamp(date_range[1]) + pd.Timedelta(days=1)
    df = df[df["date_posted"].isna() | (
        (df["date_posted"] >= date_start) & (df["date_posted"] < date_end)
    )]

# Tech stack filter
if sel_techs:
    def has_selected_tech(row):
        combined = (row.get("tech_stack_required") or []) + (row.get("tech_stack_preferred") or [])
        return any(t in sel_techs for t in combined if isinstance(t, str))
    df = df[df.apply(has_selected_tech, axis=1)]

# Title / company search
if title_search:
    mask = (
        df["job_title"].str.lower().str.contains(title_search, na=False) |
        df["company_name"].str.lower().str.contains(title_search, na=False)
    )
    df = df[mask]

# Inflation filter
if show_inflated_only:
    df = df[df["is_title_inflated"] == True]

# ── Summary bar ───────────────────────────────────────────────────────────────
total = len(df_full)
filtered = len(df)
st.markdown(
    f"Showing **{filtered}** of **{total}** postings",
    help="Filters are applied cumulatively. Salary filter passes through rows with no salary data.",
)

if filtered == 0:
    st.warning("No postings match the current filters.")
    st.stop()

# ── Grid display ──────────────────────────────────────────────────────────────

# Build display dataframe for the grid
def make_display_df(df: pd.DataFrame) -> pd.DataFrame:
    display = pd.DataFrame()
    display["Title"] = df["job_title"].fillna("—")
    display["Company"] = df["company_name"].fillna("—")
    display["Archetype"] = df["role_archetype"].apply(
        lambda x: x.replace("_", " ") if pd.notna(x) and x else "—"
    )
    display["Work Model"] = df["work_model"].fillna("—")
    display["Source"] = df["source"].apply(lambda x: fmt_source(x) if pd.notna(x) else "—")
    display["Salary"] = df.apply(
        lambda r: format_salary(r["final_salary_min"], r["final_salary_max"]), axis=1
    )
    display["Posted"] = df["date_posted"].dt.strftime("%b %d, %Y").fillna("—")
    # Keep job_id as hidden key for row linking
    display["_job_id"] = df["job_id"].values
    display["_idx"] = df.index.values
    return display


display_df = make_display_df(df)

# Show grid — hide _job_id and _idx from column display
visible_cols = ["Title", "Company", "Archetype", "Work Model", "Source", "Salary", "Posted"]

# Selection via selectbox (simpler and reliable across Streamlit versions)
st.markdown("#### Postings")

# Render the display table
st.dataframe(
    display_df[visible_cols].reset_index(drop=True),
    use_container_width=True,
    hide_index=True,
    height=320,
)

# Row selector
st.markdown("#### Inspect a Posting")
row_labels = [
    f"{i+1}. {row['Title']} @ {row['Company']}"
    for i, row in display_df[visible_cols].iterrows()
]
selected_label = st.selectbox(
    "Select a posting to inspect",
    options=row_labels,
    index=0,
    label_visibility="collapsed",
)
selected_pos = row_labels.index(selected_label)
selected_job_id = display_df.iloc[selected_pos]["_job_id"]

# Fetch the full row from the original df
job = df[df["job_id"] == selected_job_id].iloc[0]

# ── Detail panel ──────────────────────────────────────────────────────────────
st.divider()

def tag_pills(items: list, css_class: str = "tag-blue") -> str:
    if not items:
        return "<span style='color:#94a3b8; font-size:0.8rem;'>None listed</span>"
    return " ".join(
        f'<span class="tag-pill {css_class}">{t}</span>'
        for t in items if isinstance(t, str)
    )


col_left, col_right = st.columns([1.1, 1])

with col_left:
    # Header
    inflation_badge = ""
    if job.get("is_title_inflated"):
        inflation_badge = ' <span class="tag-pill tag-red">🚩 Title Inflated</span>'

    st.markdown(
        f"<h3 style='margin-bottom:2px'>{job['job_title']}{inflation_badge}</h3>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div style='font-size:1.05rem; color:#475569; margin-bottom:12px'>"
        f"<strong>{job['company_name']}</strong>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # Core metadata pills
    wm_color = {"remote": "tag-green", "hybrid": "tag-amber", "onsite": "tag-blue"}.get(
        str(job.get("work_model", "")).lower(), "tag-gray"
    )
    et_color = "tag-blue" if str(job.get("employment_type", "")) == "full_time" else "tag-gray"
    src_color = "tag-purple"

    meta_html = (
        f'<span class="tag-pill {wm_color}">{job.get("work_model", "—")}</span>'
        f'<span class="tag-pill {et_color}">{str(job.get("employment_type","—")).replace("_"," ")}</span>'
        f'<span class="tag-pill {src_color}">{fmt_source(job.get("source","—"))}</span>'
    )
    st.markdown(meta_html, unsafe_allow_html=True)

    st.markdown("")

    # Quick stats grid
    qc1, qc2, qc3 = st.columns(3)
    with qc1:
        st.metric("Salary", format_salary(job.get("final_salary_min"), job.get("final_salary_max")))
    with qc2:
        posted = job.get("date_posted")
        st.metric("Posted", posted.strftime("%b %d, %Y") if pd.notna(posted) else "—")
    with qc3:
        city = job.get("city")
        state = job.get("state")
        location = f"{city}, {state}" if city and state else (city or state or "Remote / Unknown")
        st.metric("Location", location)

    st.markdown("")

    # LLM enrichment section
    st.markdown("##### 🔩 AI Enrichment")

    arch = str(job.get("role_archetype") or "—").replace("_", " ").title()
    focus = str(job.get("work_focus") or "—").replace("_", " ").title()
    seniority = str(job.get("inferred_seniority") or "—").replace("_", " ").title()
    degree = str(job.get("degree_requirement") or "—").replace("_", " ").title()
    confidence = job.get("confidence_score")
    conf_str = f"{confidence:.0%}" if pd.notna(confidence) else "—"

    yr_min = job.get("years_required_min")
    yr_max = job.get("years_required_max")
    if pd.notna(yr_min) and pd.notna(yr_max):
        yoe_str = f"{int(yr_min)}–{int(yr_max)} yrs"
    elif pd.notna(yr_min):
        yoe_str = f"{int(yr_min)}+ yrs"
    elif pd.notna(yr_max):
        yoe_str = f"up to {int(yr_max)} yrs"
    else:
        yoe_str = "Not specified"

    enrich_cols = st.columns(2)
    with enrich_cols[0]:
        st.markdown(f"**Archetype:** {arch}")
        st.markdown(f"**Work Focus:** {focus}")
        st.markdown(f"**Seniority:** {seniority}")
    with enrich_cols[1]:
        st.markdown(f"**Degree Req:** {degree}")
        st.markdown(f"**YoE Required:** {yoe_str}")
        st.markdown(f"**Confidence:** {conf_str}")

    # Title inflation reasoning
    if job.get("is_title_inflated") and job.get("inflation_reasoning"):
        st.markdown("")
        st.warning(f"**Inflation Note:** {job['inflation_reasoning']}", icon="🚩")

    st.markdown("")

    # Tech stack
    st.markdown("##### 🛠 Tech Stack")
    ts_req = job.get("tech_stack_required") or []
    ts_pref = job.get("tech_stack_preferred") or []

    st.markdown(
        f"**Required:** {tag_pills(ts_req, 'tag-blue')}",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"**Preferred:** {tag_pills(ts_pref, 'tag-gray')}",
        unsafe_allow_html=True,
    )

    st.markdown("")

    # Paradigms
    st.markdown("##### 🧠 Paradigms & Methods")
    par_req = job.get("paradigms_required") or []
    par_pref = job.get("paradigms_preferred") or []

    st.markdown(
        f"**Required:** {tag_pills(par_req, 'tag-green')}",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"**Preferred:** {tag_pills(par_pref, 'tag-gray')}",
        unsafe_allow_html=True,
    )

    st.markdown("")

    # Apply link
    job_url = job.get("job_url")
    if job_url:
        st.link_button("Apply / View Original Posting →", job_url, use_container_width=True)

with col_right:
    st.markdown("##### 📄 Full Job Description")
    st.markdown(
        "<div style='font-size:0.8rem; color:#94a3b8; margin-bottom:8px;'>"
        "Raw description as ingested — AI metadata extracted from this text."
        "</div>",
        unsafe_allow_html=True,
    )
    desc = job.get("description") or "No description available."
    st.text_area(
        label="description",
        value=desc,
        height=600,
        label_visibility="collapsed",
        disabled=True,
    )