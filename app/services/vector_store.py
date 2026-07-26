"""
Corpus AI - Vector Store Service
===============================
Manages interactions with ChromaDB for document storage and semantic queries.
"""

import logging
import chromadb
from app.config import settings

logger = logging.getLogger("corpus_ai.vector_store")


class VectorStoreService:
    """Interface to ChromaDB vector store with tenant isolation constraints."""

    def __init__(self):
        self._client = None
        self._collection = None
        self.collection_name = "corpus_ai_documents"

    @property
    def client(self) -> chromadb.PersistentClient:
        if self._client is None:
            logger.info("Initializing ChromaDB persistent client at: %s", settings.chroma_path)
            try:
                self._client = chromadb.PersistentClient(path=str(settings.chroma_path))
            except Exception as e:
                logger.error("Failed to initialize ChromaDB client: %s", e, exc_info=True)
                raise RuntimeError(f"ChromaDB connection error: {str(e)}") from e
        return self._client

    @property
    def collection(self):
        if self._collection is None:
            try:
                # We do not pass an embedding function to Chroma because we compute
                # embeddings ourselves using the local sentence-transformers model.
                self._collection = self.client.get_or_create_collection(
                    name=self.collection_name,
                    metadata={"hnsw:space": "cosine"}  # Use cosine similarity space
                )
                logger.info("ChromaDB collection '%s' initialized", self.collection_name)
            except Exception as e:
                logger.error("Failed to get/create ChromaDB collection: %s", e, exc_info=True)
                raise RuntimeError(f"ChromaDB collection error: {str(e)}") from e
        return self._collection

    def add_chunks(
        self,
        company_id: str,
        document_id: str,
        ids: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict],
        documents: list[str],
    ) -> None:
        """Add document chunks and their vector embeddings to ChromaDB.
        
        All metadatas must include 'company_id' and 'document_id' to enforce security filters.
        """
        if not ids:
            return

        # Double check metadata security fields are present on each item
        for meta in metadatas:
            meta["company_id"] = company_id
            meta["document_id"] = document_id

        try:
            logger.info("Inserting %d chunks into ChromaDB for doc: %s", len(ids), document_id)
            self.collection.add(
                ids=ids,
                embeddings=embeddings,
                metadatas=metadatas,
                documents=documents
            )
            logger.info("ChromaDB insert successful for doc: %s", document_id)
        except Exception as e:
            logger.error("ChromaDB insertion failed: %s", e, exc_info=True)
            raise RuntimeError(f"Error saving to vector database: {str(e)}") from e

    def delete_document_chunks(self, company_id: str, document_id: str) -> None:
        """Remove all text chunks and vectors associated with a document.
        
        Enforces tenant isolation by matching both company_id and document_id.
        """
        try:
            logger.info("Deleting chunks from ChromaDB for doc: %s under company: %s", document_id, company_id)
            self.collection.delete(
                where={
                    "$and": [
                        {"company_id": company_id},
                        {"document_id": document_id}
                    ]
                }
            )
            logger.info("ChromaDB deletion successful for doc: %s", document_id)
        except Exception as e:
            logger.error("ChromaDB deletion failed: %s", e, exc_info=True)
            raise RuntimeError(f"Error removing from vector database: {str(e)}") from e

    def similarity_search(
        self,
        company_id: str,
        query_embedding: list[float],
        top_k: int = 5,
    ) -> list[dict]:
        """Perform semantic search against ChromaDB, restricted to the tenant company_id.
        
        Returns:
            list of dicts containing:
            - id
            - text (document text)
            - metadata (document_id, company_id, etc.)
            - relevance_score
        """
        try:
            logger.debug("Performing similarity search for company: %s", company_id)
            
            # Enforce strict metadata filter for tenant separation
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where={"company_id": company_id}
            )

            formatted_results = []
            if not results or not results["ids"] or not results["ids"][0]:
                return formatted_results

            # Unpack Chroma query results
            ids = results["ids"][0]
            documents = results["documents"][0]
            metadatas = results["metadatas"][0]
            distances = results["distances"][0]

            for idx in range(len(ids)):
                # Distance in cosine space is (1 - cosine_similarity).
                # Convert distance to a similarity score (relevance): 1.0 - distance
                relevance = 1.0 - distances[idx]
                
                formatted_results.append({
                    "id": ids[idx],
                    "text": documents[idx],
                    "metadata": metadatas[idx],
                    "relevance_score": float(relevance)
                })

            return formatted_results

        except Exception as e:
            logger.error("ChromaDB similarity query failed: %s", e, exc_info=True)
            raise RuntimeError(f"Vector search query failed: {str(e)}") from e


# Singleton service instance
vector_store = VectorStoreService()
