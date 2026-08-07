"""Per-tenant vector RAG over business documentation."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from config import DOCS_DIR, MAX_DOC_CHARS, USE_VECTOR_RAG, VECTOR_DB_DIR
from doc_loader import format_doc_context, load_all_docs, search_docs

logger = logging.getLogger(__name__)

_collections: dict[str, object] = {}
_initialized: set[str] = set()


def _collection_name(tenant_id: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", tenant_id)
    return f"business_docs_{safe}"


def _tokenize(text: str) -> set[str]:
    return {w.lower() for w in re.findall(r"\w+", text) if len(w) > 2}


def _chunk_text(text: str, source: str, chunk_size: int = 800) -> list[str]:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) > chunk_size and current:
            chunks.append(f"[{source}]\n{current}")
            current = para
        else:
            current = f"{current}\n\n{para}".strip() if current else para
    if current:
        chunks.append(f"[{source}]\n{current}")
    return chunks or [text[:chunk_size]]


def _init_chroma(documents: dict[str, str], tenant_id: str) -> bool:
    if tenant_id in _initialized:
        return tenant_id in _collections and _collections[tenant_id] is not None

    _initialized.add(tenant_id)

    if not USE_VECTOR_RAG or not documents:
        _collections[tenant_id] = None
        return False

    try:
        import chromadb

        VECTOR_DB_DIR.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(VECTOR_DB_DIR))
        collection = client.get_or_create_collection(_collection_name(tenant_id))

        if collection.count() == 0:
            ids, docs, metas = [], [], []
            for name, content in documents.items():
                chunks = _chunk_text(content, name)
                for i, chunk in enumerate(chunks):
                    ids.append(f"{tenant_id}::{name}::{i}")
                    docs.append(chunk)
                    metas.append({"source": name, "tenant_id": tenant_id})
            if ids:
                collection.add(ids=ids, documents=docs, metadatas=metas)
                logger.info("Indexed %d chunks for tenant %s", len(ids), tenant_id)

        _collections[tenant_id] = collection
        return True
    except Exception as exc:
        logger.warning("Vector RAG unavailable for %s: %s", tenant_id, exc)
        _collections[tenant_id] = None
        return False


def vector_search(
    query: str,
    documents: dict[str, str] | None = None,
    top_k: int = 4,
    tenant_id: str = "default",
) -> str:
    """Search docs via vector similarity for a tenant, falling back to keyword search."""
    docs = documents if documents is not None else load_all_docs(DOCS_DIR)

    if _init_chroma(docs, tenant_id):
        collection = _collections.get(tenant_id)
        if collection is not None:
            try:
                results = collection.query(query_texts=[query], n_results=top_k)
                if results and results.get("documents"):
                    chunks = []
                    for i, doc in enumerate(results["documents"][0]):
                        meta = results["metadatas"][0][i] if results.get("metadatas") else {}
                        source = meta.get("source", "doc")
                        chunks.append((source, doc, 1.0 - i * 0.1))
                    return format_doc_context(chunks, MAX_DOC_CHARS)
            except Exception as exc:
                logger.warning("Vector search failed for %s: %s", tenant_id, exc)

    hits = search_docs(query, docs, top_k=top_k)
    return format_doc_context(hits, MAX_DOC_CHARS)


def reindex_documents(docs_dir: Path | None = None, tenant_id: str = "default") -> int:
    """Force reindex of tenant documents."""
    global _collections
    _initialized.discard(tenant_id)
    _collections.pop(tenant_id, None)

    docs = load_all_docs(docs_dir)
    if _init_chroma(docs, tenant_id):
        collection = _collections.get(tenant_id)
        if collection is not None:
            try:
                import chromadb

                client = chromadb.PersistentClient(path=str(VECTOR_DB_DIR))
                name = _collection_name(tenant_id)
                try:
                    client.delete_collection(name)
                except Exception:
                    pass
                _initialized.discard(tenant_id)
                _collections.pop(tenant_id, None)
                return reindex_documents(docs_dir, tenant_id)
            except Exception:
                return collection.count()
    return len(docs)
