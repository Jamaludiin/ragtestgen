"""Retrieval stage: chunk, embed and index program sources in ChromaDB.

Chunking and retrieval depth follow the original tool (500-character chunks at
a stride of 400, ten nearest neighbours); the embedding model is
all-MiniLM-L6-v2, served through ChromaDB's bundled ONNX runtime so that no
PyTorch installation is required.
"""
import threading
import uuid

import chromadb
from chromadb.utils import embedding_functions

CHUNK, STRIDE, N_RESULTS = 500, 400, 10

_ef = None
_client = None
# Chroma keeps one shared in-process system per settings object, so building
# clients/collections concurrently corrupts its sysdb. One client, created and
# mutated under a lock, with a collection name unique per index.
_lock = threading.Lock()


def embedder():
    global _ef
    if _ef is None:
        _ef = embedding_functions.ONNXMiniLM_L6_V2()
    return _ef


def client():
    global _client
    if _client is None:
        _client = chromadb.EphemeralClient()
    return _client


class CodeIndex:
    def __init__(self, name=None):
        name = name or f"ragtestgen-{uuid.uuid4().hex[:12]}"
        with _lock:
            self.client = client()
            self.col = self.client.create_collection(name, embedding_function=embedder())
        self.n_chunks = 0

    def add_file(self, path, text, language="java"):
        chunks = [text[i:i + CHUNK] for i in range(0, max(len(text), 1), STRIDE)]
        chunks = [c for c in chunks if c.strip()]
        if not chunks:
            return
        with _lock:
            self.col.add(documents=chunks,
                         metadatas=[{"language": language, "file_name": str(path)} for _ in chunks],
                         ids=[f"{uuid.uuid4().hex}" for _ in chunks])
        self.n_chunks += len(chunks)

    def retrieve(self, query, n=N_RESULTS):
        if self.n_chunks == 0:
            return "", 0
        n = min(n, self.n_chunks)
        with _lock:
            res = self.col.query(query_texts=[query], n_results=n)
        docs = res.get("documents", [[]])[0]
        return "\n".join(docs), len(docs)
