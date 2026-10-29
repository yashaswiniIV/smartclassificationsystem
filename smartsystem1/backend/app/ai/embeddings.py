"""Local multilingual embeddings via fastembed (ONNX runtime — no torch).

Model: paraphrase-multilingual-MiniLM-L12-v2 (384-d, 50+ languages, paraphrase-
tuned — ideal for "are these two complaints the same problem?"). It's symmetric,
so queries and passages are embedded the same way (no e5-style role prefixes).

This is a local model, not an external API — it runs even when MOCK_AI is set.
First use downloads the model (~120 MB) and caches it; offline thereafter.
"""

import asyncio
import threading

from app.core.config import get_settings

EMBED_DIM = 384

_settings = get_settings()
_model = None
_lock = threading.Lock()


def _get_model():
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                from fastembed import TextEmbedding

                _model = TextEmbedding(model_name=_settings.embedding_model)
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    return [vec.tolist() for vec in _get_model().embed(texts)]


# Kept as named aliases for call-site clarity; the model is symmetric so both
# just embed the raw text.
embed_queries = embed_texts
embed_passages = embed_texts


async def aembed_query(text: str) -> list[float]:
    """Async wrapper — runs the (sync, ~30 ms CPU) ONNX inference off the event loop."""
    vecs = await asyncio.to_thread(embed_texts, [text])
    return vecs[0]


def to_pgvector(vec: list[float]) -> str:
    """pgvector text literal for binding into raw SQL: '[0.1,0.2,...]'."""
    return "[" + ",".join(f"{x:.7f}" for x in vec) + "]"
