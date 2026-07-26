"""
Corpus AI - Documents Router
===========================
Endpoints for uploading, listing, and deleting company documents.
Only Admins are authorized to upload or delete documents.
"""

import os
import logging
import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_role
from app.config import settings
from app.db import get_db
from app.models import Document, DocumentStatus, User
from app.schemas import DocumentListResponse, DocumentResponse, DocumentStatus as SchemaStatus
from app.services.vector_store import vector_store
# Import task inside routers or lazily to avoid startup circular dependencies
from app.worker import process_document_task

logger = logging.getLogger("corpus_ai.document_router")

router = APIRouter(prefix="/documents", tags=["Documents"])

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10MB limit


@router.post(
    "/upload",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a new workspace document (admin only)",
)
async def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(require_role("admin", "super_admin")),
    db: Session = Depends(get_db),
):
    """Uploads a company file and triggers the asynchronous vector search parsing pipeline.
    
    Restricted to Admin users to enforce tenant file ownership rules.
    """
    filename = file.filename
    file_ext = Path(filename).suffix.lower()

    # Validate file type
    if file_ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{file_ext}'. Allowed formats: {', '.join(SUPPORTED_EXTENSIONS)}",
        )

    # Generate document ID and disk storage destination
    doc_id = str(uuid.uuid4())
    upload_file_path = settings.upload_path / f"{doc_id}{file_ext}"

    # Read and save file chunk-by-chunk to avoid high RAM spikes
    file_size_bytes = 0
    try:
        with open(upload_file_path, "wb") as buffer:
            while chunk := await file.read(8192):
                file_size_bytes += len(chunk)
                if file_size_bytes > MAX_FILE_SIZE_BYTES:
                    # Clean up partial upload before raising error
                    buffer.close()
                    os.unlink(upload_file_path)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File exceeds maximum allowed size of {MAX_FILE_SIZE_BYTES / (1024 * 1024)}MB",
                    )
                buffer.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to write uploaded file to disk: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save uploaded file to server storage",
        )

    try:
        # Create Document record in metadata DB
        document = Document(
            id=doc_id,
            company_id=current_user.company_id,
            uploaded_by=current_user.id,
            filename=filename,
            file_type=file_ext.lstrip("."),
            file_size_bytes=file_size_bytes,
            status=DocumentStatus.UPLOADING,
            storage_path=str(upload_file_path),
        )
        db.add(document)
        db.commit()
        db.refresh(document)
        logger.info("Saved document metadata: %s for user: %s", doc_id, current_user.email)

        # Trigger background indexing Celery task
        process_document_task.delay(doc_id)
        logger.info("Queued Celery parsing task for document: %s", doc_id)

        return document

    except Exception as db_err:
        logger.error("Database metadata insert failed: %s", db_err, exc_info=True)
        # Clean up file on disk if DB record fails to keep system in sync
        if upload_file_path.exists():
            os.unlink(upload_file_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initialize document processing transaction",
        )


@router.get(
    "/",
    response_model=DocumentListResponse,
    summary="List all company workspace documents",
)
def list_documents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve all document records belonging to the current user's tenant organization.
    
    Enforces row-level multi-tenant isolation by filtering by `company_id`.
    """
    try:
        documents = db.query(Document).filter(
            Document.company_id == current_user.company_id
        ).order_by(Document.created_at.desc()).all()
        
        return DocumentListResponse(
            documents=documents,
            total=len(documents)
        )
    except Exception as e:
        logger.error("Error retrieving document list: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to query database catalog",
        )


@router.delete(
    "/{doc_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a document (admin only)",
)
def delete_document(
    doc_id: str,
    current_user: User = Depends(require_role("admin", "super_admin")),
    db: Session = Depends(get_db),
):
    """Remove a document from server disk, metadata tables, and ChromaDB vector search database.
    
    Ensures admins cannot delete documents from other tenant organizations.
    """
    # Fetch and verify document owner matches current user company
    document = db.query(Document).filter(
        Document.id == doc_id,
        Document.company_id == current_user.company_id
    ).first()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found or access denied",
        )

    try:
        logger.info("Initiating deletion sequence for doc: %s", doc_id)

        # 1. Delete vectors from ChromaDB index
        vector_store.delete_document_chunks(
            company_id=current_user.company_id,
            document_id=doc_id
        )

        # 2. Delete physical file from disk storage
        file_path = Path(document.storage_path)
        if file_path.exists():
            os.unlink(file_path)
            logger.info("Deleted physical file: %s", file_path)

        # 3. Delete DB record (will cascade-delete DocumentChunk records automatically via foreign key relationship)
        db.delete(document)
        db.commit()
        logger.info("Deleted database records for doc: %s", doc_id)

        return {"message": f"Successfully deleted document '{document.filename}' and its embeddings"}

    except Exception as e:
        logger.error("Error deleting document %s: %s", doc_id, e, exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failure during deletion operation: {str(e)}",
        )
