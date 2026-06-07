"""
pages/01_market_insights.py
Market Insights — placeholder until EDA determines what's worth showing.
"""

import streamlit as st

st.title("📈 Market Insights")
st.info(
    "**Coming soon.** This page will be built after EDA in "
    "`presentation/notebooks/eda.ipynb` reveals what's actually interesting in the data.\n\n"
    "Candidates include: salary distributions by archetype, top required tech stack skills, "
    "work model breakdown, title inflation patterns, and posting trends over time.",
    icon="🔬",
)
st.markdown(
    "Head to **Job Explorer** to browse and inspect postings, or **Pipeline Health** to see "
    "how the pipeline is performing."
)