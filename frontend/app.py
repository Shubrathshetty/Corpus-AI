"""
Corpus AI - Streamlit Entry Point
==================================
Uses Streamlit's st.Page and st.navigation to build a clean multi-page app
with role-based dynamic routing.

WHY THIS ARCHITECTURE?
1. Clean: Hides page files from standard sidebar menu
2. Secure: Prevents unauthorized roles from seeing or accessing admin routes
3. Responsive: Adapts sidebar items immediately upon state changes (e.g. login/logout)

INTERVIEW NOTE:
"We use Streamlit's new programmatic navigation API. If a user is not logged in,
only the login page is registered, hiding all application pages. Once logged in,
regular members see Chat and Docs, while admins also see Dashboard and Settings.
This implements front-end role-based routing natively."
"""

import streamlit as st
from frontend.components.auth import init_auth_state

# Initialize session state variables
init_auth_state()

# Configure page paths (relative to root workspace directory)
login_page = st.Page("frontend/pages/Login.py", title="Access Portal", icon="🔐")
chat_page = st.Page("frontend/pages/Chat.py", title="Chat Q&A", icon="💬")
docs_page = st.Page("frontend/pages/Documents.py", title="Documents", icon="📄")
dash_page = st.Page("frontend/pages/Dashboard.py", title="Dashboard", icon="📊")
settings_page = st.Page("frontend/pages/Settings.py", title="Settings", icon="⚙️")


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
