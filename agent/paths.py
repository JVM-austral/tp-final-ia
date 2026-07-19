from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MEMORY_STORE_DIR = PROJECT_ROOT / "memory_store"
RAG_DOCS_DIR = PROJECT_ROOT / "rag_sources" / "nestjs"
RAG_CHROMA_DIR = PROJECT_ROOT / "rag_sources" / "chroma_db"
