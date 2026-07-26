"""
Corpus AI - Chat Router
=======================
Endpoints for querying the RAG pipeline, retrieving chat sessions, and loading conversation history.
"""

import time
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import ollama

from app.auth import get_current_user
from app.config import settings
from app.db import get_db
from app.models import ChatMessage, ChatSession, QueryLog, User, utc_now
from app.schemas import (
    ChatHistoryMessage,
    ChatHistoryResponse,
    ChatQuery,
    ChatResponse,
    ChatSessionListItem,
    ChatSessionListResponse,
    Source,
)
from app.services.embedding_service import embedding_service
from app.services.vector_store import vector_store

logger = logging.getLogger("corpus_ai.chat_router")

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post(
    "/query",
    response_model=ChatResponse,
    summary="Ask a question grounded in the workspace documentation (RAG)",
)
def query_chat(
    data: ChatQuery,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Processes user prompt via RAG (Retrieval-Augmented Generation).
    
    1. Validates or creates a ChatSession.
    2. Generates an embedding for the user prompt.
    3. Finds top matching document passages in ChromaDB (enforcing tenant isolation).
    4. Formulates history context & passes context to local Ollama model.
    5. Stores user/assistant chat history and logs metrics.
    """
    start_time = time.time()
    question = data.question.strip()
    session_id = data.session_id

    # 1. Resolve Chat Session
    if not session_id:
        # Create a new session if not specified
        chat_session = ChatSession(
            company_id=current_user.company_id,
            user_id=current_user.id,
            title=question[:47] + "..." if len(question) > 50 else question
        )
        db.add(chat_session)
        db.commit()
        db.refresh(chat_session)
        session_id = chat_session.id
        logger.info("Created new chat session: %s", session_id)
    else:
        # Verify existing session belongs to this tenant and user
        chat_session = db.query(ChatSession).filter(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id,
            ChatSession.company_id == current_user.company_id
        ).first()
        if not chat_session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat session not found or access denied",
            )

    try:
        # 2. Embed the question
        query_vector = embedding_service.get_embedding(question)

        # 3. Retrieve relevant chunks from ChromaDB (with tenant constraint)
        search_results = vector_store.similarity_search(
            company_id=current_user.company_id,
            query_embedding=query_vector,
            top_k=4  # Fetch top 4 context chunks
        )

        sources = []
        context_chunks = []
        top_score = None
        
        for res in search_results:
            relevance = res["relevance_score"]
            if top_score is None or relevance > top_score:
                top_score = relevance
                
            sources.append(
                Source(
                    document_name=res["metadata"].get("filename", "Unknown Document"),
                    chunk_id=res["id"],
                    relevance_score=relevance,
                    text_preview=res["text"][:200] + "..." if len(res["text"]) > 200 else res["text"]
                )
            )
            # Format text segment for system prompt context
            context_chunks.append(
                f"Document: {res['metadata'].get('filename')}\nContent: {res['text']}"
            )

        context_str = "\n\n".join(context_chunks) if context_chunks else "No document context matches your request."

        # 4. Fetch last 4 turns of message history to construct prompt memory
        history_messages = db.query(ChatMessage).filter(
            ChatMessage.session_id == session_id
        ).order_by(ChatMessage.created_at.desc()).limit(4).all()
        
        # Reverse history so it flows chronologically
        history_messages.reverse()

        # 5. Formulate prompt messages list
        system_prompt = (
            "You are a helpful, professional enterprise search AI assistant for Corpus AI.\n"
            "Answer the user's question using ONLY the provided document context below.\n"
            "If the context does not contain the answer, politely state that you do not have that information.\n"
            "Provide clean, detailed, markdown-formatted answers. Cite your sources clearly if multiple are provided.\n\n"
            f"--- DOCUMENT CONTEXT ---\n{context_str}\n-------------------------"
        )

        prompt_msgs = [{"role": "system", "content": system_prompt}]
        for h_msg in history_messages:
            prompt_msgs.append({"role": h_msg.role, "content": h_msg.content})
        prompt_msgs.append({"role": "user", "content": question})

        # 6. Call local Ollama LLM
        logger.info("Calling Ollama chat model: %s", settings.OLLAMA_MODEL)
        try:
            client = ollama.Client(host=settings.OLLAMA_BASE_URL)
            response = client.chat(
                model=settings.OLLAMA_MODEL,
                messages=prompt_msgs,
                options={"temperature": 0.2}  # Keep answers grounded & factual
            )
            answer = response["message"]["content"]
        except Exception as ollama_err:
            logger.error("Failed to connect to local Ollama service: %s", ollama_err, exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Local AI reasoning service is offline. "
                    "Verify that Ollama is running and the model has been pulled: "
                    f"ollama pull {settings.OLLAMA_MODEL}"
                ),
            )

        latency_ms = int((time.time() - start_time) * 1000)
        logger.info("Answer generated in %dms", latency_ms)

        # 7. Persist chat messages in database
        user_msg = ChatMessage(
            session_id=session_id,
            role="user",
            content=question
        )
        assistant_msg = ChatMessage(
            session_id=session_id,
            role="assistant",
            content=answer,
            sources=[s.model_dump() for s in sources],
            metadata_={
                "latency_ms": latency_ms,
                "model": settings.OLLAMA_MODEL,
                "context_chunks_count": len(context_chunks)
            }
        )
        db.add(user_msg)
        db.add(assistant_msg)

        # Update session title if default placeholder
        if chat_session.title.endswith("..."):
            # Update title timestamp to keep sorting active
            chat_session.updated_at = utc_now()

        # 8. Log telemetry query metrics
        query_log = QueryLog(
            company_id=current_user.company_id,
            user_id=current_user.id,
            question=question,
            latency_ms=latency_ms,
            cache_hit=False,
            top_score=top_score
        )
        db.add(query_log)
        
        db.commit()

        return ChatResponse(
            answer=answer,
            sources=sources,
            session_id=session_id,
            metadata={
                "latency_ms": latency_ms,
                "model": settings.OLLAMA_MODEL,
                "cached": False
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("RAG pipeline failed: %s", e, exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat pipeline error: {str(e)}",
        )


@router.get(
    "/sessions",
    response_model=ChatSessionListResponse,
    summary="List previous user chat sessions",
)
def list_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returns all chat threads started by the authenticated user in this tenant."""
    try:
        sessions = db.query(ChatSession).filter(
            ChatSession.user_id == current_user.id,
            ChatSession.company_id == current_user.company_id
        ).order_by(ChatSession.created_at.desc()).all()

        session_list = []
        for s in sessions:
            msg_count = db.query(ChatMessage).filter(ChatMessage.session_id == s.id).count()
            session_list.append(
                ChatSessionListItem(
                    id=s.id,
                    title=s.title,
                    created_at=s.created_at,
                    message_count=msg_count
                )
            )

        return ChatSessionListResponse(
            sessions=session_list,
            total=len(session_list)
        )
    except Exception as e:
        logger.error("Failed to query chat sessions: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to query chat threads",
        )


@router.get(
    "/history",
    response_model=ChatHistoryResponse,
    summary="Get full conversation history for a chat session",
)
def get_history(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve full chronological messages list inside a chat session thread."""
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id,
        ChatSession.company_id == current_user.company_id
    ).first()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat thread not found or access denied",
        )

    try:
        messages = db.query(ChatMessage).filter(
            ChatMessage.session_id == session_id
        ).order_by(ChatMessage.created_at.asc()).all()

        formatted_messages = []
        for m in messages:
            sources_list = None
            if m.sources:
                sources_list = [Source(**s) for s in m.sources]

            formatted_messages.append(
                ChatHistoryMessage(
                    id=m.id,
                    role=m.role,
                    content=m.content,
                    sources=sources_list,
                    metadata=m.metadata_ or {},
                    created_at=m.created_at
                )
            )

        return ChatHistoryResponse(
            session_id=session_id,
            title=session.title,
            messages=formatted_messages
        )
    except Exception as e:
        logger.error("Failed to fetch session history: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to query thread messages history",
        )
