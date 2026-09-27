"""
Corpus AI - Shared Sidebar Component
=====================================
Sidebar for tenant branding, active user profile, and session logout.
Page navigation itself is handled natively by st.navigation in app.py.
"""

import streamlit as st
from frontend.components.auth import logout_user


def draw_sidebar() -> None:
    """Renders the sidebar tenant branding, user info profile, and logout button."""
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
                <h1 style="margin: 0; color: #FF4B4B; font-size: 26px;">Corpus AI</h1>
                <p style="margin: 0; color: #888; font-size: 13px;">🏢 {company_name}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

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
