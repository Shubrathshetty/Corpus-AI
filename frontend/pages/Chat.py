"""
Corpus AI - Chat Q&A Page
==========================
Full RAG Chat interface. Sends user questions to the FastAPI backend,
receives answers grounded in uploaded company documents, and displays
cited source chunks inline.

ARCHITECTURE NOTE:
  User types question
    → POST /chat/query (with session_id for continuity)
    → Backend: embed question → ChromaDB similarity search (tenant-filtered)
    → Backend: inject top-k chunks into LLM prompt → Ollama Llama-3.1
    → Backend: returns answer + source citations
    → Frontend: render answer in chat bubble + expandable sources

INTERVIEW NOTE:
  "We persist session_id in Streamlit's session_state so the user can
  have multi-turn conversations. The backend maintains message history
  per session in PostgreSQL and injects the last 4 turns into the LLM
  prompt as context — giving the model conversational memory without
  an expensive state machine."
"""

import streamlit as st
from frontend.components.auth import check_auth_or_redirect
from frontend.components.sidebar import draw_sidebar
from frontend.utils.api_client import CorpusAPIClient

# ---- Guard: redirect to login if not authenticated ----
check_auth_or_redirect()

st.set_page_config(
    page_title="Corpus AI - Chat",
    page_icon="💬",
    layout="wide",
)

draw_sidebar()

# ---- API Client ----
api_client = CorpusAPIClient()
token = st.session_state.access_token

# ---- Session State Initialization ----
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []          # List of message dicts
if "current_session_id" not in st.session_state:
    st.session_state.current_session_id = None  # Backend ChatSession UUID


# ============================================================
# Page Header
# ============================================================
col_title, col_btn = st.columns([5, 1])
with col_title:
    st.title("💬 Chat with your Documents")
    st.caption("Answers are grounded **only** in your company's uploaded documents. Sources are always cited.")
with col_btn:
    st.write("")  # spacing
    if st.button("🔄 New Chat", use_container_width=True):
        st.session_state.chat_history = []
        st.session_state.current_session_id = None
        st.rerun()

st.divider()


# ============================================================
# Previous Session Loader (Sidebar-style selector)
# ============================================================
with st.expander("📂 Load a previous conversation", expanded=False):
    sessions_res = api_client.get_chat_sessions(token)
    if sessions_res["success"] and sessions_res["data"]["sessions"]:
        sessions = sessions_res["data"]["sessions"]
        session_labels = {s["title"] or f"Session {i+1}": s["id"] for i, s in enumerate(sessions)}
        chosen_label = st.selectbox("Select session", options=list(session_labels.keys()))
        if st.button("Load session"):
            chosen_id = session_labels[chosen_label]
            hist_res = api_client.get_chat_history(chosen_id, token)
            if hist_res["success"]:
                # Re-hydrate chat history from backend
                st.session_state.chat_history = []
                st.session_state.current_session_id = chosen_id
                for msg in hist_res["data"]["messages"]:
                    entry = {"role": msg["role"], "content": msg["content"]}
                    if msg.get("sources"):
                        entry["sources"] = msg["sources"]
                    st.session_state.chat_history.append(entry)
                st.rerun()
            else:
                st.error("Failed to load session history.")
    else:
        st.info("No previous sessions found. Start a new conversation below.")


# ============================================================
# Chat Message Display
# ============================================================
if not st.session_state.chat_history:
    # Empty state hint
    st.markdown(
        """
        <div style="text-align:center; color:#888; margin-top:60px;">
            <div style="font-size:48px;">🧠</div>
            <p style="font-size:18px; margin-top:10px;">Ask me anything about your company's documents</p>
            <p style="font-size:13px;">e.g. "What is our leave policy?" or "Summarize the Q3 financial report."</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
else:
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

            # Show cited sources for assistant messages
            if msg["role"] == "assistant" and msg.get("sources"):
                sources = msg["sources"]
                if sources:
                    with st.expander(f"📎 {len(sources)} Source(s) cited", expanded=False):
                        for i, src in enumerate(sources):
                            score = src.get("relevance_score", 0)
                            score_pct = int(score * 100)
                            doc_name = src.get("document_name", "Unknown Document")
                            preview = src.get("text_preview", "")

                            # Colour-code by relevance score
                            if score_pct >= 75:
                                badge = "🟢"
                            elif score_pct >= 50:
                                badge = "🟡"
                            else:
                                badge = "🔴"

                            st.markdown(
                                f"**{badge} Source {i+1}: {doc_name}** "
                                f"— Relevance: `{score_pct}%`"
                            )
                            st.caption(f'"{preview}"')
                            if i < len(sources) - 1:
                                st.divider()


# ============================================================
# Chat Input Box
# ============================================================
if prompt := st.chat_input("Ask a question about your company docs..."):

    # 1. Show user's message immediately
    st.session_state.chat_history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 2. Call the RAG backend
    with st.chat_message("assistant"):
        with st.spinner("🔍 Searching documents and generating answer..."):
            res = api_client.query_chat(
                question=prompt,
                session_id=st.session_state.current_session_id,
                token=token,
            )

        if res["success"]:
            data = res["data"]
            answer = data.get("answer", "Sorry, I could not generate an answer.")
            sources = data.get("sources", [])
            meta = data.get("metadata", {})

            # Persist session_id so next message continues the thread
            if not st.session_state.current_session_id:
                st.session_state.current_session_id = data.get("session_id")

            # Render answer
            st.markdown(answer)

            # Render latency badge
            latency = meta.get("latency_ms")
            if latency:
                st.caption(f"⚡ Answered in {latency}ms · Model: {meta.get('model', 'llama3.1')}")

            # Render cited sources inline
            if sources:
                with st.expander(f"📎 {len(sources)} Source(s) cited", expanded=True):
                    for i, src in enumerate(sources):
                        score = src.get("relevance_score", 0)
                        score_pct = int(score * 100)
                        doc_name = src.get("document_name", "Unknown Document")
                        preview = src.get("text_preview", "")

                        badge = "🟢" if score_pct >= 75 else ("🟡" if score_pct >= 50 else "🔴")
                        st.markdown(
                            f"**{badge} Source {i+1}: {doc_name}** — Relevance: `{score_pct}%`"
                        )
                        st.caption(f'"{preview}"')
                        if i < len(sources) - 1:
                            st.divider()

            # Save to local chat history
            st.session_state.chat_history.append({
                "role": "assistant",
                "content": answer,
                "sources": sources,
            })

        else:
            # API error — show a user-friendly error and still log it
            error_msg = res.get("error", {}).get("message", "Unknown backend error.")
            status_code = res.get("status_code", 500)

            if status_code == 503:
                friendly = (
                    "⚠️ **AI service is offline.**\n\n"
                    "The local Ollama LLM is not running. "
                    "Please start it with:\n```\nollama run llama3.1:8b\n```"
                )
            elif status_code == 429:
                friendly = (
                    "⏱️ **Rate limit reached.**\n\n"
                    "You have hit the 20 queries/hour limit. Please wait before asking again."
                )
            elif status_code == 401:
                friendly = "🔒 **Session expired.** Please log in again."
            else:
                friendly = f"❌ **Error:** {error_msg}"

            st.markdown(friendly)
            st.session_state.chat_history.append({
                "role": "assistant",
                "content": friendly,
            })

    # Force page rerun to update the message list correctly
    st.rerun()
