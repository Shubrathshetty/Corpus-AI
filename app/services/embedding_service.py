"""
Corpus AI - Embedding Service
=============================
Generates vector embeddings for document chunks using SentenceTransformers.
"""

import logging
from sentence_transformers import SentenceTransformer
from app.config import settings

logger = logging.getLogger("corpus_ai.embedding_service")


class EmbeddingService:
    """Lazy-loaded embedding service using a local sentence-transformers model."""

    def __init__(self):
        self._model = None

    @property
    def model(self) -> SentenceTransformer:
        if self._model is None:
            logger.info("Loading embedding model: %s", settings.EMBEDDING_MODEL)
            try:
                # Load sentence transformer model locally
                self._model = SentenceTransformer(settings.EMBEDDING_MODEL)
                logger.info("Embedding model loaded successfully")
            except Exception as e:
                logger.error("Failed to load embedding model %s: %s", settings.EMBEDDING_MODEL, e, exc_info=True)
                raise RuntimeError(f"Error loading embedding model: {str(e)}") from e
        return self._model

    def get_embedding(self, text: str) -> list[float]:
        """Generate a 384-dimensional dense vector for a single text string."""
        if not text.strip():
            # Return zero vector if text is empty (all-MiniLM-L6-v2 outputs 384 dimensions)
            return [0.0] * 384
        
        try:
            vector = self.model.encode(text, convert_to_numpy=True)
            return vector.tolist()
        except Exception as e:
            logger.error("Failed to compute embedding for text: %s", e, exc_info=True)
            raise RuntimeError(f"Embedding computation error: {str(e)}") from e

    def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Generate dense vectors in bulk for a list of text strings."""
        if not texts:
            return []
        
        try:
            vectors = self.model.encode(texts, convert_to_numpy=True)
            return vectors.tolist()
        except Exception as e:
            logger.error("Failed to compute bulk embeddings: %s", e, exc_info=True)
            raise RuntimeError(f"Bulk embedding computation error: {str(e)}") from e


# Singleton service instance
embedding_service = EmbeddingService()
