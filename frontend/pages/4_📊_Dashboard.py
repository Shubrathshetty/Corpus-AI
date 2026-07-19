"""
Corpus AI - Admin Analytics Dashboard
======================================
View usage stats, cost savings, latency, and popular questions.
"""

import streamlit as st
from frontend.components.auth import check_auth_or_redirect
from frontend.components.sidebar import draw_sidebar

check_auth_or_redirect()

# Ensure user is an admin
if st.session_state.user.get("role") not in ["admin", "super_admin"]:
    st.error("🔒 Access Denied: You must be an administrator to view this page.")
    st.stop()

st.set_page_config(
    page_title="Corpus AI - Dashboard",
    page_icon="📊",
    layout="wide",
)

draw_sidebar()

st.title("📊 Usage Dashboard")
st.write("Monitor queries, costs, and search metrics for your workspace.")

# Metrics Row
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Total Documents", "12", delta="2 this week")
with col2:
    st.metric("Total Queries", "248", delta="34 today")
with col3:
    st.metric("Active Members", "4", delta="1 new joiner")

st.divider()

# Chart / Metrics details
col_left, col_right = st.columns(2)
with col_left:
    st.subheader("🔥 Popular Inquiries")
    st.write("Most frequent questions asked by employees:")
    popular_data = {
        "Question": [
            "What is our parental leave policy?",
            "How do I submit an expense report?",
            "What is the PTO policy?",
            "Where is the API keys documentation?",
        ],
        "Queries Count": [48, 32, 19, 12]
    }
    st.table(popular_data)

with col_right:
    st.subheader("⏱️ System Metrics")
    st.metric("Average Response Latency", "2.1s", delta="-0.4s (cache improvements)")
    st.metric("Cache Hit Ratio", "42%", delta="+5% (Redis cache)")
