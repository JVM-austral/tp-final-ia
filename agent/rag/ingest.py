"""Ingesta del corpus RAG: chunking por headers de markdown + ventana de
tokens, embeddings con OpenAI (text-embedding-3-small) y carga en ChromaDB
persistente local.

Estrategia de chunking: primero se parte cada doc por sus headers de
markdown (## a ####), preservando la ruta de títulos como contexto; cada
sección se subdivide en ventanas de ~500 tokens con 50 de solapamiento
(tiktoken, encoding cl100k_base) para no cortar ideas a mitad de camino ni
mandar secciones enteras gigantes al embedding.
"""

import re
from pathlib import Path

import tiktoken

from ..paths import RAG_CHROMA_DIR, RAG_DOCS_DIR
from .store import get_collection

CHUNK_TOKENS = 500
CHUNK_OVERLAP = 50
EMBEDDING_MODEL = "text-embedding-3-small"

_encoder = tiktoken.get_encoding("cl100k_base")

HEADER_RE = re.compile(r"^(#{2,4})\s+(.*)$", re.MULTILINE)


def split_by_headers(text: str) -> list:
    """Divide un markdown en secciones (heading_path, contenido) usando
    headers de nivel ## a ####."""
    matches = list(HEADER_RE.finditer(text))
    if not matches:
        return [("", text)]

    sections = []
    heading_stack = []

    if matches[0].start() > 0:
        preamble = text[: matches[0].start()].strip()
        if preamble:
            sections.append(("", preamble))

    for i, m in enumerate(matches):
        level = len(m.group(1))
        title = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()

        heading_stack = [h for h in heading_stack if h[0] < level]
        heading_stack.append((level, title))
        heading_path = " > ".join(t for _, t in heading_stack)

        if content:
            sections.append((heading_path, content))

    return sections


def _token_windows(text: str, size: int, overlap: int):
    tokens = _encoder.encode(text)
    if len(tokens) <= size:
        yield tokens
        return
    step = size - overlap
    start = 0
    while start < len(tokens):
        window = tokens[start : start + size]
        if not window:
            break
        yield window
        if start + size >= len(tokens):
            break
        start += step


def chunk_document(source_name: str, text: str) -> list:
    """Devuelve una lista de chunks {text, source, heading} listos para
    embeddear."""
    chunks = []
    for heading, content in split_by_headers(text):
        for window in _token_windows(content, CHUNK_TOKENS, CHUNK_OVERLAP):
            chunk_text = _encoder.decode(window)
            prefix = f"[{source_name} > {heading}]\n" if heading else f"[{source_name}]\n"
            chunks.append({"text": prefix + chunk_text, "source": source_name, "heading": heading})
    return chunks


def embed_texts(client, texts: list) -> list:
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    return [d.embedding for d in response.data]


def ingest_directory(
    client,
    docs_dir: str = str(RAG_DOCS_DIR),
    persist_dir: str = str(RAG_CHROMA_DIR),
) -> int:
    """Lee todos los .md de docs_dir, los chunkea, embeddea y carga en
    Chroma. Devuelve la cantidad de chunks indexados."""
    collection = get_collection(persist_dir)

    existing_ids = collection.get()["ids"]
    if existing_ids:
        collection.delete(ids=existing_ids)

    all_chunks = []
    for path in sorted(Path(docs_dir).glob("*.md")):
        text = path.read_text(encoding="utf-8")
        all_chunks.extend(chunk_document(path.stem, text))

    batch_size = 64
    total = 0
    for i in range(0, len(all_chunks), batch_size):
        batch = all_chunks[i : i + batch_size]
        embeddings = embed_texts(client, [c["text"] for c in batch])
        ids = [f"{c['source']}-{i + j}" for j, c in enumerate(batch)]
        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=[c["text"] for c in batch],
            metadatas=[{"source": c["source"], "heading": c["heading"]} for c in batch],
        )
        total += len(batch)
    return total
