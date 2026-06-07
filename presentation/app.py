"""
app.py
NYC Data Job Market Tracker — Streamlit dashboard entry point.
Uses st.navigation for multi-page layout.
"""

import streamlit as st

st.set_page_config(
    page_title="NYC Data Job Tracker",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom global styles ──────────────────────────────────────────────────────
st.markdown(
    """
    <style>
        /* Tighten sidebar width slightly */
        [data-testid="stSidebar"] { min-width: 260px; max-width: 300px; }

        /* Suppress the default Streamlit nav header text */
        [data-testid="stSidebarNav"] > ul > li:first-child { display: none; }

        /* Tag pill style — used across pages */
        .tag-pill {
            display: inline-block;
            padding: 2px 10px;
            border-radius: 99px;
            font-size: 0.75rem;
            font-weight: 600;
            margin: 2px 3px 2px 0;
            white-space: nowrap;
        }
        .tag-blue  { background: #dbeafe; color: #1e40af; }
        .tag-green { background: #dcfce7; color: #166534; }
        .tag-amber { background: #fef9c3; color: #854d0e; }
        .tag-red   { background: #fee2e2; color: #991b1b; }
        .tag-gray  { background: #f1f5f9; color: #475569; }
        .tag-purple{ background: #ede9fe; color: #5b21b6; }

        /* Metric card */
        .metric-card {
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 10px;
            padding: 18px 22px;
            text-align: center;
        }
        .metric-card .metric-val {
            font-size: 2rem;
            font-weight: 700;
            color: #0f172a;
            line-height: 1.1;
        }
        .metric-card .metric-label {
            font-size: 0.8rem;
            color: #64748b;
            margin-top: 4px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Page definitions ──────────────────────────────────────────────────────────
market_insights = st.Page(
    "pages/01_market_insights.py",
    title="Market Insights",
    icon="📈",
)
job_explorer = st.Page(
    "pages/02_job_explorer.py",
    title="Job Explorer",
    icon="🔍",
)
pipeline_health = st.Page(
    "pages/03_pipeline_health.py",
    title="Pipeline Health",
    icon="🛠",
)

pg = st.navigation(
    {
        "Dashboard": [market_insights, job_explorer, pipeline_health],
    }
)

# Sidebar branding
with st.sidebar:
    st.markdown(
        """
        <div style="padding: 4px 0 20px 0;">
            <div style="font-size:1.15rem; font-weight:700; color:#c2c3c4; letter-spacing:-0.02em;">
                NYC Data Job Tracker
            </div>
            <div style="font-size:0.75rem; color:#94a3b8; margin-top:2px;">
                Early-career analytics roles · Live pipeline
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    # st.divider()

pg.run()