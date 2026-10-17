"""
Text embeddings for the semantic role index.

Two providers, one interface:

* **Gemini** (`gemini-embedding-001`) whenever a `GEMINI_API_KEY` is configured.
  Real semantic quality, costs an API call per embed.
* **Local** — a deterministic hashing embedder (signed hashing trick over word
  tokens and character 4-grams). It is weaker, but it needs no API key, no
  network and no model download, so the test suite, CI and a laptop without a
  key still get a working index.

Both produce `EMBEDDING_DIM`-length, L2-normalised vectors, so the dimension of
the Qdrant collection never depends on which provider is active. The provider —
and, for Gemini, the model — still forms part of the collection name (see
`vector_store.collection_name`) so vectors from two different spaces are never
compared with each other.

`active_provider()` resolves, in order:

1. `EMBEDDING_PROVIDER=gemini|local` when set explicitly;
2. the provider that built the index on disk (recorded by the ingest migration,
   see `recorded_provider`) so queries always embed the way the index was built;
3. `gemini` when `GEMINI_API_KEY` is configured, otherwise `local`.
"""

import hashlib
import math
import os
import re
import unicodedata
from typing import Dict, List

from app_logging import get_logger

try:  # pragma: no cover - import-time convenience, exercised via ai_service too
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover
    pass

log = get_logger("careercompass.embeddings")

# Both providers are held to this width. `gemini-embedding-001` is Matryoshka-
# trained, so asking for (or truncating to) 768 dimensions is a supported
# operation; the local hashing embedder is sized to match.
EMBEDDING_DIM = 768

# The current Gemini embedding model. Override with GEMINI_EMBEDDING_MODEL; the
# model is part of the collection name, so switching it starts a new space rather
# than overwriting vectors that are not comparable.
GEMINI_DEFAULT_MODEL = "models/gemini-embedding-001"

# Written into the embedded index directory by the migration.
PROVIDER_MANIFEST = "PROVIDER"

_last_good_attempt = None

_WORD_RE = re.compile(r"[a-z0-9+#.]+")
_SLUG_RE = re.compile(r"[^a-z0-9]+")


class EmbeddingError(RuntimeError):
    """Raised when the configured embedding provider cannot produce vectors."""


# ── Provider selection ────────────────────────────────────────────────────────
def gemini_model() -> str:
    """The Gemini embedding model to use, read at call time."""
    return os.environ.get("GEMINI_EMBEDDING_MODEL", "").strip() or GEMINI_DEFAULT_MODEL


def model_tag(model: str) -> str:
    """Slug for a model id: 'models/gemini-embedding-001' -> 'gemini-embedding-001'."""
    return _SLUG_RE.sub("-", model.rsplit("/", 1)[-1].lower()).strip("-")


def index_dir() -> str:
    """Filesystem location of the embedded index.

    Mirrors `vector_store.index_path`, which cannot be imported here without a
    cycle (`vector_store` imports this module).
    """
    override = os.environ.get("QDRANT_PATH", "").strip()
    if override:
        return override
    from database.db import DATA_DIR

    return os.path.join(DATA_DIR, "qdrant")


def recorded_provider() -> str:
    """The provider that built the index on disk, or '' when it did not say.

    Only meaningful for the embedded index: a Qdrant server holds whichever
    collections it holds, and the answer is really "whatever you ingested".
    """
    if os.environ.get("QDRANT_URL", "").strip():
        return ""
    try:
        with open(os.path.join(index_dir(), PROVIDER_MANIFEST), encoding="utf-8") as handle:
            value = handle.read().strip().lower()
    except OSError:
        return ""
    return value if value in ("gemini", "local") else ""


def record_provider(provider: str) -> None:
    """Remembers which provider built the index so queries embed the same way."""
    if os.environ.get("QDRANT_URL", "").strip():
        return
    directory = index_dir()
    try:
        os.makedirs(directory, exist_ok=True)
        with open(os.path.join(directory, PROVIDER_MANIFEST), "w", encoding="utf-8") as handle:
            handle.write(f"{provider}\n")
    except OSError as error:  # pragma: no cover - best effort
        log.warning("Could not record the index provider in %s (%s)", directory, error)


def active_provider() -> str:
    """Returns the provider that will be used right now: 'gemini' or 'local'."""
    forced = os.environ.get("EMBEDDING_PROVIDER", "").strip().lower()
    if forced in ("gemini", "local"):
        return forced
    has_key = bool(os.environ.get("GEMINI_API_KEY", "").strip())
    recorded = recorded_provider()
    if recorded == "local":
        return "local"
    if recorded == "gemini" and has_key:
        return "gemini"
    return "gemini" if has_key else "local"


def signature() -> str:
    """A stable name for the vector space these embeddings live in.

    Gemini models are named, not just "gemini": each model is its own space even
    at the same width, so a model change must start a fresh collection instead of
    comparing incomparable vectors.
    """
    if active_provider() == "gemini":
        return f"gemini-{model_tag(gemini_model())}-{EMBEDDING_DIM}"
    return f"local-{EMBEDDING_DIM}"


def model_name() -> str:
    """Human-readable description of the active provider, for logs and status."""
    if active_provider() == "gemini":
        model = gemini_model()
        truncated = _last_good_attempt == (model, False)
        return f"{model} (truncated to {EMBEDDING_DIM}d)" if truncated else f"{model} ({EMBEDDING_DIM}d)"
    return f"local-hashing-{EMBEDDING_DIM}d"


# ── Local deterministic embedder ──────────────────────────────────────────────
def _local_tokens(text: str) -> Dict[str, float]:
    """Word unigrams plus character 4-grams, counted for the hashing trick."""
    cleaned = unicodedata.normalize("NFKD", text or "").lower()
    counts: Dict[str, float] = {}
    for word in _WORD_RE.findall(cleaned):
        if len(word) < 2:
            continue
        counts["w:" + word] = counts.get("w:" + word, 0.0) + 1.0
        padded = f"^{word}$"
        for index in range(len(padded) - 3):
            gram = "c:" + padded[index:index + 4]
            counts[gram] = counts.get(gram, 0.0) + 0.35
    return counts


def _normalise(vector: List[float]) -> List[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        return vector
    return [value / norm for value in vector]


def _local_vector(text: str) -> List[float]:
    """Deterministic, dependency-free embedding.

    Uses a *signed* hash so unrelated texts land near-orthogonal instead of
    always accumulating positive mass in the same buckets.
    """
    vector = [0.0] * EMBEDDING_DIM
    tokens = _local_tokens(text)
    if not tokens:
        return vector
    for token, count in tokens.items():
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        index = int.from_bytes(digest, "big") % EMBEDDING_DIM
        sign = 1.0 if digest[0] & 1 else -1.0
        vector[index] += sign * math.log1p(count)
    return _normalise(vector)


# ── Gemini embedder ───────────────────────────────────────────────────────────
def _gemini_vectors(texts: List[str], task_type: str) -> List[List[float]]:
    """Embeds a batch with Gemini.

    Two request shapes for the *same* model: the natural-width call, then the
    full-width call truncated to `EMBEDDING_DIM`. Both stay inside one vector
    space, so a fallback can never mix incomparable vectors. Which shape answered
    is remembered and tried first from then on.
    """
    global _last_good_attempt
    import google.generativeai as genai

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise EmbeddingError("GEMINI_API_KEY is not set.")
    genai.configure(api_key=api_key, transport="rest")

    model = gemini_model()

    def _request(with_dimension: bool) -> List[List[float]]:
        kwargs = {"model": model, "content": texts, "task_type": task_type}
        if with_dimension:
            kwargs["output_dimensionality"] = EMBEDDING_DIM
        response = genai.embed_content(**kwargs)
        embedded = response["embedding"]
        if embedded and isinstance(embedded[0], (int, float)):
            embedded = [embedded]  # single-input response arrives flat
        return [
            _normalise([float(value) for value in vector][:EMBEDDING_DIM])
            for vector in embedded
        ]

    shapes = [True, False]
    if _last_good_attempt == (model, False):
        shapes.reverse()

    last_error = None
    for with_dimension in shapes:
        try:
            vectors = _request(with_dimension=with_dimension)
        except Exception as error:  # retired model, quota, transport, ...
            last_error = error
            log.warning(
                "Gemini embedding attempt failed (%s %s): %s",
                model, f"at {EMBEDDING_DIM} dims" if with_dimension else "full width", error,
            )
            continue
        if _last_good_attempt != (model, with_dimension):
            log.info("Gemini embeddings served by %s%s", model,
                     f" at {EMBEDDING_DIM} dims" if with_dimension else " (truncated)")
            _last_good_attempt = (model, with_dimension)
        return vectors
    raise EmbeddingError(f"Gemini embeddings unavailable: {last_error}")


# ── Public API ────────────────────────────────────────────────────────────────
def embed_documents(texts: List[str]) -> List[List[float]]:
    """Embeds role documents for indexing. Raises rather than mixing spaces."""
    clean = [text or "" for text in texts]
    if not clean:
        return []
    if active_provider() == "gemini":
        return _gemini_vectors(clean, task_type="RETRIEVAL_DOCUMENT")
    return [_local_vector(text) for text in clean]


def embed_query(text: str) -> List[float]:
    """Embeds a single retrieval query (a candidate profile hand-off)."""
    if active_provider() == "gemini":
        return _gemini_vectors([text or ""], task_type="RETRIEVAL_QUERY")[0]
    return _local_vector(text or "")


def cosine(a: List[float], b: List[float]) -> float:
    """Cosine similarity for two already-normalised vectors (test helper)."""
    return sum(x * y for x, y in zip(a, b))
