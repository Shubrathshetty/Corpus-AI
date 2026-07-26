"""
Corpus AI - Login, Register, & Join Page
==========================================
Handles new user signup, company registration, and employee onboarding.

WHY THREE TABS?
- Tab 1 (Login): Existing users log in.
- Tab 2 (Register): Admin registers a new company.
- Tab 3 (Join): Employee joins a company using a shared invite code.
"""

import streamlit as st
from frontend.components.auth import login_user, init_auth_state
from frontend.utils.api_client import CorpusAPIClient

st.set_page_config(
    page_title="Corpus AI - Access Portal",
    page_icon="🔐",
    layout="centered",
)

api_client = CorpusAPIClient()
init_auth_state()

# Redirection check
if st.session_state.authenticated:
    st.info("Already logged in! Redirecting...")
    st.switch_page("pages/Chat.py")

# Title and branding
st.markdown(
    """
    <div style="text-align: center; margin-top: 50px; margin-bottom: 30px;">
        <h1 style="color: #FF4B4B; font-size: 42px; margin-bottom: 0;">🧠 Corpus AI</h1>
        <p style="color: #888; font-size: 18px;">Your company's internal knowledge assistant</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# Tabs for Login, Register, and Join
tab_login, tab_register, tab_join = st.tabs(
    ["🔑 Sign In", "🏢 Register Company", "🎟️ Join Company"]
)

# ============================================================
# Tab 1: Sign In
# ============================================================
with tab_login:
    st.markdown("### Access your company's workspace")
    login_email = st.text_input("Email", key="login_email_input", placeholder="sarah@acme.com")
    login_password = st.text_input("Password", type="password", key="login_pwd_input", placeholder="••••••••")

    if st.button("Sign In", type="primary", use_container_width=True):
        if not login_email or not login_password:
            st.error("Please fill in all fields.")
        else:
            with st.spinner("Authenticating..."):
                res = api_client.login(login_email, login_password)
                if res["success"]:
                    login_user(res["data"])
                    st.success("Successfully logged in!")
                    st.rerun()
                else:
                    st.error(res["error"]["message"])

# ============================================================
# Tab 2: Register Company
# ============================================================
with tab_register:
    st.markdown("### Create a new workspace")
    reg_company = st.text_input("Company Name", key="reg_company_input", placeholder="Acme Corporation")
    reg_name = st.text_input("Your Full Name", key="reg_name_input", placeholder="Sarah Chen")
    reg_email = st.text_input("Business Email", key="reg_email_input", placeholder="sarah@acme.com")
    reg_password = st.text_input("Password", type="password", key="reg_pwd_input", help="Minimum 8 characters with 1 capital letter and 1 digit.")
    reg_confirm = st.text_input("Confirm Password", type="password", key="reg_confirm_input")

    if st.button("Create Company Workspace", type="primary", use_container_width=True):
        if not all([reg_company, reg_name, reg_email, reg_password, reg_confirm]):
            st.error("Please fill in all fields.")
        elif reg_password != reg_confirm:
            st.error("Passwords do not match.")
        else:
            with st.spinner("Creating workspace..."):
                res = api_client.register(reg_company, reg_name, reg_email, reg_password)
                if res["success"]:
                    login_user(res["data"])
                    st.success("Workspace created successfully!")
                    st.rerun()
                else:
                    st.error(res["error"]["message"])

# ============================================================
# Tab 3: Join Company
# ============================================================
with tab_join:
    st.markdown("### Join an existing workspace")
    join_code = st.text_input("Invite Code", key="join_code_input", placeholder="ABC12345")
    join_name = st.text_input("Your Full Name", key="join_name_input", placeholder="Raj Kumar")
    join_email = st.text_input("Work Email", key="join_email_input", placeholder="raj@acme.com")
    join_password = st.text_input("Password", type="password", key="join_pwd_input")
    join_confirm = st.text_input("Confirm Password", type="password", key="join_confirm_input")

    if st.button("Join Workspace", type="primary", use_container_width=True):
        if not all([join_code, join_name, join_email, join_password, join_confirm]):
            st.error("Please fill in all fields.")
        elif join_password != join_confirm:
            st.error("Passwords do not match.")
        else:
            with st.spinner("Joining company..."):
                res = api_client.join(
                    invite_code=join_code,
                    name=join_name,
                    email=join_email,
                    password=join_password,
                )
                if res["success"]:
                    login_user(res["data"])
                    st.success("Successfully joined the company workspace!")
                    st.rerun()
                else:
                    st.error(res["error"]["message"])
