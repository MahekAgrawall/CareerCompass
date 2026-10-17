"""
Migration: load the role catalog into the Qdrant semantic index.

Run this whenever `backend/data/roles.json` changes:

    cd backend
    .\\.venv\\Scripts\\python.exe -m scripts.ingest_roles

Why a script and not startup work? Booting the API should never depend on
embeddings, an API key or the network. If the index is stale or missing the
matcher simply stays keyword-only (see `services/vector_store.semantic_search`),
so this migration is safe to skip, re-run or postpone.

Options:
    --rebuild        drop the collection first (use after switching embedding
                     provider, which moves the data to a new collection)
    --query "text"   run a semantic smoke test afterwards and print the hits

Which embeddings are used follows `EMBEDDING_PROVIDER`; the default `auto` uses
Gemini when `GEMINI_API_KEY` is set. Vectors from two providers — or from two
Gemini models — are never compared, so each space gets its own collection. The
provider that builds the index is recorded next to it and the API follows that
record, so adding or removing a key later still reads the right collection. If
Gemini is configured but unusable (quota, retired model, offline) this script
builds the offline local index instead and says so, rather than leaving you with
no index and no explanation.

Note on embedded mode: qdrant-client's local storage is locked by whichever
process has it open. If the API server is running, stop it before ingesting, or
point QDRANT_URL at a real Qdrant (which needs no lock).
"""

import argparse
import os
import sys

from app_logging import get_logger
from database.db import init_db
from services import career_service, embeddings, vector_store

log = get_logger("careercompass.rag.migration")


def _explain(error: Exception) -> str:
    """Turns a failure into something a human can act on."""
    message = str(error)
    if "lock" in message.lower() or "portalocker" in message.lower():
        return (
            "Could not open the embedded index at "
            f"{vector_store.index_path()} ({message}).\n"
            "Another process — the API server? — probably has it open. Stop the "
            "server and re-run, or set QDRANT_URL to use a Qdrant server instead."
        )
    return (
        f"Could not build the semantic index: {message}\n"
        "Nothing was written. The API keeps working with keyword matching only."
    )


def _write(roles, rebuild: bool) -> int:
    return vector_store.rebuild(roles) if rebuild else vector_store.upsert_roles(roles)


def _fall_back_to_local(roles, error: Exception) -> int:
    """Builds the offline index when Gemini is configured but unusable.

    The fallback is only useful if the API ends up *reading* the index we build,
    which is why the choice is recorded next to the index (see
    `embeddings.record_provider`). Anything the failed provider already wrote is
    discarded instead of being left to mix two vector spaces in one collection.
    """
    abandoned = vector_store.collection_name()
    log.warning("Gemini embeddings unavailable (%s); building the offline index", error)
    print(f"! Gemini embeddings unavailable: {error}")
    print("  Falling back to the deterministic local embedder.")
    os.environ["EMBEDDING_PROVIDER"] = "local"
    vector_store.reset_clients()
    if vector_store.qdrant_url():
        vector_store.drop_collection(abandoned)
    return vector_store.rebuild(roles)  # rebuild clears anything half-written


def ingest(rebuild: bool = False, query: str = "") -> dict:
    """Indexes every catalogued role and reports what happened."""
    init_db()
    roles = career_service.get_all_roles()
    if not roles:
        raise SystemExit("No roles found in the database — is data/roles.json present?")

    provider = embeddings.active_provider()
    previous = vector_store.index_status()
    try:
        written = _write(roles, rebuild)
    except embeddings.EmbeddingError as error:
        if provider != "gemini":
            raise SystemExit(_explain(error)) from error
        try:
            written = _fall_back_to_local(roles, error)
        except Exception as fallback_error:  # noqa: BLE001 - reported, not swallowed
            raise SystemExit(_explain(fallback_error)) from fallback_error
    except Exception as error:  # noqa: BLE001 - reported, not swallowed
        raise SystemExit(_explain(error)) from error

    embeddings.record_provider(embeddings.active_provider())
    status = vector_store.index_status()
    log.info(
        "Indexed %s roles into %s (%s, %s points)",
        written, status["collection"], status["model"], status["points"],
    )
    return {"written": written, "previous": previous, "status": status}


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--rebuild", action="store_true",
                        help="drop the collection before ingesting")
    parser.add_argument("--query", default="",
                        help="run a semantic smoke test after ingesting")
    args = parser.parse_args(argv)

    try:
        result = ingest(rebuild=args.rebuild, query=args.query)
        status = result["status"]
        print(f"provider   : {embeddings.active_provider()} ({status['model']})")
        print(f"collection : {status['collection']}")
        print(f"location   : {status['location']}")
        print(f"points     : {status['points']} (wrote {result['written']})")

        if args.query:
            print(f"\nTop matches for {args.query!r}:")
            hits = vector_store.search_titles(args.query, limit=5)
            if not hits:
                print("  (no hits — is the index available?)")
            for title, category, score in hits:
                print(f"  {score:.3f}  {title}  [{category}]")
    finally:
        # Closing the embedded client on the way out keeps the process exit quiet
        # and releases the directory for the next run or for the API.
        vector_store.reset_clients()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
