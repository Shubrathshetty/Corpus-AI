"""
Corpus AI - Document Management Page
====================================
Upload, list, and delete company documents with real backend integration.
"""

import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

import streamlit as st
from datetime import datetime
from frontend.components.auth import check_auth_or_redirect
from frontend.components.sidebar import draw_sidebar
from frontend.utils.api_client import CorpusAPIClient

# Protect the page
check_auth_or_redirect()

draw_sidebar()
api_client = CorpusAPIClient()

st.title("📄 Document Management")
st.write("Upload company files to embed them into your vector search index.")

user = st.session_state.user
is_admin = user.get("role") in ["admin", "super_admin"]


def format_size(bytes_size: int) -> str:
    """Format file size in human-readable units."""
    if bytes_size < 1024:
        return f"{bytes_size} B"
    elif bytes_size < 1024 * 1024:
        return f"{bytes_size / 1024:.1f} KB"
    else:
        return f"{bytes_size / (1024 * 1024):.1f} MB"


def get_status_badge(status_str: str) -> str:
    """Get status representation badge."""
    status_lower = status_str.lower()
    if status_lower == "uploading":
        return "⏳ Uploading"
    elif status_lower == "processing":
        return "⚙️ Processing"
    elif status_lower == "ready":
        return "✅ Ready"
    elif status_lower == "failed":
        return "❌ Failed"
    return status_str


# ---- Section 1: Upload (Admins only) ----
if is_admin:
    st.subheader("📤 Upload New Document")
    uploaded_file = st.file_uploader(
        "Choose a file (PDF, DOCX, TXT, or MD)",
        type=["pdf", "docx", "txt", "md"],
        help="Maximum file size: 10MB."
    )
    if uploaded_file is not None:
        if st.button("Upload & Process", type="primary", use_container_width=True):
            with st.spinner("Uploading and queueing text ingestion..."):
                file_bytes = uploaded_file.read()
                res = api_client.upload_document(
                    file_name=uploaded_file.name,
                    file_content=file_bytes,
                    token=st.session_state.access_token
                )
                if res["success"]:
                    st.success(f"Successfully uploaded '{uploaded_file.name}'! It is now being processed in the background.")
                    st.rerun()
                else:
                    st.error(f"Upload failed: {res['error']['message']}")
else:
    st.info("🔒 Only administrators can upload documents to the workspace.")

st.divider()

# ---- Section 2: Document List ----
st.subheader("📋 Workspace Documents")
st.write("Here is the list of documents available in this company workspace.")

# Fetch real documents from backend
with st.spinner("Loading document list..."):
    res = api_client.list_documents(st.session_state.access_token)

if not res["success"]:
    st.error(f"Failed to load documents: {res['error']['message']}")
else:
    doc_list = res["data"]["documents"]
    total_docs = res["data"]["total"]

    if total_docs == 0:
        st.info("No documents uploaded yet in this workspace. Ask an administrator to upload documents.")
    else:
        # Display as a table using streamlit columns
        # Header Row
        hdr_col1, hdr_col2, hdr_col3, hdr_col4, hdr_col5 = st.columns([3, 1, 1.2, 1.8, 1])
        hdr_col1.markdown("**Filename**")
        hdr_col2.markdown("**Size**")
        hdr_col3.markdown("**Status**")
        hdr_col4.markdown("**Uploaded Date**")
        hdr_col5.markdown("**Actions**")
        st.divider()

        # Data Rows
        for doc in doc_list:
            col1, col2, col3, col4, col5 = st.columns([3, 1, 1.2, 1.8, 1])
            
            # Column 1: Filename + format type helper
            file_icon = "📕" if doc["file_type"] == "pdf" else "📘" if doc["file_type"] == "docx" else "📝"
            col1.write(f"{file_icon} {doc['filename']}")
            
            # Column 2: File Size
            col2.write(format_size(doc["file_size_bytes"]))
            
            # Column 3: Processing Status
            status_text = get_status_badge(doc["status"])
            if doc["status"].lower() == "failed" and doc["error_message"]:
                col3.write(status_text)
                col3.caption(f"Error: {doc['error_message']}")
            else:
                col3.write(status_text)
                
            # Column 4: Date
            dt = datetime.fromisoformat(doc["created_at"].replace("Z", "+00:00"))
            col4.write(dt.strftime("%b %d, %Y %H:%M"))
            
            # Column 5: Actions (Delete Button for Admins only)
            if is_admin:
                if col5.button("🗑️ Delete", key=f"del_{doc['id']}", type="secondary", use_container_width=True):
                    with st.spinner("Deleting document index..."):
                        del_res = api_client.delete_document(doc["id"], st.session_state.access_token)
                        if del_res["success"]:
                            st.success("Document deleted!")
                            st.rerun()
                        else:
                            st.error(del_res["error"]["message"])
            else:
                col5.write("🔒 Restricted")
            
            st.divider()
