"""
Migration: collect live job postings and load them into the `job_role` collection.

    cd backend
    .\\.venv\\Scripts\\python.exe -m scripts.ingest_jobs --limit 1000

Why a script and not startup work? The API must never depend on a third-party job
board being up, on an embedding key, or on a network call at boot. This is data
plumbing: run it when you want fresh postings, skip it otherwise. The Jobs page
reads `job_role`, so a skipped run shows a stale feed rather than a broken app —
which is why every ingest records *when* it happened and the API reports it.

What it does:

1. collects postings from the public job-board APIs (see `services.job_feed`);
2. writes them to `data/job_postings.json`, so re-ingesting needs no network, and
   stamps the file with the harvest time;
3. embeds each posting and upserts it into the `job_role` collection;
4. records the harvest and ingest times in `<index>/job_role.meta.json`, which is
   what `GET /jobs/search`'s `freshness` block reports;
5. creates the payload indexes the Jobs page's filters read (see
   `services.job_service.FILTER_INDEXES`). Skipping this step breaks nothing in
   the embedded store, which ignores payload indexes — but a `QDRANT_URL`
   deployment needs the text indexes before Qdrant will run a full-text filter.

Options:
    --limit N          how many postings to collect (default 1000)
    --source NAME      restrict to one board (himalayas, arbeitnow); repeatable
    --rebuild          drop the `job_role` collection first
    --query "text"     run a semantic smoke test afterwards and print the hits
    --from-file PATH   ingest a previously collected JSON file instead of fetching
    --save PATH        where to write the collected postings
                       (default data/job_postings.json; '' skips writing)
    --if-stale DAYS    do nothing when the current harvest is younger than DAYS

`--if-stale` is what makes a frequent schedule cheap: point a scheduler at it
hourly or daily and the run is a no-op until the feed is actually getting old.
`--rebuild` overrides it, and the harvest time of a `--from-file` artifact is the
artifact's own, so re-ingesting old data never ages it up to today.

Embeddings follow the same `EMBEDDING_PROVIDER` rules as the role index. Because
`job_role` is a fixed, human-chosen name, the space it holds is recorded in
`<index>/job_role.space`; ingesting with a different provider or Gemini model
refuses rather than mixing incomparable vectors — pass `--rebuild` to switch.

Note on embedded mode: qdrant-client's local storage is locked by whichever
process has it open, so stop the API server before running this.
"""

import argparse
import os
import sys

from app_logging import get_logger
from database.db import DATA_DIR
from services import embeddings, job_feed, job_service, vector_store

log = get_logger("careercompass.jobs.migration")

DEFAULT_SAVE = os.path.join(DATA_DIR, "job_postings.json")


def _explain(error: Exception) -> str:
    """Turns a failure into something a human can act on."""
    message = str(error)
    if "lock" in message.lower() or "portalocker" in message.lower():
        return (
            f"Could not open the embedded index at {vector_store.index_path()} ({message}).\n"
            "Another process — the API server? — probably has it open. Stop the "
            "server and re-run, or set QDRANT_URL to use a Qdrant server instead."
        )
    return (
        f"Could not build the {vector_store.JOBS_COLLECTION} collection: {message}\n"
        "Nothing was written. The rest of the app is unaffected."
    )


def _collect(limit: int, sources, from_file: str, save_path: str) -> tuple:
    """Postings, from the network or from a previously saved artifact.

    Returns `(postings, harvested_at)`. The harvest time is when the data was
    pulled: now for a fresh collect, and the artifact's own stamp for
    `--from-file` — which is the point, because re-ingesting a week-old file must
    not present it as today's harvest. An artifact written before the stamp
    existed loads with `""`, which the API reports as "not recorded".
    """
    if from_file:
        artifact = job_feed.load_artifact(from_file)
        postings = artifact["postings"]
        harvested_at = artifact["harvested_at"]
        when = f", harvested {harvested_at}" if harvested_at else " (no harvest date in the file)"
        print(f"loaded     : {len(postings)} postings from {from_file}{when}")
        return postings, harvested_at

    print(f"collecting : up to {limit} postings from {', '.join(sources)}")
    postings = job_feed.collect(limit=limit, sources=sources)
    harvested_at = job_feed.harvest_stamp()
    if save_path:
        job_feed.save(postings, save_path, harvested_at=harvested_at)
        print(f"saved      : {len(postings)} postings to {save_path}")
    return postings, harvested_at


def _skip_reason(max_age_days: int) -> str:
    """Why a scheduled run has nothing to do, or '' when a refresh is due.

    Separate from `ingest` so the decision can be tested without a scheduler, and
    built only on the recorded sidecar — it never opens the collection.
    """
    state = job_service.freshness()
    age = state["age_days"]
    if age is None or age >= max_age_days:
        return ""
    return (
        f"the index already holds postings harvested {state['harvested_at']} "
        f"({age} day(s) ago), younger than --if-stale {max_age_days}"
    )


def ingest(
    limit: int = 1000,
    sources=None,
    rebuild: bool = False,
    query: str = "",
    from_file: str = "",
    save_path: str = DEFAULT_SAVE,
) -> dict:
    """Collects, embeds and stores live postings. Returns a summary."""
    sources = list(sources or job_feed.SOURCES)
    postings, harvested_at = _collect(limit, sources, from_file, save_path)

    rows = [
        (row["record_id"], row["document"], row["payload"])
        for row in job_feed.rows(postings)
    ]
    if not rows:
        raise SystemExit(
            "No usable postings were collected — the boards may be unreachable. "
            "Nothing was written."
        )

    collection = vector_store.JOBS_COLLECTION
    space = embeddings.signature()
    recorded = vector_store.recorded_space(collection)
    if recorded and recorded != space and not rebuild:
        # The collection name is fixed, so nothing else stops two embedding
        # spaces from being compared inside it. Refuse instead of corrupting it.
        raise SystemExit(
            f"Collection {collection} was built in embedding space {recorded!r} "
            f"but the active embeddings are {space!r}.\n"
            "Re-run with --rebuild to replace it with the current space."
        )

    previous_points = vector_store.count_points(collection)
    try:
        if rebuild:
            vector_store.drop_collection(collection)
        written = vector_store.upsert_records(collection, rows)
    except embeddings.EmbeddingError as error:
        raise SystemExit(_explain(error)) from error
    except Exception as error:  # noqa: BLE001 - reported, not swallowed
        raise SystemExit(_explain(error)) from error

    vector_store.record_space(collection, space)
    ingested_at = job_feed.harvest_stamp()
    vector_store.record_meta(
        collection,
        {"harvested_at": harvested_at, "ingested_at": ingested_at},
    )
    payload_indexes = vector_store.ensure_payload_indexes(collection, job_service.FILTER_INDEXES)
    status = {
        "collection": collection,
        "space": space,
        "provider": embeddings.active_provider(),
        "model": embeddings.model_name(),
        "location": vector_store.location(),
        "points": vector_store.count_points(collection),
        "previous_points": previous_points,
        "postings": len(postings),
        "harvested_at": harvested_at,
        "ingested_at": ingested_at,
        "payload_indexes": payload_indexes,
    }
    log.info(
        "Indexed %s postings into %s (%s, %s points)",
        written, collection, status["model"], status["points"],
    )
    return {"written": written, "status": status}


def _print_hits(query: str, limit: int = 5) -> None:
    print(f"\nTop matches for {query!r}:")
    hits = vector_store.search_records(vector_store.JOBS_COLLECTION, query, limit=limit)
    if not hits:
        print("  (no hits — is the collection available?)")
    for score, payload in hits:
        salary = payload.get("salary_text") or "salary n/a"
        print(f"  {score:.3f}  {payload.get('title', '?')}  @ {payload.get('company', '?')}")
        print(f"         {payload.get('location') or 'location n/a'} · {salary} · {payload.get('source', '?')}")


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--limit", type=int, default=1000,
                        help="how many postings to collect (default 1000)")
    parser.add_argument("--source", action="append", dest="sources", default=None,
                        choices=list(job_feed.SOURCES),
                        help="restrict to one board (repeatable)")
    parser.add_argument("--rebuild", action="store_true",
                        help="drop the collection before ingesting")
    parser.add_argument("--query", default="",
                        help="run a semantic smoke test after ingesting")
    parser.add_argument("--from-file", default="",
                        help="ingest a saved JSON file instead of fetching")
    parser.add_argument("--save", default=DEFAULT_SAVE,
                        help="where to write collected postings ('' to skip)")
    parser.add_argument("--if-stale", type=int, default=0, metavar="DAYS",
                        help="do nothing when the harvested data is younger than DAYS "
                             "(for a schedule; --rebuild overrides)")
    args = parser.parse_args(argv)

    try:
        if args.if_stale and not args.rebuild:
            reason = _skip_reason(args.if_stale)
            if reason:
                print(f"skipped    : {reason}")
                print("             nothing was fetched or written; drop --if-stale to force a run")
                return 0

        result = ingest(
            limit=args.limit,
            sources=args.sources,
            rebuild=args.rebuild,
            query=args.query,
            from_file=args.from_file,
            save_path=args.save,
        )
        status = result["status"]
        print(f"provider   : {status['provider']} ({status['model']})")
        print(f"collection : {status['collection']}")
        print(f"space      : {status['space']}")
        print(f"location   : {status['location']}")
        print(f"points     : {status['points']} (wrote {result['written']})")
        print(f"harvested  : {status['harvested_at'] or 'not recorded'}")
        print(f"filters    : payload indexes on {', '.join(status['payload_indexes']) or 'none'}")

        if args.query:
            _print_hits(args.query)
    finally:
        # Closing the embedded client on the way out keeps the process exit quiet
        # and releases the directory for the next run or for the API.
        vector_store.reset_clients()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
