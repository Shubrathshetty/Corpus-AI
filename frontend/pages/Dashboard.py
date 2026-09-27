"""
Corpus AI - Admin Analytics Dashboard
======================================
View real system statistics, daily usage graphs, response latency, and popular questions.
Restricted to Workspace Administrators.
"""

import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

import streamlit as st
import pandas as pd
from frontend.components.auth import check_auth_or_redirect
from frontend.components.sidebar import draw_sidebar
from frontend.utils.api_client import CorpusAPIClient

check_auth_or_redirect()

# Ensure user is an admin
if st.session_state.user.get("role") not in ["admin", "super_admin"]:
    st.error("🔒 Access Denied: You must be an administrator to view this page.")
    st.stop()

draw_sidebar()
api_client = CorpusAPIClient()

st.title("📊 Usage Dashboard")
st.write("Monitor queries, costs, and search metrics for your workspace in real-time.")

# Fetch statistics in parallel
with st.spinner("Compiling dashboard telemetry analytics..."):
    stats_res = api_client.get_dashboard_stats(st.session_state.access_token)
    popular_res = api_client.get_popular_queries(st.session_state.access_token)
    usage_res = api_client.get_usage_over_time(st.session_state.access_token)

if not stats_res["success"]:
    st.error(f"Failed to load stats: {stats_res['error']['message']}")
    st.stop()

stats = stats_res["data"]

# ---- Section 1: Metrics Row ----
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Indexed Documents", str(stats["total_documents"]))
with col2:
    st.metric("Total Queries", str(stats["total_queries"]))
with col3:
    st.metric("Active Members", str(stats["active_users"]))
with col4:
    st.metric("Vector Passages Chunks", str(stats["total_chunks"]))

st.divider()

# ---- Section 2: Chart & Detail Rows ----
col_left, col_right = st.columns([1.2, 0.8])

with col_left:
    st.subheader("📈 Search Request Volume (Past 30 Days)")
    if usage_res["success"] and usage_res["data"]["data"]:
        usage_data = usage_res["data"]["data"]
        # Format as pandas dataframe
        df = pd.DataFrame([{"Date": pt["date"], "Queries Count": pt["query_count"]} for pt in usage_data])
        df.set_index("Date", inplace=True)
        # Draw interactive line chart
        st.line_chart(df, color="#FF4B4B")
    else:
        st.info("No query traffic records available yet to display graph.")

with col_right:
    st.subheader("⏱️ Performance Telemetry")
    # Convert average latency to seconds for presentation if needed
    avg_l = stats["avg_latency_ms"]
    latency_str = f"{avg_l / 1000:.2f}s" if avg_l >= 1000 else f"{avg_l}ms"
    st.metric("Average Response Latency", latency_str)
    
    cache_hit_pct = float(stats["cache_hit_ratio"]) * 100.0
    st.metric("Cache Hit Ratio", f"{cache_hit_pct:.1f}%")

st.divider()

# ---- Section 3: Popular Queries ----
st.subheader("🔥 Popular Inquiries")
st.write("Most frequent questions asked by employees:")

if popular_res["success"] and popular_res["data"]["queries"]:
    pop_queries = popular_res["data"]["queries"]
    df_pop = pd.DataFrame([{"Question": q["question"], "Queries Count": q["count"]} for q in pop_queries])
    st.dataframe(df_pop, use_container_width=True, hide_index=True)
else:
    st.info("Not enough query telemetry logs to group popular queries yet.")
