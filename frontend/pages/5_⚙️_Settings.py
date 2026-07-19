"""
Corpus AI - Workspace Settings
================================
Manage company workspace and invite employees.
"""

import streamlit as st
from frontend.components.auth import check_auth_or_redirect
from frontend.components.sidebar import draw_sidebar
from frontend.utils.api_client import CorpusAPIClient

check_auth_or_redirect()

# Ensure user is an admin
if st.session_state.user.get("role") not in ["admin", "super_admin"]:
    st.error("🔒 Access Denied: You must be an administrator to view this page.")
    st.stop()

st.set_page_config(
    page_title="Corpus AI - Settings",
    page_icon="⚙️",
    layout="wide",
)

draw_sidebar()
api_client = CorpusAPIClient()

st.title("⚙️ Workspace Settings")
st.write("Manage team membership and system settings.")

# ---- Section 1: Invite System ----
st.subheader("✉️ Onboard New Employees")
st.write("Generate a secure signup invite code to share with your colleagues.")

invite_email = st.text_input("Employee Email (Optional)", placeholder="raj@company.com", help="Optional restriction. If filled, only this email can join.")
invite_role = st.selectbox("Role", ["Member", "Admin"], index=0)

if st.button("Generate Invite Code"):
    role_val = invite_role.lower()
    res = api_client.invite(
        email=invite_email if invite_email else None,
        role=role_val,
        token=st.session_state.access_token
    )
    if res["success"]:
        st.success("Invite Code Generated!")
        st.code(res["data"]["invite_code"], language="text")
        st.info("Share this code with your colleague. They can sign up using the 'Join Company' tab on the login portal.")
    else:
        st.error(res["error"]["message"])

st.divider()

# ---- Section 2: Team Members ----
st.subheader("👥 Active Team Members")

import pandas as pd
team_data = {
    "Name": ["Sarah Chen", "Raj Kumar", "Alice Wong"],
    "Email": ["sarah@acme.com", "raj@acme.com", "alice@acme.com"],
    "Role": ["Admin", "Member", "Member"],
    "Joined Date": ["2026-07-01", "2026-07-05", "2026-07-10"]
}
st.dataframe(pd.DataFrame(team_data), use_container_width=True)
