"""
Corpus AI - Streamlit Entry Point
==================================
Uses Streamlit's st.Page and st.navigation to build a clean multi-page app
with role-based dynamic routing.
"""

import sys
from pathlib import Path

# Ensure root directory is in sys.path
_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

import streamlit as st
from frontend.components.auth import init_auth_state

# Global page configuration (must be called before other streamlit commands)
st.set_page_config(
    page_title="Corpus AI",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize session state variables
init_auth_state()

# Configure page paths (relative to THIS script's directory, i.e. frontend/)
login_page = st.Page("pages/Login.py", title="Access Portal", icon="🔐")
chat_page = st.Page("pages/Chat.py", title="Chat Q&A", icon="💬")
docs_page = st.Page("pages/Documents.py", title="Documents", icon="📄")
dash_page = st.Page("pages/Dashboard.py", title="Dashboard", icon="📊")
settings_page = st.Page("pages/Settings.py", title="Settings", icon="⚙️")


# ---- Dynamic Route Selection ----
if not st.session_state.authenticated:
    # If not logged in, show only Login Portal and hide sidebar navigation
    pg = st.navigation([login_page], position="hidden")
else:
    # If logged in, build custom navigation list based on user role
    role = st.session_state.user.get("role", "member")
    if role in ["admin", "super_admin"]:
        pages_list = [chat_page, docs_page, dash_page, settings_page]
    else:
        pages_list = [chat_page, docs_page]
    
    pg = st.navigation(pages_list)

# Run the active page
pg.run()
