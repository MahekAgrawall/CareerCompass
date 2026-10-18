"""Reads the adverts in a harvest and records what each job actually is.

The Jobs page shows a stored verdict when a listing has one and offers to classify
it when it does not, so nobody has to wait for the model during a page view. This
script is the other half of that: it pre-fills the classifications in the
background, so a feed that has just been ingested becomes a feed that can already
say what its listings are.

    python -m scripts.classify_jobs --limit 100
    python -m scripts.classify_jobs --from-file data/job_postings.json --source adzuna
    python -m scripts.classify_jobs --force --limit 20      # re-read 20 verdicts

Reads the harvest artifact (`--from-file`, the file `scripts.ingest_jobs` writes)
rather than the index by default, which matters for one practical reason: the
embedded Qdrant store is locked by whoever has it open, so a script that read the
index could not run while the API is up. The artifact holds the same postings the
index was built from, turned into the same payloads `services.classification`
reads, so the verdicts land on the very ids the API looks up. `--from-index` reads
the collection instead, and then the API does have to be stopped.

Only listings *without* a verdict are read, so this is safe to re-run and safe to
schedule: `--limit` counts work not yet done, and a listing already classified is
skipped without a model call. `--force` re-reads anyway.

The delay between calls is deliberate. Gemini's free tier meters requests per
minute, and a batch job has the luxury of being slow: finishing the feed overnight
beats exhausting the quota in a minute and leaving half of it unclassified.
"""

import argparse
import os
import sys
import time
from collections import Counter
from typing import Any, Dict, List, Tuple

from app_logging import get_logger
from database.db import DATA_DIR
from services import ai_service, classification, job_feed, vector_store

log = get_logger("careercompass.jobs.classify")

DEFAULT_POSTINGS = os.path.join(DATA_DIR, "job_postings.json")

#: Seconds between model calls — see the module docstring.
DEFAULT_DELAY = 4.0

#: How many model calls in a row may fail to reach the model before the run stops.
#: One is a blip; three in a row is a spent quota or a bad key, and carrying on
#: would spend a delay per listing to collect the same failure. Nothing is lost by
#: stopping: the listings stay unclassified, and re-running picks them up.
GIVE_UP_AFTER = 3

#: Short labels for the kinds in a summary line, where the sentences are too long.
KIND_LABELS = {
    classification.KIND_TOO_THIN: "advert too thin",
    classification.KIND_DECLINED: "no declared family",
    classification.KIND_UNSURE: "low confidence",
    classification.KIND_UNREADABLE: "unreadable answer",
    classification.KIND_UNREACHABLE: "no answer from the model",
}


def _load_postings(from_file: str, from_index: bool, source: str) -> List[Dict[str, Any]]:
    """The adverts to read, newest first, from the artifact or the live index.

    Newest first because that is the order a candidate sees: pre-filling the feed's
    tail before its head would classify the listings nobody is going to open.

    Both sources produce the same payload shape — the index holds what
    `job_feed.posting_payload` built, and an artifact is turned into exactly that
    here — so a verdict written from a file is the same verdict the API would have
    reached for the indexed posting, and is found under the same id.
    """
    if from_index:
        payloads = vector_store.scroll_payloads(
            vector_store.JOBS_COLLECTION, None, classification.MAX_SCAN_POSTINGS
        )
        print(f"source     : {len(payloads)} postings from the live index")
    else:
        try:
            artifact = job_feed.load_artifact(from_file)
        except OSError as error:
            raise SystemExit(
                f"Could not read {from_file}: {error}\n"
                "Run `python -m scripts.ingest_jobs` first, or point --from-file at a "
                "harvest, or pass --from-index to read the live collection."
            ) from error
        payloads = [job_feed.posting_payload(row) for row in artifact["postings"]]
        stamp = artifact.get("harvested_at") or "no harvest date in the file"
        print(f"source     : {len(payloads)} postings from {from_file} ({stamp})")

    if source:
        payloads = [row for row in payloads if row.get("source") == source]
        print(f"filtered   : {len(payloads)} postings from {source}")

    payloads.sort(key=lambda row: (-int(row.get("published_ts") or 0), str(row.get("id") or "")))
    return payloads


def _pending(
    payloads: List[Dict[str, Any]], limit: int, force: bool
) -> Tuple[List[Dict[str, Any]], int]:
    """The first `limit` listings with no verdict yet, and how many were skipped.

    Skipped means *already answered*: this is a pure read of the store, exactly what a
    page view consults, so a listing whose advert has been re-harvested into different
    text counts as unanswered here too rather than being passed over because a row for
    its id exists. An advert with nothing to classify is *not* skipped — it is still
    work this run will do, and it will be reported as such rather than silently
    disappearing into the store.
    """
    pending: List[Dict[str, Any]] = []
    skipped = 0
    for payload in payloads:
        if classification.stored(payload, force=force) is not None:
            skipped += 1
            continue
        pending.append(payload)
        if len(pending) >= limit:
            break
    return pending, skipped


def classify_jobs(
    limit: int = 50,
    from_file: str = DEFAULT_POSTINGS,
    from_index: bool = False,
    source: str = "",
    force: bool = False,
    delay: float = DEFAULT_DELAY,
) -> Dict[str, Any]:
    """Classifies the pending listings, printing each verdict as it lands."""
    payloads = _load_postings(from_file, from_index, source)
    pending, skipped = _pending(payloads, limit, force)
    print(f"pending    : {len(pending)} to read ({skipped} already have a verdict)")

    placed: Counter = Counter()
    unplaced: Counter = Counter()
    unread = 0
    streak = 0
    for index, payload in enumerate(pending, start=1):
        record = classification.classify_posting(payload, force=force)
        kind = record.get("unclassified_kind") or ""
        if kind:
            unplaced[kind] += 1
            label = f"unplaced   {KIND_LABELS.get(kind, kind)}"
            if kind in classification.TRANSIENT_KINDS:
                streak += 1
                if streak >= GIVE_UP_AFTER:
                    unread = len(pending) - index
                    print(
                        f"\nstopped    : {GIVE_UP_AFTER} model calls in a row did not "
                        "answer. Nothing was lost — re-run to carry on from here."
                    )
                    break
            else:
                streak = 0
        else:
            placed[record["primary_category"]] += 1
            label = f"{record['canonical_role']} ({record['classification_confidence']:.2f})"
            streak = 0

        title = (record.get("original_title") or "")[:58]
        print(f"  [{index:>4}/{len(pending)}] {label:<52} ← {title}")
        # An advert too thin to classify never reached the model, so it costs no
        # quota and earns no wait.
        if record.get("model"):
            time.sleep(max(0.0, delay))

    summary = {
        "read": len(pending) - unread,
        "placed": sum(placed.values()),
        "unplaced": sum(unplaced.values()),
        "left": unread,
        "categories": dict(placed.most_common()),
        "unplaced_kinds": dict(unplaced.most_common()),
        "stored": classification.stored_count(),
    }
    return summary


def _print_summary(summary: Dict[str, Any]) -> None:
    print()
    print(f"read       : {summary['read']} listings")
    print(
        f"placed     : {summary['placed']}   unplaced: {summary['unplaced']}"
        + (f"   left unread: {summary['left']}" if summary["left"] else "")
    )
    if summary["categories"]:
        print(
            "categories : "
            + ", ".join(f"{name} {count}" for name, count in summary["categories"].items())
        )
    if summary["unplaced_kinds"]:
        print(
            "why not    : "
            + ", ".join(
                f"{KIND_LABELS.get(kind, kind)} {count}"
                for kind, count in summary["unplaced_kinds"].items()
            )
        )
    print(f"stored     : {summary['stored']} listings now have a verdict")


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--limit", type=int, default=50, metavar="N",
                        help="how many unclassified listings to read (default 50)")
    parser.add_argument("--from-file", default=DEFAULT_POSTINGS,
                        help="harvest JSON to read adverts from")
    parser.add_argument("--from-index", action="store_true",
                        help="read the live index instead (needs it to itself: stop the API)")
    parser.add_argument("--source", default="",
                        help="restrict to one board, e.g. adzuna")
    parser.add_argument("--force", action="store_true",
                        help="re-read listings that already have a verdict")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY, metavar="SECONDS",
                        help=f"pause between model calls (default {DEFAULT_DELAY:g})")
    args = parser.parse_args(argv)

    if not ai_service.is_configured():
        raise SystemExit(
            "No Gemini API key found, so there is no model to read the adverts with.\n"
            "Copy .env.example to .env, paste your free key from "
            "https://aistudio.google.com, then re-run. The API reports the same thing "
            "as a 503 on POST /jobs/classify."
        )

    summary = classify_jobs(
        limit=max(0, args.limit),
        from_file=args.from_file,
        from_index=args.from_index,
        source=args.source,
        force=args.force,
        delay=args.delay,
    )
    _print_summary(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
