"""
Corpus AI - Chat Router
=======================
Endpoints for querying the RAG pipeline, retrieving chat sessions, and loading conversation history.
"""

import time
import logging
import hashlib
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import ollama
import redis as redis_lib

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


def _get_redis_client() -> Optional[redis_lib.Redis]:
    """Obtain a Redis client instance with a short timeout. Returns None if unreachable."""
    try:
        r = redis_lib.from_url(settings.REDIS_URL, socket_timeout=1, decode_responses=True)
        r.ping()
        return r
    except Exception as e:
        logger.debug("Redis unavailable for caching/rate-limiting: %s", e)
        return None


def _check_rate_limit(redis_client: Optional[redis_lib.Redis], user_id: str, limit: int) -> bool:
    """Enforce hourly sliding-window rate limiting per user. Returns False if exceeded."""
    if not redis_client:
        return True  # Graceful fallback if Redis is down
    try:
        now_hour = datetime.now(timezone.utc).strftime("%Y%m%d%H")
        key = f"rate_limit:{user_id}:{now_hour}"
        current = redis_client.incr(key)
        if current == 1:
            redis_client.expire(key, 3600)
        return current <= limit
    except Exception as e:
        logger.warning("Error checking rate limit in Redis: %s", e)
        return True


def _get_cached_answer(redis_client: Optional[redis_lib.Redis], company_id: str, question: str) -> Optional[Dict[str, Any]]:
    """Retrieve cached Q&A response for identical questions within the tenant."""
    if not redis_client:
        return None
    try:
        q_hash = hashlib.sha256(question.lower().strip().encode()).hexdigest()
        key = f"chat_cache:{company_id}:{q_hash}"
        data = redis_client.get(key)
        if data:
            return json.loads(data)
    except Exception as e:
        logger.warning("Error reading chat cache from Redis: %s", e)
    return None


def _set_cached_answer(
    redis_client: Optional[redis_lib.Redis],
    company_id: str,
    question: str,
    answer: str,
    sources: List[Dict[str, Any]],
    ttl: int = 3600,
) -> None:
    """Cache answer and sources for 1 hour to reduce redundant LLM calls."""
    if not redis_client:
        return
    try:
        q_hash = hashlib.sha256(question.lower().strip().encode()).hexdigest()
        key = f"chat_cache:{company_id}:{q_hash}"
        payload = {"answer": answer, "sources": sources}
        redis_client.setex(key, ttl, json.dumps(payload))
    except Exception as e:
        logger.warning("Error writing chat cache to Redis: %s", e)


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

    redis_client = _get_redis_client()

    # Rate limiting: Maximum queries per hour per user
    if not _check_rate_limit(redis_client, current_user.id, settings.RATE_LIMIT_PER_HOUR):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Maximum {settings.RATE_LIMIT_PER_HOUR} queries per hour allowed.",
        )

    # Check cache for recent/frequent identical questions in this tenant
    cached = _get_cached_answer(redis_client, current_user.company_id, question)
    if cached:
        latency_ms = max(1, int((time.time() - start_time) * 1000))
        cached_answer = cached.get("answer", "")
        cached_sources = [Source(**s) for s in cached.get("sources", [])]

        user_msg = ChatMessage(session_id=session_id, role="user", content=question)
        assistant_msg = ChatMessage(
            session_id=session_id,
            role="assistant",
            content=cached_answer,
            sources=[s.model_dump() for s in cached_sources],
            metadata_={
                "latency_ms": latency_ms,
                "model": settings.OLLAMA_MODEL,
                "cached": True,
            },
        )
        db.add(user_msg)
        db.add(assistant_msg)

        query_log = QueryLog(
            company_id=current_user.company_id,
            user_id=current_user.id,
            question=question,
            latency_ms=latency_ms,
            cache_hit=True,
            top_score=cached_sources[0].relevance_score if cached_sources else None,
        )
        db.add(query_log)
        db.commit()

        logger.info("Serving answer from Redis cache in %dms", latency_ms)
        return ChatResponse(
            answer=cached_answer,
            sources=cached_sources,
            session_id=session_id,
            metadata={
                "latency_ms": latency_ms,
                "model": settings.OLLAMA_MODEL,
                "cached": True,
            },
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

        # 9. Cache answer in Redis for 1 hour for subsequent identical queries
        _set_cached_answer(
            redis_client=redis_client,
            company_id=current_user.company_id,
            question=question,
            answer=answer,
            sources=[s.model_dump() for s in sources],
        )

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
