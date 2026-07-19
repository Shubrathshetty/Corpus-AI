"""
Corpus AI - Document Management Page
====================================
Upload, list, and delete company documents.
"""

import streamlit as st
from frontend.components.auth import check_auth_or_redirect
from frontend.components.sidebar import draw_sidebar

# Protect the page
check_auth_or_redirect()

st.set_page_config(
    page_title="Corpus AI - Documents",
    page_icon="📄",
    layout="wide",
)

draw_sidebar()

st.title("📄 Document Management")
st.write("Upload company files to embed them into your vector search index.")

user = st.session_state.user
is_admin = user.get("role") in ["admin", "super_admin"]

# ---- Section 1: Upload (Admins only) ----
if is_admin:
    st.subheader("📤 Upload New Document")
    uploaded_file = st.file_uploader(
        "Choose a file (PDF, DOCX, or TXT)",
        type=["pdf", "docx", "txt"],
        help="Maximum file size: 10MB."
    )
    if uploaded_file is not None:
        if st.button("Upload & Process"):
            st.info("Upload trigger initiated! We will connect this to the Celery workers in Week 2.")
else:
    st.info("🔒 Only administrators can upload documents.")

st.divider()

# ---- Section 2: Document List ----
st.subheader("📋 Workspace Documents")
st.write("Here is the list of documents available in this company workspace.")

# Placeholder table
import pandas as pd
data = {
    "Filename": ["HR_Policy_2024.pdf", "Engineering_Runbook.docx", "Onboarding_Guide.txt"],
    "Type": ["PDF", "DOCX", "TXT"],
    "Size": ["2.4 MB", "1.1 MB", "42 KB"],
    "Status": ["Ready ✅", "Ready ✅", "Processing ⏳"],
}
st.dataframe(pd.DataFrame(data), use_container_width=True)
