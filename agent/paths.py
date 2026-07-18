"""Rutas propias del agente, ancladas a la raíz de este proyecto y por lo
tanto independientes del cwd del proceso.

El harness hace `os.chdir()` al workspace del proyecto objetivo (NestJS)
para que las tools de archivos/comandos operen ahí con paths relativos.
Por eso cualquier ruta propia del agente (memoria persistente, índice RAG)
tiene que anclarse explícitamente acá en vez de usar rutas relativas, o
terminaría leyendo/escribiendo dentro del repo del usuario.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MEMORY_STORE_DIR = PROJECT_ROOT / "memory_store"
RAG_DOCS_DIR = PROJECT_ROOT / "rag_sources" / "nestjs"
RAG_CHROMA_DIR = PROJECT_ROOT / "rag_sources" / "chroma_db"
