"""
Corpus AI - Workspace Settings
================================
Manage company workspace and invite employees.
Restricted to Company Administrators.
"""

import streamlit as st
import pandas as pd
from datetime import datetime
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

with st.spinner("Loading team listing..."):
    res_users = api_client.list_users(st.session_state.access_token)

if res_users["success"]:
    users = res_users["data"]["users"]
    team_list = []
    for u in users:
        # Convert created_at ISO string to display format
        try:
            dt = datetime.fromisoformat(u["created_at"].replace("Z", "+00:00"))
            joined_str = dt.strftime("%b %d, %Y")
        except Exception:
            joined_str = str(u["created_at"])[:10]
            
        role_disp = u["role"].replace("_", " ").title()
        team_list.append({
            "Name": u["name"],
            "Email": u["email"],
            "Role": role_disp,
            "Joined Date": joined_str
        })
    
    st.dataframe(pd.DataFrame(team_list), use_container_width=True, hide_index=True)
else:
    st.error(f"Failed to load team list: {res_users['error']['message']}")
