"""
Corpus AI - Celery Worker Tasks
==============================
Asynchronous tasks for document parsing, chunking, and vector indexing.
"""

import logging
from pathlib import Path
from celery import Celery

from app.config import settings
from app.db import SessionLocal
from app.models import Document, DocumentChunk, DocumentStatus, utc_now
from app.services.document_processor import extract_text, split_text
from app.services.embedding_service import embedding_service
from app.services.vector_store import vector_store

logger = logging.getLogger("corpus_ai.worker")

# Initialize Celery Application
celery_app = Celery("corpus_ai_worker", broker=settings.REDIS_URL, backend=settings.REDIS_URL)

# Configure Celery tasks parameters
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=600,  # Max 10 minutes processing per file
)


@celery_app.task(name="app.worker.process_document_task")
def process_document_task(document_id: str) -> dict:
    """Asynchronous background task to process an uploaded document.
    
    Workflow:
    1. Reads document metadata from the SQL database.
    2. Extracts raw text based on file format (PDF, DOCX, TXT, MD).
    3. Splits text into semantic chunks using overlapping sliders.
    4. Computes vector embeddings in bulk using SentenceTransformers.
    5. Saves vector records into ChromaDB.
    6. Persists chunk metadata into SQL database for citations.
    7. Updates document status to READY.
    """
    logger.info("Starting processing for document: %s", document_id)
    db = SessionLocal()
    
    try:
        # Load document from Database
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            logger.error("Document %s not found in database", document_id)
            return {"success": False, "error": "Document not found"}

        # Update status to PROCESSING
        document.status = DocumentStatus.PROCESSING
        db.commit()
        db.refresh(document)
        logger.info("Document %s status updated to PROCESSING", document_id)

        # 1. Extract raw text
        file_path = Path(document.storage_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found on disk: {file_path}")

        raw_text = extract_text(str(file_path))
        if not raw_text.strip():
            raise ValueError("Extracted text is empty or invalid")

        logger.info("Text extraction complete. Characters extracted: %d", len(raw_text))

        # 2. Split text into chunks
        chunks = split_text(raw_text)
        if not chunks:
            raise ValueError("No text chunks generated during parsing splitter")

        logger.info("Split text into %d chunks", len(chunks))

        # 3. Compute vector embeddings in bulk
        logger.info("Computing embeddings in bulk using SentenceTransformers...")
        embeddings = embedding_service.get_embeddings(chunks)
        logger.info("Embedding computations completed successfully")

        # 4. Save to ChromaDB vector store
        ids = [f"{document_id}_chunk_{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "company_id": document.company_id,
                "document_id": document_id,
                "chunk_index": i,
                "filename": document.filename
            }
            for i in range(len(chunks))
        ]
        
        vector_store.add_chunks(
            company_id=document.company_id,
            document_id=document_id,
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
            documents=chunks
        )

        # 5. Save chunk metadata to SQL Database (used for direct text retrieval and citation links)
        for i, chunk_text in enumerate(chunks):
            # Estimate token count (standard heuristic: ~4 characters per token / ~0.75 words per token)
            word_count = len(chunk_text.split())
            token_count = int(word_count * 1.33) or 1
            
            chunk_db = DocumentChunk(
                document_id=document_id,
                chunk_index=i,
                content=chunk_text,
                token_count=token_count,
                chroma_id=ids[i]
            )
            db.add(chunk_db)

        # 6. Update Document status to READY
        document.status = DocumentStatus.READY
        document.chunk_count = len(chunks)
        document.processed_at = utc_now()
        
        db.commit()
        logger.info("Document %s processing successfully completed", document_id)
        return {"success": True, "chunks_processed": len(chunks)}

    except Exception as e:
        logger.error("Failed to process document %s: %s", document_id, e, exc_info=True)
        # Roll back any partial database transactions
        db.rollback()
        
        # Load document in clean transaction to set FAILED state
        try:
            document = db.query(Document).filter(Document.id == document_id).first()
            if document:
                document.status = DocumentStatus.FAILED
                document.error_message = str(e)
                db.commit()
                logger.info("Document %s state updated to FAILED", document_id)
        except Exception as db_err:
            logger.error("Failed to write error state for doc %s: %s", document_id, db_err)
            
        return {"success": False, "error": str(e)}

    finally:
        db.close()
