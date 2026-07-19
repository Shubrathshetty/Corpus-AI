"""
Corpus AI - Shared Sidebar Component
=====================================
Sidebar for navigation, tenant branding, user profile, and session control.

DESIGN STRATEGY:
Provides consistent navigation across all pages and displays the current user's
profile and role (important for showing RBAC constraints).
"""

import streamlit as st
from frontend.components.auth import logout_user


def draw_sidebar() -> None:
    """Renders the sidebar navigation and user info profile."""
    # Ensure auth state exists
    if "user" not in st.session_state or not st.session_state.user:
        return

    user = st.session_state.user
    company_name = user.get("company_name", "My Company")
    role_name = user.get("role", "member").replace("_", " ").title()

    with st.sidebar:
        # ---- Logo / Brand ----
        st.markdown(
            f"""
            <div style="text-align: center; margin-bottom: 20px;">
                <h1 style="margin: 0; color: #FF4B4B; font-size: 28px;">🧠 Corpus AI</h1>
                <p style="margin: 0; color: #888; font-size: 14px;">{company_name}</p>
            </div>
            """,
            unsafe_allow_allowed=True,
            unsafe_allow_html=True,
        )

        st.divider()

        # ---- Navigation ----
        st.markdown("### 🧭 Navigation")
        st.page_link("pages/2_💬_Chat.py", label="Chat Q&A", icon="💬")
        st.page_link("pages/3_📄_Documents.py", label="Documents", icon="📄")
        
        # Admin-only pages
        if user.get("role") in ["admin", "super_admin"]:
            st.page_link("pages/4_📊_Dashboard.py", label="Dashboard", icon="📊")
            st.page_link("pages/5_⚙️_Settings.py", label="Settings", icon="⚙️")

        st.divider()

        # ---- User Profile ----
        st.markdown("### 👤 Active User")
        st.markdown(
            f"""
            **Name**: {user.get('name')}<br>
            **Email**: {user.get('email')}<br>
            **Role**: <span style="background-color: #333; padding: 2px 6px; border-radius: 4px; font-size: 12px; color: #FF4B4B;">{role_name}</span>
            """,
            unsafe_allow_html=True,
        )

        st.divider()

        # ---- Logout ----
        if st.button("🚪 Logout", use_container_width=True):
            logout_user()
