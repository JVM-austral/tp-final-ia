import chromadb

from ..paths import RAG_CHROMA_DIR

_client = None
_collection = None
_collection_path = None


def get_collection(persist_dir: str = str(RAG_CHROMA_DIR), name: str = "nestjs_docs"):
    global _client, _collection, _collection_path
    if _collection is not None and _collection_path == persist_dir:
        return _collection
    _client = chromadb.PersistentClient(path=persist_dir)
    _collection = _client.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})
    _collection_path = persist_dir
    return _collection


def query(client_openai, query_text: str, k: int = 4, persist_dir: str = str(RAG_CHROMA_DIR)) -> list:

    from .ingest import embed_texts

    collection = get_collection(persist_dir)
    if collection.count() == 0:
        return []

    embedding = embed_texts(client_openai, [query_text])[0]
    results = collection.query(query_embeddings=[embedding], n_results=min(k, collection.count()))

    out = []
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    dists = results.get("distances", [[]])[0]
    for doc, meta, dist in zip(docs, metas, dists):
        out.append(
            {
                "text": doc,
                "source": meta.get("source", ""),
                "heading": meta.get("heading", ""),
                "score": 1 - dist,
            }
        )
    return out
