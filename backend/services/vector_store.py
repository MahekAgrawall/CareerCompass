"""
Semantic role index, backed by Qdrant.

The vector index is a **recall** layer and nothing more: it answers "which roles
are semantically near this candidate", and the explainable scorer in
`career_service` still ranks and explains whatever comes back. That keeps the
interest/skill breakdown a candidate reads exactly as reproducible as before.

Storage defaults to qdrant-client's *embedded local mode* (a directory under
`backend/data/qdrant`), so the app needs no server or Docker. Set `QDRANT_URL`
(plus optional `QDRANT_API_KEY`) to point at a real Qdrant instead.

Ingestion is explicit — `python -m scripts.ingest_roles` — never on startup, so
boot time does not depend on embeddings or on the network. When the index is
missing, empty or unreachable, `semantic_search` returns nothing and the matcher
silently stays keyword-only.

Vectors are compared only within a collection named after the embedding
signature (provider + dimension), so two different embedding providers never
contaminate one another.
"""

import hashlib
import os
from typing import Any, Dict, List, Optional, Tuple

from app_logging import get_logger
from database.db import DATA_DIR
from services import embeddings

log = get_logger("careercompass.rag")

DEFAULT_QDRANT_PATH = os.path.join(DATA_DIR, "qdrant")
COLLECTION_PREFIX = "careercompass_roles"

# Cache key -> QdrantClient. Embedded local mode locks its directory, so holding
# one client per location matters.
_CLIENTS: Dict[str, Any] = {}


# ── Location & client ─────────────────────────────────────────────────────────
def qdrant_url() -> str:
    """Configured remote Qdrant URL, or '' for embedded local mode."""
    return os.environ.get("QDRANT_URL", "").strip()


def index_path() -> str:
    """Filesystem location of the embedded index (overridable for tests)."""
    return os.environ.get("QDRANT_PATH", "").strip() or DEFAULT_QDRANT_PATH


def location() -> str:
    return qdrant_url() or index_path()


def _client():
    """Lazily opens (and caches) the Qdrant client for the configured location."""
    from qdrant_client import QdrantClient

    key = location()
    client = _CLIENTS.get(key)
    if client is not None:
        return client
    url = qdrant_url()
    if url:
        client = QdrantClient(
            url=url,
            api_key=os.environ.get("QDRANT_API_KEY") or None,
            timeout=10,
        )
    else:
        client = QdrantClient(path=key)
    _CLIENTS[key] = client
    return client


def reset_clients() -> None:
    """Closes cached clients. Used by tests and by the ingest migration."""
    for client in _CLIENTS.values():
        try:
            client.close()
        except Exception:  # pragma: no cover - best effort cleanup
            pass
    _CLIENTS.clear()


def is_available() -> bool:
    """True when an index could exist at the configured location.

    Embedded mode deliberately checks the directory *before* opening a client,
    so a plain API process never creates (or locks) an empty index on boot.
    """
    if qdrant_url():
        return True
    path = index_path()
    try:
        return os.path.isdir(path) and bool(os.listdir(path))
    except OSError:
        return False


def collection_name() -> str:
    """One collection per embedding space (provider + model + width)."""
    return f"{COLLECTION_PREFIX}_{embeddings.signature()}"


# ── Documents ─────────────────────────────────────────────────────────────────
def role_document(role: Dict[str, Any]) -> str:
    """The text that stands in for a role inside the vector index.

    Kept deliberately wordy: it is what makes "I like maths and cloud" land on
    analytics and infrastructure roles rather than on exact keyword matches.
    """
    skills = role.get("skills") or {}
    ordered_skills = (
        list(skills.get("must_have") or [])
        + list(skills.get("good_to_have") or [])
        + list(skills.get("can_have") or [])
    )
    parts = [
        str(role.get("title") or ""),
        str(role.get("category") or ""),
        str(role.get("niche_category") or ""),
        str(role.get("description") or ""),
        "Responsibilities: " + "; ".join(role.get("responsibilities") or []),
        "Skills: " + ", ".join(ordered_skills),
        "Related interests: " + ", ".join(role.get("matching_interests") or []),
        "Related skills: " + ", ".join(role.get("matching_skills") or []),
        "Career growth: " + ", ".join(role.get("growth_path") or []),
    ]
    return "\n".join(part for part in parts if part.strip())


def profile_query(profile: Dict[str, Any]) -> str:
    """The text that stands in for a candidate when searching the index."""
    parts: List[str] = []
    interests = profile.get("interests") or []
    skills = profile.get("current_skills") or []
    if interests:
        parts.append("Interests: " + ", ".join(str(i) for i in interests))
    if skills:
        parts.append("Skills: " + ", ".join(str(s) for s in skills))
    for key, label in (
        ("career_goal", "Goal"),
        ("experience", "Experience"),
        ("work_mode", "Work mode"),
        ("location", "Location"),
    ):
        value = profile.get(key) or ""
        if isinstance(value, str) and value.strip():
            parts.append(f"{label}: {value.strip()}")
    return "\n".join(parts)


def _point_id(role_id: str) -> int:
    """Deterministic uint64 id so re-ingesting updates instead of duplicating."""
    return int.from_bytes(
        hashlib.blake2b(role_id.encode("utf-8"), digest_size=8).digest(), "big"
    )


# ── Collection management ─────────────────────────────────────────────────────
def _ensure_collection(client, name: str) -> None:
    from qdrant_client import models

    if client.collection_exists(name):
        info = client.get_collection(name)
        size = info.config.params.vectors.size
        if size != embeddings.EMBEDDING_DIM:
            raise ValueError(
                f"Collection {name} holds {size}-dim vectors but "
                f"{embeddings.signature()} produces {embeddings.EMBEDDING_DIM}; "
                "run the ingest migration with --rebuild."
            )
        return
    client.create_collection(
        collection_name=name,
        vectors_config=models.VectorParams(
            size=embeddings.EMBEDDING_DIM, distance=models.Distance.COSINE
        ),
    )
    log.info("Created Qdrant collection %s (%s)", name, embeddings.signature())


def upsert_roles(roles: List[Dict[str, Any]], batch_size: int = 32) -> int:
    """Embeds and stores every role. Returns the number of points written."""
    from qdrant_client import models

    if not roles:
        return 0
    client = _client()
    name = collection_name()
    _ensure_collection(client, name)
    written = 0
    for start in range(0, len(roles), batch_size):
        batch = roles[start:start + batch_size]
        vectors = embeddings.embed_documents([role_document(role) for role in batch])
        points = [
            models.PointStruct(
                id=_point_id(str(role["id"])),
                vector=vector,
                payload={
                    "role_id": str(role["id"]),
                    "title": str(role.get("title") or ""),
                    "category": str(role.get("category") or ""),
                },
            )
            for role, vector in zip(batch, vectors)
        ]
        client.upsert(collection_name=name, points=points, wait=True)
        written += len(points)
    return written


def drop_collection(name: str) -> bool:
    """Deletes one named collection on a Qdrant server. No-op in embedded mode.

    Embedded mode has no per-collection cleanup that survives a reopen on Windows
    (see `rebuild`), so callers there clear the whole directory instead.
    """
    if not qdrant_url() or not name:
        return False
    try:
        client = _client()
        if client.collection_exists(name):
            client.delete_collection(name)
            return True
    except Exception as exc:  # noqa: BLE001 - reported by the caller's fallback
        log.warning("Could not drop collection %s (%s)", name, exc)
    return False


def rebuild(roles: List[Dict[str, Any]]) -> int:
    """Drops this embedding space's collection and re-ingests everything.

    In embedded local mode this clears the whole local index directory (every
    embedding space), because on Windows a collection's storage file can survive
    `delete_collection` and get re-read on the next open. Requires the API server
    to be stopped, exactly like the first ingest.
    """
    if qdrant_url():
        client = _client()
        if client.collection_exists(collection_name()):
            client.delete_collection(collection_name())
    else:
        import shutil

        path = index_path()
        reset_clients()
        shutil.rmtree(path, ignore_errors=True)
        if os.path.isdir(path):
            raise RuntimeError(
                f"could not clear the embedded index at {path} — another process "
                "(the API server?) is probably holding it open."
            )
    return upsert_roles(roles)


# ── Retrieval ─────────────────────────────────────────────────────────────────
def semantic_search(text: str, limit: int = 25) -> List[Tuple[str, float]]:
    """Returns `(role_id, similarity)` pairs, best first.

    Never raises: a missing index, a retired embedding model or a network
    outage all degrade to "no semantic recall", leaving keyword matching intact.
    """
    if not (text or "").strip() or not is_available():
        return []
    try:
        client = _client()
        name = collection_name()
        if not client.collection_exists(name):
            return []
        vector = embeddings.embed_query(text)
        response = client.query_points(
            collection_name=name,
            query=vector,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        hits = getattr(response, "points", response) or []
        results: List[Tuple[str, float]] = []
        for hit in hits:
            payload = getattr(hit, "payload", None) or {}
            role_id = payload.get("role_id")
            if role_id:
                results.append((str(role_id), float(getattr(hit, "score", 0.0))))
        return results
    except Exception as exc:
        log.warning("Semantic recall unavailable (%s); using keyword matching only", exc)
        return []


def index_status() -> Dict[str, Any]:
    """Diagnostics for the `/health` endpoint and the migration summary."""
    status: Dict[str, Any] = {
        "provider": embeddings.active_provider(),
        "model": embeddings.model_name(),
        "collection": collection_name(),
        "location": location(),
        "available": False,
        "points": 0,
    }
    if not is_available():
        return status
    try:
        client = _client()
        name = collection_name()
        collections = [collection.name for collection in client.get_collections().collections]
        if name in collections:
            counted = client.count(name)
            status["available"] = True
            status["points"] = int(getattr(counted, "count", 0))
        else:
            # This embedding space has never been ingested. Naming the spaces that
            # *do* exist turns "semantic search looks off" into something the
            # reader can act on: re-run the migration, or pin EMBEDDING_PROVIDER.
            status["other_collections"] = [collection for collection in collections if collection != name]
    except Exception as exc:
        status["error"] = str(exc)
    return status


def search_titles(query: str, limit: int = 5) -> List[Tuple[str, str, float]]:
    """Convenience wrapper for the migration's smoke test: title, category, score."""
    return [
        (title, category, score)
        for (title, category, score) in _titled_hits(query, limit)
    ]


def _titled_hits(query: str, limit: int) -> List[Tuple[str, str, float]]:
    if not (query or "").strip() or not is_available():
        return []
    try:
        client = _client()
        name = collection_name()
        if not client.collection_exists(name):
            return []
        response = client.query_points(
            collection_name=name,
            query=embeddings.embed_query(query),
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        hits = getattr(response, "points", response) or []
        return [
            (
                str((getattr(hit, "payload", None) or {}).get("title", "")),
                str((getattr(hit, "payload", None) or {}).get("category", "")),
                float(getattr(hit, "score", 0.0)),
            )
            for hit in hits
        ]
    except Exception as exc:
        log.warning("Semantic search failed (%s)", exc)
        return []
