"""
Corpus AI - Chat Q&A Page
==========================
Chat interface for querying company documents.
"""

import streamlit as st
from frontend.components.auth import check_auth_or_redirect
from frontend.components.sidebar import draw_sidebar

# Protect the page
check_auth_or_redirect()

# Set up page configurations
st.set_page_config(
    page_title="Corpus AI - Chat",
    page_icon="💬",
    layout="wide",
)

# Draw sidebar navigation
draw_sidebar()

# Main Page Header
st.title("💬 Chat with your documents")
st.write("Ask questions and get answers cited from your company's uploaded documents.")

# Session state initialization for chat messages
if "chat_history" not in st.session_state:
    st.session_state.chat_history = [
        {"role": "assistant", "content": "Welcome! Ask me anything about your uploaded documents."}
    ]

# Display chat history
for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        if "sources" in msg and msg["sources"]:
            with st.expander("📎 Cited Sources"):
                for source in msg["sources"]:
                    st.write(f"- **{source['document_name']}** (Score: {source['relevance_score']:.2f})")
                    st.caption(f"\"{source['text_preview']}\"")

# Input field
if prompt := st.chat_input("Ask a question about your docs..."):
    # Add user message to UI
    st.session_state.chat_history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    # Call RAG API (Day 9 placeholder response)
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            # Placeholder response for now
            response_text = f"This is a placeholder response for your question: '{prompt}'. We will connect the RAG pipeline here in Week 2."
            st.write(response_text)
            
            # Save response to history
            st.session_state.chat_history.append({"role": "assistant", "content": response_text})
