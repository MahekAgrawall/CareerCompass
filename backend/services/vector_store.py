"""
Semantic role index, backed by Qdrant.

The vector index is a **recall** layer and nothing more: it answers "which roles
are semantically near this candidate", and the explainable scorer in
`career_service` still ranks and explains whatever comes back. That keeps the
interest/skill breakdown a candidate reads exactly as reproducible as before.

Storage defaults to qdrant-client's *embedded local mode* (a directory under
`backend/data/qdrant`), so the app needs no server or Docker. Set `QDRANT_URL`
(plus optional `QDRANT_API_KEY`) to point at a real Qdrant instead.

Ingestion is explicit — `python -m scripts.ingest_roles` for the curated catalog,
`python -m scripts.ingest_jobs` for the live job feed — never on startup, so boot
time does not depend on embeddings or on the network. When the index is missing,
empty or unreachable, `semantic_search` returns nothing and the matcher silently
stays keyword-only.

Two kinds of collection live here:

* `careercompass_roles_<signature>` — the curated role catalog, named after its
  embedding space (provider + model + width) so two spaces never contaminate one
  another;
* `job_role` — live job postings (see `services.job_feed`). That name is a plain,
  human-chosen one, so the space it holds is recorded in a sidecar file
  (`<index>/job_role.space`) and checked before ingestion instead.
"""

import gc
import hashlib
import os
import shutil
from typing import Any, Dict, List, Optional, Tuple

from app_logging import get_logger
from database.db import DATA_DIR
from services import embeddings

log = get_logger("careercompass.rag")

DEFAULT_QDRANT_PATH = os.path.join(DATA_DIR, "qdrant")
COLLECTION_PREFIX = "careercompass_roles"
# Live job postings get their own deliberately plain collection name, so the
# data is easy to find from any Qdrant client (`scripts.ingest_jobs` fills it).
JOBS_COLLECTION = "job_role"

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


def _purge_embedded(name: str) -> bool:
    """Removes one embedded collection completely: metadata *and* files.

    `delete_collection` alone is not enough here. In embedded mode a collection
    is just a directory: deleting it drops the name from `meta.json` but leaves
    `collection/<name>/storage.sqlite` behind, and creating that name again
    re-attaches the old file — so "deleted" points reappear. Clearing the
    directory is the only thing that actually clears the data, and it has to
    happen with every client closed and after a `gc.collect()`, because the
    delete itself leaves a SQLite handle open.

    Returns whether the collection existed. Raises when the files could not be
    removed: a half-purged collection is worse than a failed rebuild.
    """
    client = _client()
    existed = client.collection_exists(name)
    if existed:
        client.delete_collection(name)

    target = os.path.join(index_path(), "collection", name)
    reset_clients()
    gc.collect()
    shutil.rmtree(target, ignore_errors=True)
    if os.path.isdir(target):
        raise RuntimeError(
            f"could not clear the embedded collection {name!r} at {target} — another "
            "process (the API server?) is probably holding it open. Stop it and re-run."
        )
    return existed


def drop_collection(name: str) -> bool:
    """Deletes a collection by name, whichever storage mode is configured.

    Returns whether it existed. In embedded mode this really clears the stored
    vectors (see `_purge_embedded`); on a Qdrant server it is a plain server-side
    delete. Raises if an embedded collection could not be cleared, because
    leaving stale vectors behind under the same name would silently poison the
    next ingest.
    """
    if not name:
        return False
    if not qdrant_url():
        return _purge_embedded(name)
    try:
        client = _client()
        if client.collection_exists(name):
            client.delete_collection(name)
            return True
    except Exception as exc:  # noqa: BLE001 - reported by the caller's fallback
        log.warning("Could not drop collection %s (%s)", name, exc)
    return False


def rebuild(roles: List[Dict[str, Any]]) -> int:
    """Drops this embedding space's collection and re-ingests every role.

    Scoped to its own collection on purpose: other collections in the same store
    (`job_role`, or a previous embedding space) are left alone, so rebuilding the
    catalog cannot destroy them. The API server must still be stopped — embedded
    mode holds the index directory for the whole process.
    """
    drop_collection(collection_name())
    return upsert_roles(roles)


# ── Named collections (live job postings) ─────────────────────────────────────
def _space_manifest(collection: str) -> str:
    return os.path.join(index_path(), f"{collection}.space")


def recorded_space(collection: str) -> str:
    """The embedding space a named collection was built in, or '' if unknown.

    Always '' on a Qdrant server: there the space is whatever was ingested, and
    the sidecar file would live on the wrong machine.
    """
    if qdrant_url():
        return ""
    try:
        with open(_space_manifest(collection), encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def record_space(collection: str, space: str) -> None:
    """Remembers which embedding space a fixed-name collection holds.

    `job_role` is a human-chosen name, so unlike the role collections it cannot
    carry its provider and model in the name. This sidecar is what keeps two
    spaces from ever being compared inside one collection.
    """
    if qdrant_url():
        return
    try:
        os.makedirs(index_path(), exist_ok=True)
        with open(_space_manifest(collection), "w", encoding="utf-8") as handle:
            handle.write(f"{space}\n")
    except OSError as exc:  # pragma: no cover - best effort
        log.warning("Could not record the embedding space for %s (%s)", collection, exc)


def collection_exists(name: str) -> bool:
    """Whether a collection is present in the store. Never raises."""
    try:
        return bool(_client().collection_exists(name))
    except Exception as exc:  # noqa: BLE001 - diagnostics must never raise
        log.warning("Could not look up collection %s (%s)", name, exc)
        return False


def count_points(name: str) -> int:
    """Number of points in a collection, 0 when it does not exist."""
    try:
        client = _client()
        if not client.collection_exists(name):
            return 0
        return int(getattr(client.count(name), "count", 0))
    except Exception as exc:  # noqa: BLE001 - diagnostics must never raise
        log.warning("Could not count %s (%s)", name, exc)
        return 0


def upsert_records(
    name: str,
    rows: List[Tuple[str, str, Dict[str, Any]]],
    batch_size: int = 64,
) -> int:
    """Embeds and stores `(record_id, document, payload)` rows in a collection.

    Returns the number of points written. Re-ingesting the same ids updates them
    instead of duplicating, exactly like `upsert_roles`.
    """
    from qdrant_client import models

    if not rows:
        return 0
    client = _client()
    _ensure_collection(client, name)
    written = 0
    for start in range(0, len(rows), batch_size):
        batch = rows[start:start + batch_size]
        vectors = embeddings.embed_documents([document for _, document, _ in batch])
        points = [
            models.PointStruct(
                id=_point_id(record_id),
                vector=vector,
                payload=payload,
            )
            for (record_id, _, payload), vector in zip(batch, vectors)
        ]
        client.upsert(collection_name=name, points=points, wait=True)
        written += len(points)
    return written


def search_records(name: str, text: str, limit: int = 10) -> List[Tuple[float, Dict[str, Any]]]:
    """`[(score, payload), ...]` from a named collection, best first.

    Never raises: an absent collection or an unavailable embedder yields [].
    """
    if not (text or "").strip() or not is_available():
        return []
    try:
        client = _client()
        if not client.collection_exists(name):
            return []
        response = client.query_points(
            collection_name=name,
            query=embeddings.embed_query(text),
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        hits = getattr(response, "points", response) or []
        return [
            (
                float(getattr(hit, "score", 0.0)),
                dict(getattr(hit, "payload", None) or {}),
            )
            for hit in hits
        ]
    except Exception as exc:
        log.warning("Search on %s failed (%s)", name, exc)
        return []


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
