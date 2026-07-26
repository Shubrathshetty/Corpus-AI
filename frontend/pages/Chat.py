"""
Corpus AI - Chat Q&A Page
==========================
Interactive Chat chatbot interface for querying uploaded company documents.
Supports session thread switching, Citations/Grounding validation, and message history.
"""

import streamlit as st
from frontend.components.auth import check_auth_or_redirect
from frontend.components.sidebar import draw_sidebar
from frontend.utils.api_client import CorpusAPIClient

# Protect the page
check_auth_or_redirect()

# Set up page configurations
st.set_page_config(
    page_title="Corpus AI - Chat",
    page_icon="💬",
    layout="wide",
)

# Draw generic sidebar first
draw_sidebar()
api_client = CorpusAPIClient()

# Initialize session state for current active thread
if "current_session_id" not in st.session_state:
    st.session_state.current_session_id = None

# ---- Render Sidebar Conversations List ----
with st.sidebar:
    st.divider()
    st.subheader("💬 Chat Sessions")
    
    # Load user's conversations from database
    sessions_res = api_client.get_chat_sessions(st.session_state.access_token)
    if sessions_res["success"]:
        sessions = sessions_res["data"]["sessions"]
        
        # Form options list
        options = [None] + [s["id"] for s in sessions]
        titles = {None: "➕ Start New Conversation"}
        for s in sessions:
            titles[s["id"]] = s["title"] or f"Chat thread {s['id'][:6]}..."

        # Show selector
        # To avoid rerun loops, compare selectbox value directly
        selected = st.selectbox(
            "Select active conversation:",
            options=options,
            format_func=lambda x: titles[x],
            index=options.index(st.session_state.current_session_id) if st.session_state.current_session_id in options else 0,
            key="chat_session_selector_box"
        )
        
        if selected != st.session_state.current_session_id:
            st.session_state.current_session_id = selected
            # Clear local cache to force reload on rerun
            if "chat_history" in st.session_state:
                del st.session_state.chat_history
            st.rerun()
    else:
        st.warning("Failed to load chat history logs")

# ---- Load Message History for Selected Session ----
if st.session_state.current_session_id:
    if "chat_history" not in st.session_state:
        with st.spinner("Loading conversation history..."):
            hist_res = api_client.get_chat_history(
                session_id=st.session_state.current_session_id,
                token=st.session_state.access_token
            )
            if hist_res["success"]:
                messages = hist_res["data"]["messages"]
                st.session_state.chat_history = [
                    {
                        "role": m["role"],
                        "content": m["content"],
                        "sources": m["sources"]
                    }
                    for m in messages
                ]
            else:
                st.error("Failed to load conversation messages")
                st.session_state.chat_history = []
else:
    # New Chat thread default welcoming message
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = [
            {
                "role": "assistant",
                "content": "Welcome! Ask me anything. I will search the company's uploaded documents and answer using cited text.",
                "sources": None
            }
        ]

# Main Page Title
st.title(" 💬 Chat with your documents")
st.write("Ask questions and get answers cited from your company's uploaded documents.")

# Display chat history log
for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        
        # Display citation cards if assistant provides sources
        if msg.get("sources"):
            with st.expander("📎 Grounding Sources / Citations", expanded=False):
                for idx, source in enumerate(msg["sources"]):
                    st.markdown(
                        f"**Source {idx+1}: {source['document_name']}** "
                        f"(Match Score: `{source['relevance_score']:.2f}`)\n"
                        f"> *\"{source['text_preview']}\"*"
                    )

# Chat Input prompt
if prompt := st.chat_input("Ask a question about your docs..."):
    # Append user question to local state UI immediately
    st.session_state.chat_history.append({"role": "user", "content": prompt, "sources": None})
    with st.chat_message("user"):
        st.write(prompt)

    # Call RAG Pipeline API
    with st.chat_message("assistant"):
        with st.spinner("Searching document index & thinking..."):
            res = api_client.query_chat(
                question=prompt,
                session_id=st.session_state.current_session_id,
                token=st.session_state.access_token
            )
            
            if res["success"]:
                data = res["data"]
                answer = data["answer"]
                sources = data["sources"]
                new_session_id = data["session_id"]
                
                # Write answer
                st.write(answer)
                
                # Display sources
                if sources:
                    with st.expander("📎 Grounding Sources / Citations", expanded=False):
                        for idx, source in enumerate(sources):
                            st.markdown(
                                f"**Source {idx+1}: {source['document_name']}** "
                                f"(Match Score: `{source['relevance_score']:.2f}`)\n"
                                f"> *\"{source['text_preview']}\"*"
                            )

                # Save response to history cache
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": answer,
                    "sources": sources
                })
                
                # If we just started a new session, lock it in
                if st.session_state.current_session_id is None:
                    st.session_state.current_session_id = new_session_id
                    
                # Rerun to update sidebar lists in sync
                st.rerun()
            else:
                error_msg = res["error"]["message"]
                st.error(f"Failed to generate answer: {error_msg}")
