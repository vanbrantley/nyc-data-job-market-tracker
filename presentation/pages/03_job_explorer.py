"""
pages/03_job_explorer.py
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
from data_loader import load_fct_job_postings, format_salary, format_source, format_seniority, format_label


DEGREE_LABELS = {
    "none": "No Degree Required",
    "bachelors": "Bachelor's",
    "masters": "Master's",
    "equivalent_ok": "Experience Accepted",
}

# ── Load data ─────────────────────────────────────────────────────────────────
df_full = load_fct_job_postings()
df_full = df_full[df_full["title_role_bucket"] != "no_match"]

st.title("🔍 Job Explorer")
st.caption(
    "Filter, search, and inspect every posting — including the AI-extracted metadata "
    "layered on top of each raw description."
)

# ── Sidebar filters ───────────────────────────────────────────────────────────
FILTER_KEYS = [
    "filter_techs", "filter_roles", "filter_work_models",
    "filter_emp_types", "filter_sources", "filter_degrees",
    "filter_salary", "filter_date_preset", "filter_title", "filter_salary_only",
    "filter_listed_seniority", "filter_listed_seniority_only", "filter_inferred_seniority",
    "filter_domain", "filter_acknowledges_ai", "filter_encourages_applicants",
]

salary_df = df_full.dropna(subset=["final_salary_min", "final_salary_max"])
sal_min_overall = int(salary_df["final_salary_min"].min()) if len(salary_df) else 0
sal_max_overall = min(int(salary_df["final_salary_max"].max()), 300_000) if len(salary_df) else 300_000

with st.sidebar:
    st.markdown("### Filters")

    if st.session_state.get("pending_clear"):
        st.session_state["filter_techs"] = []
        st.session_state["filter_roles"] = []
        st.session_state["filter_work_models"] = []
        st.session_state["filter_emp_types"] = []
        st.session_state["filter_sources"] = []
        st.session_state["filter_degrees"] = []
        st.session_state["filter_salary"] = (sal_min_overall, sal_max_overall)
        st.session_state["filter_date_preset"] = "All Time"
        st.session_state["filter_title"] = ""
        st.session_state["filter_salary_only"] = False
        st.session_state["filter_listed_seniority"] = []
        st.session_state["filter_listed_seniority_only"] = False
        st.session_state["filter_inferred_seniority"] = []
        st.session_state["filter_domain"] = []
        st.session_state["filter_acknowledges_ai"] = False
        st.session_state["filter_encourages_applicants"] = False
        st.session_state["pending_clear"] = False

    # Date posted — quick presets
    date_preset = st.radio(
        "Date Posted",
        options=["All Time", "Past 3 Days", "Past Week", "Past Month"],
        index=0,
        key="filter_date_preset",
    )

    if date_preset == "All Time":
        date_range = None
    else:
        days_map = {"Past 3 Days": 3, "Past Week": 7, "Past Month": 30}
        cutoff = pd.Timestamp.now().normalize() - pd.Timedelta(days=days_map[date_preset])
        date_range = (cutoff.date(), pd.Timestamp.now().date())

    # Role (classified from job title)
    role_opts = sorted(df_full["title_role_bucket"].dropna().unique().tolist())
    sel_roles = st.multiselect(
        "Role",
        options=role_opts,
        default=[],
        placeholder="All roles",
        key="filter_roles"
    )

    # Listed seniority
    listed_sen_opts = sorted(df_full["listed_seniority"].dropna().unique().tolist())
    sel_listed_seniority = st.multiselect(
        "Listed Seniority",
        options=listed_sen_opts,
        format_func=format_seniority,
        default=[],
        placeholder="All seniority levels",
        key="filter_listed_seniority"
    )

    # LLM inferred seniority
    inferred_sen_opts = sorted(df_full["inferred_seniority"].dropna().unique().tolist())
    sel_inferred_seniority = st.multiselect(
        "LLM Inferred Seniority",
        options=inferred_sen_opts,
        format_func=format_seniority,
        default=[],
        placeholder="All seniority levels",
        key="filter_inferred_seniority"
    )

    # Salary slider
    salary_range = st.slider(
        "Salary Range (where disclosed)",
        min_value=sal_min_overall,
        max_value=sal_max_overall,
        value=(sal_min_overall, sal_max_overall),
        step=5_000,
        format="$%d",
        key="filter_salary"
    )

    # Degree requirement
    degree_opts = sorted(df_full["degree_requirement"].dropna().unique().tolist())
    sel_degrees = st.multiselect(
        "Degree Requirement",
        options=degree_opts,
        format_func=lambda x: DEGREE_LABELS.get(x, format_label(x)),
        default=[],
        placeholder="Any requirement",
        key="filter_degrees"
    )

    # Work model
    work_models = sorted(df_full["work_model"].dropna().unique().tolist())
    sel_work_models = st.multiselect(
        "Work Model",
        options=work_models,
        format_func=format_label,
        default=[],
        placeholder="All models",
        key="filter_work_models"
    )

    # Industry
    domain_opts = sorted(df_full["domain"].dropna().unique().tolist())
    sel_domain = st.multiselect(
        "Industry",
        options=domain_opts,
        format_func=lambda x: x.capitalize(),
        default=[],
        placeholder="All industries",
        key="filter_domain"
    )

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
        key="filter_techs"
    )

    # Employment type
    emp_types = sorted(df_full["employment_type"].dropna().unique().tolist())
    sel_emp_types = st.multiselect(
        "Employment Type",
        options=emp_types,
        format_func=format_label,
        default=[],
        placeholder="All types",
        key="filter_emp_types"
    )

    # Source
    sources = sorted(df_full["source"].dropna().unique().tolist())
    sel_sources = st.multiselect(
        "Source",
        options=sources,
        format_func=format_source,
        default=[],
        placeholder="All sources",
        key="filter_sources"
    )

    # Title search
    title_search = st.text_input(
        "Search Title / Company",
        placeholder="e.g. analyst, Stripe",
        key="filter_title"
    ).strip().lower()

    # Acknowledges AI
    sel_acknowledges_ai = st.checkbox(
        "Acknowledges AI",
        value=False,
        key="filter_acknowledges_ai"
    )

    salary_only = st.checkbox(
        "Show jobs with salary data only",
        value=False,
        key="filter_salary_only"
    )

    listed_seniority_only = st.checkbox(
        "Show jobs with listed seniority only",
        value=False,
        key="filter_listed_seniority_only"
    )

    # Explicitly encourages applicants
    sel_encourages = st.checkbox(
        "Encourages Underqualified Applicants",
        value=False,
        key="filter_encourages_applicants"
    )

    st.divider()
    if st.button("Clear all filters", use_container_width=True):
        st.session_state["pending_clear"] = True
        st.rerun()

# ── Apply filters ─────────────────────────────────────────────────────────────
df = df_full.copy()

if sel_roles:
    df = df[df["title_role_bucket"].isin(sel_roles)]
if sel_work_models:
    df = df[df["work_model"].isin(sel_work_models)]
if sel_emp_types:
    df = df[df["employment_type"].isin(sel_emp_types)]
if sel_sources:
    df = df[df["source"].isin(sel_sources)]
if sel_degrees:
    df = df[df["degree_requirement"].isin(sel_degrees)]
if sel_listed_seniority:
    df = df[df["listed_seniority"].isin(sel_listed_seniority)]
if sel_inferred_seniority:
    df = df[df["inferred_seniority"].isin(sel_inferred_seniority)]
if sel_domain:
    df = df[df["domain"].isin(sel_domain)]
if sel_acknowledges_ai:
    df = df[df["acknowledges_ai"] == True]
if sel_encourages:
    df = df[df["explicitly_encourages_applicants"] == True]

# Salary filter
salary_filter_active = (
    salary_range[0] > sal_min_overall or salary_range[1] < sal_max_overall
)
if salary_filter_active:
    has_salary = df["final_salary_min"].notna() & df["final_salary_max"].notna()
    in_salary_range = (
        (df["final_salary_max"] >= salary_range[0]) &
        (df["final_salary_min"] <= salary_range[1])
    )
    df = df[has_salary & in_salary_range]

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

if st.session_state.get("filter_salary_only"):
    df = df[df["final_salary_min"].notna() & df["final_salary_max"].notna()]

if st.session_state.get("filter_listed_seniority_only"):
    df = df[df["listed_seniority"].notna()]

# ── Summary bar ───────────────────────────────────────────────────────────────
total = len(df_full)
filtered = len(df)
st.markdown(
    f"Showing **{filtered}** of **{total}** postings",
    help="Filters are applied cumulatively. Salary filter passes through rows with no salary data.",
)

if filtered == 0:
    st.session_state["was_empty"] = True
    st.warning("No postings match the current filters.")
    st.stop()

# ── Grid display ──────────────────────────────────────────────────────────────
def make_display_df(df: pd.DataFrame) -> pd.DataFrame:
    display = pd.DataFrame()
    display["Title"] = df["job_title"].fillna("—")
    display["Company"] = df["company_name"].fillna("—")
    display["Role"] = df["title_role_bucket"].fillna("—")
    display["Work Model"] = df["work_model"].fillna("—")
    display["Source"] = df["source"].apply(lambda x: format_source(x) if pd.notna(x) else "—")
    display["sal_min"] = df["final_salary_min"].values
    display["sal_max"] = df["final_salary_max"].values
    display["Posted"] = df["date_posted"].values
    display["_job_id"] = df["job_id"].values
    display["_idx"] = df.index.values
    return display

display_df = make_display_df(df)
visible_cols = ["Title", "Company", "Role", "Work Model", "Source", "sal_min", "sal_max", "Posted"]

st.markdown("#### Postings")

current_job_ids = tuple(df["job_id"].values)
current_fingerprint = hash(current_job_ids)

if "last_fingerprint" not in st.session_state or st.session_state["last_fingerprint"] != current_fingerprint:
    st.session_state["last_fingerprint"] = current_fingerprint
    st.session_state["df_key"] = st.session_state.get("df_key", 0) + 1

if "df_key" not in st.session_state:
    st.session_state["df_key"] = 0

current_key = f"row_selection_{st.session_state['df_key']}"

if current_key not in st.session_state:
    st.session_state[current_key] = {"selection": {"rows": [0], "columns": [], "cells": []}}

if st.session_state.get("was_empty"):
    st.session_state["was_empty"] = False
    st.rerun()

event = st.dataframe(
    display_df[visible_cols].reset_index(drop=True),
    use_container_width=True,
    hide_index=True,
    height=320,
    on_select="rerun",
    selection_mode="single-row",
    key=current_key,
    column_config={
        "sal_min": st.column_config.NumberColumn("Sal. Min", format="$%d"),
        "sal_max": st.column_config.NumberColumn("Sal. Max", format="$%d"),
        "Posted": st.column_config.DateColumn("Posted", format="MMM DD, YYYY"),
    }
)

selected_rows = event.selection.rows if event and event.selection else []
selected_pos = selected_rows[0] if selected_rows else 0
selected_job_id = display_df.iloc[selected_pos]["_job_id"]
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
    st.markdown(
        f"<h3 style='margin-bottom:2px'>{job['job_title']}</h3>",
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

    meta_html = (
        f'<span class="tag-pill {wm_color}">{job.get("work_model", "—")}</span>'
        f'<span class="tag-pill {et_color}">{format_label(job.get("employment_type")) or "—"}</span>'
        f'<span class="tag-pill tag-purple">{format_source(job.get("source","—"))}</span>'
    )
    if job.get("explicitly_encourages_applicants"):
        meta_html += ' <span class="tag-pill tag-green">✓ Encourages All Applicants</span>'
    if job.get("acknowledges_ai"):
        meta_html += ' <span class="tag-pill tag-blue">🤖 Acknowledges AI</span>'

    st.markdown(meta_html, unsafe_allow_html=True)
    st.markdown("")

    # Location + salary
    info_col1, info_col2 = st.columns(2)
    with info_col1:
        posted = job.get("date_posted")
        st.markdown(f"**📅 Posted:** {posted.strftime('%b %d, %Y') if pd.notna(posted) else '—'}")
        st.markdown(f"**💰 Salary:** {format_salary(job.get('final_salary_min'), job.get('final_salary_max'))}")
    with info_col2:
        city = job.get("city") if pd.notna(job.get("city")) else None
        state = job.get("state") if pd.notna(job.get("state")) else None
        if city and state:
            location = f"{city}, {state}"
        elif city or state:
            location = city or state
        elif str(job.get("work_model", "")).lower() == "remote":
            location = "Remote"
        else:
            location = "Unknown"
        st.markdown(f"**📍 Location:** {location}")
        domain = job.get("domain")
        st.markdown(f"**🏢 Industry:** {domain.capitalize() if pd.notna(domain) and domain else '—'}")

    st.markdown("")

    # LLM enrichment section
    st.markdown("##### 🔩 AI Enrichment")

    arch = format_label(job.get("role_archetype")) or "—"
    focus = format_label(job.get("work_focus")) or "—"
    inferred_sen = format_seniority(job.get("inferred_seniority"))
    listed_sen = format_seniority(job.get("listed_seniority"))
    degree_raw = job.get("degree_requirement")
    degree = DEGREE_LABELS.get(degree_raw, format_label(degree_raw) or "—")
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
        st.markdown(f"**Inferred Archetype:** {arch}")
        st.markdown(f"**Work Focus:** {focus}")
        st.markdown(f"**Inferred Seniority:** {inferred_sen}")
        st.markdown(f"**Listed Seniority:** {listed_sen}")
    with enrich_cols[1]:
        st.markdown(f"**Degree Req:** {degree}")
        st.markdown(f"**YoE Required:** {yoe_str}")
        st.markdown(f"**Confidence:** {conf_str}")

    st.markdown("")

    # Tech stack
    st.markdown("##### 🛠 Tech Stack")
    ts_req = job.get("tech_stack_required") or []
    ts_pref = job.get("tech_stack_preferred") or []
    st.markdown(f"**Required:** {tag_pills(ts_req, 'tag-blue')}", unsafe_allow_html=True)
    st.markdown(f"**Preferred:** {tag_pills(ts_pref, 'tag-gray')}", unsafe_allow_html=True)

    st.markdown("")

    # Paradigms
    st.markdown("##### 🧠 Paradigms & Methods")
    par_req = job.get("paradigms_required") or []
    par_pref = job.get("paradigms_preferred") or []
    st.markdown(f"**Required:** {tag_pills(par_req, 'tag-green')}", unsafe_allow_html=True)
    st.markdown(f"**Preferred:** {tag_pills(par_pref, 'tag-gray')}", unsafe_allow_html=True)

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