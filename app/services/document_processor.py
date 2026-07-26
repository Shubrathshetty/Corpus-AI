"""
Corpus AI - Document Processor Service
======================================
Parses uploaded files and splits them into clean text chunks.
Supports: PDF, DOCX, TXT, MD
"""

import logging
from pathlib import Path
from docx import Document as DocxDocument
from PyPDF2 import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger("corpus_ai.document_processor")


def extract_text_from_pdf(file_path: Path) -> str:
    """Extract text page-by-page from a PDF file using PyPDF2."""
    logger.info("Extracting text from PDF: %s", file_path)
    text_content = []
    try:
        reader = PdfReader(str(file_path))
        for page_idx, page in enumerate(reader.pages):
            page_text = page.extract_text()
            if page_text:
                text_content.append(page_text)
            else:
                logger.warning("Empty text extracted from page %d of %s", page_idx + 1, file_path)
    except Exception as e:
        logger.error("Failed to extract text from PDF %s: %s", file_path, e, exc_info=True)
        raise RuntimeError(f"Error parsing PDF: {str(e)}") from e
    
    return "\n\n".join(text_content)


def extract_text_from_docx(file_path: Path) -> str:
    """Extract text from Word document paragraphs using python-docx."""
    logger.info("Extracting text from DOCX: %s", file_path)
    try:
        doc = DocxDocument(str(file_path))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs)
    except Exception as e:
        logger.error("Failed to extract text from DOCX %s: %s", file_path, e, exc_info=True)
        raise RuntimeError(f"Error parsing DOCX: {str(e)}") from e


def extract_text_from_txt(file_path: Path) -> str:
    """Extract text from plain text or markdown files."""
    logger.info("Extracting text from TXT/MD: %s", file_path)
    try:
        return file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # Fallback to latin-1 if utf-8 fails
        try:
            return file_path.read_text(encoding="latin-1")
        except Exception as e:
            logger.error("Failed to extract text from TXT %s: %s", file_path, e, exc_info=True)
            raise RuntimeError(f"Error parsing text file: {str(e)}") from e
    except Exception as e:
        logger.error("Failed to extract text from TXT %s: %s", file_path, e, exc_info=True)
        raise RuntimeError(f"Error parsing text file: {str(e)}") from e


def extract_text(file_path: str) -> str:
    """Detects file type and extracts all text."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_text_from_pdf(path)
    elif suffix == ".docx":
        return extract_text_from_docx(path)
    elif suffix in [".txt", ".md"]:
        return extract_text_from_txt(path)
    else:
        raise ValueError(f"Unsupported file format: {suffix}")


def split_text(text: str, chunk_size: int = 1000, chunk_overlap: int = 200) -> list[str]:
    """Splits raw text into overlapping semantic chunks.
    
    Uses LangChain's RecursiveCharacterTextSplitter to split by logical
    delimiters (paragraphs, sentences) to maintain semantic context.
    """
    if not text.strip():
        return []

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", " ", ""],
    )
    return splitter.split_text(text)
