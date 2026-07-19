"""
Corpus AI - Streamlit Auth Helper
==================================
Manages authentication state in Streamlit session_state.

WHY THIS HELPER?
Streamlit's execution model is different from traditional frameworks:
every click runs the script from top to bottom. Persistent state must
be stored in `st.session_state`. This module centralizes state mutation.

INTERVIEW NOTE:
"In Streamlit, page reloads destroy ordinary variables. We use
st.session_state to store access and refresh tokens. We also implement
token refresh on startup to keep the session alive silently."
"""

import time
import streamlit as st
from frontend.utils.api_client import CorpusAPIClient

api_client = CorpusAPIClient()


def init_auth_state() -> None:
    """Initialize session state keys for authentication if they don't exist."""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "access_token" not in st.session_state:
        st.session_state.access_token = None
    if "refresh_token" not in st.session_state:
        st.session_state.refresh_token = None
    if "user" not in st.session_state:
        st.session_state.user = None
    if "token_expiry" not in st.session_state:
        st.session_state.token_expiry = 0


def login_user(auth_data: dict) -> None:
    """Save authentication data to session_state and redirect to chat.

    Expected auth_data structure from API:
    {
        "access_token": "...",
        "refresh_token": "...",
        "user": { ... }
    }
    """
    st.session_state.authenticated = True
    st.session_state.access_token = auth_data["access_token"]
    st.session_state.refresh_token = auth_data["refresh_token"]
    st.session_state.user = auth_data["user"]
    # Access tokens expire in 30 minutes. We set expiration to 28 minutes to be safe.
    st.session_state.token_expiry = time.time() + (28 * 60)


def logout_user() -> None:
    """Clear all authentication state and rerun to redirect to login."""
    st.session_state.authenticated = False
    st.session_state.access_token = None
    st.session_state.refresh_token = None
    st.session_state.user = None
    st.session_state.token_expiry = 0
    # Clear other user-specific states
    if "chat_history" in st.session_state:
        del st.session_state.chat_history
    if "current_session_id" in st.session_state:
        del st.session_state.current_session_id
    
    st.rerun()


def check_auth_or_redirect() -> None:
    """Fast check on any protected page to ensure the user is logged in.

    If not authenticated, displays an error and stops execution.
    Auto-refreshes token if it has expired.
    """
    init_auth_state()

    if not st.session_state.authenticated:
        st.warning("🔒 Please login to access this page.")
        st.stop()

    # Auto refresh token if near expiry
    if time.time() > st.session_state.token_expiry:
        if st.session_state.refresh_token:
            res = api_client.refresh_token(st.session_state.refresh_token)
            if res["success"]:
                login_user(res["data"])
            else:
                # Refresh failed (expired refresh token)
                st.error("Session expired. Please login again.")
                logout_user()
        else:
            logout_user()
