"""
Retrieval evaluation harness: does the index recall the role a candidate means?

`career_service.match_roles_smart` is two stages, and only the first is retrieval
work. *Recall* decides which roles are worth scoring — every role whose interests
overlap the candidate's chips, plus a capped number of vector neighbours above a
similarity floor — and then the transparent 65/35 scorer ranks them and explains
the arithmetic. The floor (`SEMANTIC_FLOOR`), the cap (`SEMANTIC_EXTRA_LIMIT`)
and the neighbour window (`SEMANTIC_RECALL_LIMIT`) were all picked by reading a
handful of examples. That is how everyone tunes a retrieval system right up until
they get a number, and then they stop doing it.

This harness turns those examples into a labelled set (`labels.json`) and reports
what the current configuration actually does with it, in three parts:

1. **Index quality** — for each labelled profile, is the role it means among the
   nearest neighbours, and at what rank (`hit@k`, `recall@k`, `MRR@k`)? The
   labels distinguish expectations that the *keyword* stage would have found
   anyway from *meaning-only* ones, because only the second kind is evidence that
   the vector index is earning its place.
2. **The floor, swept** — meaning-only recall and precision at every threshold on
   a grid, with the configured floor marked and the best-F1 point named. This is
   the recall/precision trade-off the floor controls, as a table.
3. **End to end** — whether an expected role actually reaches the *scored,
   ranked* results, run twice: once with the index and once with semantic recall
   disabled. The difference is the index's contribution, measured rather than
   asserted, and the meaning-only slots it awarded (and how many were labelled
   correct) show what a low floor costs in page space.

Which embedder? `--provider local|gemini|both`. Each provider is a separate
vector space with its own collection, so the harness builds one per provider and
the comparison is apples to apples — same labels, same documents, same scorer.

How to run it (from `backend/`):

    .\\.venv\\Scripts\\python.exe -m evals.retrieval_eval
    .\\.venv\\Scripts\\python.exe -m evals.retrieval_eval --provider both --json

The harness is hermetic on purpose: it points the database and the vector store
at its own temporary directory, so it never reads or writes the development
`data/career_compass.db` and never contends for the Qdrant lock the API server
holds. `--index-dir` reuses a real index instead (for an end-to-end number on the
deployed vectors), in which case the server has to be stopped first.

This is a measurement tool, not a gate: it is deliberately *not* part of the unit
suite, because its numbers depend on the embedding provider, the network and the
catalogue. The suite tests the arithmetic here (`tests/test_retrieval_eval.py`).
"""

import argparse
import json
import logging
import os
import shutil
import statistics
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple
from unittest import mock

from app_logging import get_logger

log = get_logger("careercompass.evals")

HERE = os.path.dirname(os.path.abspath(__file__))
LABELS_PATH = os.path.join(HERE, "labels.json")

#: Thresholds to sweep, per provider. The two embedders live on different
#: similarity scales (the local hashing embedder packs everything into a narrow
#: band near the centre; Gemini spreads real semantics much further out), so they
#: get different windows rather than one that is useless for one of them.
SWEEP_GRID = {
    "local": [round(0.05 * step, 2) for step in range(1, 9)],   # 0.05 … 0.40
    "gemini": [round(0.05 * step, 2) for step in range(8, 18)],  # 0.40 … 0.85
}

#: One full run costs ~100 role documents plus one query per labelled case, which
#: is more than a shared or free-tier API key will serve in a minute (the Gemini
#: free tier counts 100 embed items per minute). Rather than die two thirds of the
#: way through with a half-built index, the harness waits out a rate limit and
#: retries. `--pace 0` turns that off.
RATE_LIMIT_WAIT = 30.0
RATE_LIMIT_RETRIES = 8
_RATE_LIMIT_HINTS = ("429", "quota", "rate limit", "resource_exhausted")


def _is_rate_limit(error: Exception) -> bool:
    text = str(error).lower()
    return any(hint in text for hint in _RATE_LIMIT_HINTS)


def _with_backoff(action, describe: str, wait: float, retries: int):
    """Runs `action`, waiting out provider rate limits instead of failing.

    Only rate-limit errors are retried: a missing key or a retired model is a
    configuration problem, and sleeping on it for four minutes would just hide it.
    """
    from services import embeddings

    delays = retries + 1 if wait > 0 else 1
    for attempt in range(delays):
        try:
            return action()
        except embeddings.EmbeddingError as error:
            if attempt + 1 >= delays or not _is_rate_limit(error):
                raise
            log.warning(
                "%s is rate limited; waiting %.0fs and retrying (%d/%d)",
                describe, wait, attempt + 1, retries,
            )
            time.sleep(wait)


# ── The labelled set ──────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Case:
    """One labelled profile: what it means, and why that label is fair."""

    id: str
    note: str
    profile: Dict[str, Any]
    expect: Tuple[str, ...]


@dataclass(frozen=True)
class Labelled:
    """The label set plus the reachability split the metrics are read against."""

    cases: List[Case]
    version: int
    description: str


def load_labels(path: str = LABELS_PATH) -> Labelled:
    """Reads and shape-checks `labels.json`. Raises `ValueError` on a bad file."""
    with open(path, encoding="utf-8") as handle:
        raw = json.load(handle)

    entries = raw.get("cases")
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"{path} has no cases")

    cases: List[Case] = []
    seen: set = set()
    for index, entry in enumerate(entries):
        where = f"{path} case #{index}"
        for key in ("id", "profile", "expect"):
            if key not in entry:
                raise ValueError(f"{where} is missing {key!r}")
        case_id = str(entry["id"]).strip()
        if not case_id:
            raise ValueError(f"{where} has an empty id")
        if case_id in seen:
            raise ValueError(f"{where} repeats the id {case_id!r}")
        seen.add(case_id)
        expect = tuple(str(role_id).strip() for role_id in entry["expect"])
        if not expect or not all(expect):
            raise ValueError(f"{where} needs at least one non-empty expected role")
        profile = entry["profile"]
        if not isinstance(profile, dict) or not profile.get("interests"):
            raise ValueError(f"{where} needs a profile with at least one interest")
        cases.append(
            Case(
                id=case_id,
                note=str(entry.get("note", "")).strip(),
                profile=dict(profile),
                expect=expect,
            )
        )

    return Labelled(
        cases=cases,
        version=int(raw.get("version", 1)),
        description=str(raw.get("description", "")).strip(),
    )


def validate_against(expectations: Sequence[Case], known_role_ids: Sequence[str]) -> None:
    """Every label must name a role that exists, or the numbers are fiction.

    A typo in an expected id would otherwise look exactly like a recall failure:
    the index can never return a role that is not in the catalogue, so the case
    would silently count as a miss forever.
    """
    known = set(known_role_ids)
    unknown = sorted(
        {role_id for case in expectations for role_id in case.expect if role_id not in known}
    )
    if unknown:
        raise ValueError(
            "labels.json names role ids that are not in the catalogue: "
            + ", ".join(unknown)
            + " (roles.json is the source of truth)"
        )


def keyword_reachable(profile: Dict[str, Any], role: Dict[str, Any]) -> bool:
    """Whether the *keyword* stage would have recalled this role on its own.

    Uses the matcher's own rule (`career_service._terms_overlap`) rather than a
    reimplementation, because the whole point is to measure the real pipeline:
    an out-of-date copy of this predicate would silently reclassify cases as
    "meaning-only" and overstate what the index contributes.
    """
    from services import career_service

    interests = [str(chip) for chip in (profile.get("interests") or [])]
    role_interests = [str(chip).lower() for chip in (role.get("matching_interests") or [])]
    return any(
        career_service._terms_overlap(chip, role_interest)
        for chip in interests
        for role_interest in role_interests
    )


# ── Pure metrics (unit-tested without an index) ───────────────────────────────
def hit_at_k(ranked_ids: Sequence[str], expected: Sequence[str], k: int) -> bool:
    """Whether any expected role is inside the top `k` neighbours."""
    return any(role_id in expected for role_id in ranked_ids[:k])


def recall_at_k(ranked_ids: Sequence[str], expected: Sequence[str], k: int) -> float:
    """Fraction of the expected roles found inside the top `k` neighbours."""
    if not expected:
        return 0.0
    found = len(set(expected) & set(ranked_ids[:k]))
    return found / len(set(expected))


def reciprocal_rank(ranked_ids: Sequence[str], expected: Sequence[str], k: int) -> float:
    """1/rank of the first expected neighbour, 0.0 when there is none in `k`."""
    expected_set = set(expected)
    for rank, role_id in enumerate(ranked_ids[:k], start=1):
        if role_id in expected_set:
            return 1.0 / rank
    return 0.0


def sweep_thresholds(rows: Sequence[Tuple[Sequence[Tuple[str, float]], Sequence[str], Sequence[str]]],
                     thresholds: Sequence[float]) -> List[Dict[str, Any]]:
    """Recall/precision of the meaning-only gate at every threshold.

    `rows` is `[(ranked neighbours, expected, meaning-only expected), …]`. For a
    threshold `t`, a neighbour "passes" when its similarity is at least `t` — the
    exact test `match_roles_smart` applies before it will spend an extra slot on a
    role no interest chip asked for.

    Both figures are micro-averaged over every case rather than averaged per case:
    pooling keeps a profile with many expectations from outweighing one with a
    single label, and it is the aggregate behaviour the floor actually governs.

    `precision` counts only *labelled* positives, so it is a **lower bound** —
    roles the labels do not mention count as wrong even when a human would call
    them a reasonable neighbour. Read it as "of the roles the floor lets past,
    this share was one we asked for", not as a measure of the index's taste.
    """
    results: List[Dict[str, Any]] = []
    cases = len(rows) or 1
    for threshold in thresholds:
        passed = 0
        passed_expected = 0
        meaning_total = 0
        meaning_kept = 0
        for ranked, expected, meaning_only in rows:
            above = [role_id for role_id, score in ranked if score >= threshold]
            passed += len(above)
            passed_expected += sum(1 for role_id in above if role_id in set(expected))
            meaning_total += len(meaning_only)
            meaning_kept += sum(1 for role_id in above if role_id in set(meaning_only))

        meaning_recall = (meaning_kept / meaning_total) if meaning_total else None
        precision = (passed_expected / passed) if passed else None
        f1 = _f1(meaning_recall, precision)
        results.append({
            "threshold": round(float(threshold), 4),
            "meaning_recall": _round(meaning_recall),
            "precision": _round(precision),
            "f1": _round(f1),
            "neighbours_above": passed,
            #: How many extra roles per candidate clear the gate — the cost side of
            #: "let more meaning through": every one of them is a slot on a page.
            "slots_per_case": round(passed / cases, 2),
            "meaning_expected": meaning_total,
            "meaning_found": meaning_kept,
        })
    return results


def best_threshold(sweep: Sequence[Dict[str, Any]]) -> Optional[float]:
    """The swept threshold with the best F1, or None when nothing scored."""
    scored = [row for row in sweep if row.get("f1") is not None]
    if not scored:
        return None
    return max(scored, key=lambda row: (row["f1"], row["meaning_recall"] or 0.0))["threshold"]


def _f1(recall: Optional[float], precision: Optional[float]) -> Optional[float]:
    if not recall or not precision:
        return None
    return 2 * recall * precision / (recall + precision)


def _round(value: Optional[float]) -> Optional[float]:
    return None if value is None else round(float(value), 4)


def _mean(values: Sequence[float]) -> float:
    return statistics.mean(values) if values else 0.0


# ── Index-level evaluation ────────────────────────────────────────────────────
@dataclass
class IndexOutcome:
    """One case measured against the index, before the scorer gets involved."""

    case_id: str
    neighbours: List[Tuple[str, float]]
    expected: Tuple[str, ...]
    keyword_expected: Tuple[str, ...]
    meaning_expected: Tuple[str, ...]

    @property
    def ranked_ids(self) -> List[str]:
        return [role_id for role_id, _ in self.neighbours]


def _search_neighbours(profile: Dict[str, Any], case_id: str, limit: int,
                       wait: float, retries: int) -> List[Tuple[str, float]]:
    """Recalls neighbours, seeing through `semantic_search`'s silent degradation.

    `semantic_search` is *designed* to swallow a provider failure and return no
    neighbours so the running app keeps working on keywords alone. A measurement
    tool must not inherit that: an empty list would be scored as "the index
    missed" when the truth is "we never asked" — which is exactly the fake
    number this harness exists to prevent. So an empty result is treated as
    suspicious: probe the embedder directly (that call *does* raise, so the
    wait-and-retry policy applies) and only then search again. An empty result
    that survives a successful probe is a genuine miss.
    """
    from services import embeddings, vector_store

    query = vector_store.profile_query(profile)
    neighbours = vector_store.semantic_search(query, limit=limit)
    if neighbours:
        return neighbours
    _with_backoff(
        lambda: embeddings.embed_query("retrieval evaluation probe"),
        f"the query for {case_id}",
        wait,
        retries,
    )
    return vector_store.semantic_search(query, limit=limit)


def measure_index(cases: Sequence[Case], roles_by_id: Dict[str, Dict[str, Any]],
                  limit: int, wait: float = RATE_LIMIT_WAIT,
                  retries: int = RATE_LIMIT_RETRIES) -> List[IndexOutcome]:
    """Sends every labelled profile through the real recall path.

    `limit` is `SEMANTIC_RECALL_LIMIT` — the window the matcher itself asks for,
    passed in so the harness measures the neighbours the pipeline can actually
    see rather than a number of its own choosing. Embedding a query costs a
    provider call per case, so these are the calls a rate limit hits first.
    """
    outcomes: List[IndexOutcome] = []
    for case in cases:
        neighbours = _search_neighbours(case.profile, case.id, limit, wait, retries)
        known = [(role_id, score) for role_id, score in neighbours if role_id in roles_by_id]
        expected = tuple(role_id for role_id in case.expect if role_id in roles_by_id)
        keyword = tuple(
            role_id for role_id in expected
            if keyword_reachable(case.profile, roles_by_id[role_id])
        )
        outcomes.append(
            IndexOutcome(
                case_id=case.id,
                neighbours=known,
                expected=expected,
                keyword_expected=keyword,
                meaning_expected=tuple(role_id for role_id in expected if role_id not in keyword),
            )
        )
    return outcomes


# ── End-to-end evaluation (through the scorer) ────────────────────────────────
def measure_pipeline(cases: Sequence[Case], k: int, use_index: bool) -> Dict[str, Any]:
    """Runs `match_roles_smart` for every case and reports what reached the page.

    With `use_index=False` semantic recall is patched out for the duration, which
    is the honest keyword-only baseline: the same profiles, the same scorer, no
    index — the exact state of the app before the migration is run.
    """
    from services import career_service

    served = served_top = 0
    slots = slots_expected = 0
    per_case: List[Dict[str, Any]] = []

    def run() -> None:
        nonlocal served, served_top, slots, slots_expected
        for case in cases:
            results = career_service.match_roles_smart(case.profile)
            ids = [match["role"]["id"] for match in results]
            if any(role_id in case.expect for role_id in ids):
                served += 1
            if any(role_id in case.expect for role_id in ids[:k]):
                served_top += 1
            awarded = [
                match["role"]["id"] for match in results if match["recalled_by"] == ["semantic"]
            ]
            slots += len(awarded)
            slots_expected += sum(1 for role_id in awarded if role_id in case.expect)
            per_case.append({
                "id": case.id,
                "served": any(role_id in case.expect for role_id in ids),
                "served_top": any(role_id in case.expect for role_id in ids[:k]),
                "meaning_slots": len(awarded),
                "meaning_slots_expected": sum(
                    1 for role_id in awarded if role_id in case.expect
                ),
            })

    if use_index:
        run()
    else:
        with mock.patch.object(career_service, "_semantic_recall", lambda profile: {}):
            run()

    total = len(cases)
    return {
        "served": _round(served / total) if total else 0.0,
        f"served_at_{k}": _round(served_top / total) if total else 0.0,
        "meaning_slots": slots,
        "meaning_slots_expected": slots_expected,
        "per_case": per_case,
    }


# ── One provider, end to end ──────────────────────────────────────────────────
@dataclass
class ProviderReport:
    """Everything measured for one embedding space."""

    provider: str
    model: str
    collection: str
    points: int
    reused: bool
    case_count: int
    k: int
    window: int
    hit_at_k: float
    window_hit: float
    recall_at_k: float
    mrr: float
    expected_total: int
    keyword_expected_total: int
    meaning_expected_total: int
    meaning_cases: int
    meaning_hit_at_k: Optional[float]
    configured_floor: float
    sweep: List[Dict[str, Any]] = field(default_factory=list)
    best_floor: Optional[float] = None
    keyword_only: Dict[str, Any] = field(default_factory=dict)
    with_index: Dict[str, Any] = field(default_factory=dict)
    misses: List[Dict[str, Any]] = field(default_factory=list)


def prepare_space(provider: str, index_dir: str, wait: float = RATE_LIMIT_WAIT,
                  retries: int = RATE_LIMIT_RETRIES) -> Dict[str, Any]:
    """Points the retrieval stack at `provider` and makes sure its index exists."""
    from services import career_service, embeddings, vector_store

    os.environ["EMBEDDING_PROVIDER"] = provider
    os.environ["QDRANT_PATH"] = index_dir
    os.environ.pop("QDRANT_URL", None)
    vector_store.reset_clients()

    roles = career_service.get_all_roles()
    name = vector_store.collection_name()
    present = vector_store.count_points(name)
    if present == len(roles) and present:
        return {"collection": name, "points": present, "reused": True}

    written = _with_backoff(
        lambda: vector_store.rebuild(roles),
        f"the {len(roles)} role documents",
        wait,
        retries,
    )
    embeddings.record_provider(provider)
    return {"collection": name, "points": written, "reused": False}


def run_provider(provider: str, index_dir: str, k: int, with_sweep: bool = True,
                 wait: float = RATE_LIMIT_WAIT,
                 retries: int = RATE_LIMIT_RETRIES,
                 cases: Optional[Sequence[Case]] = None) -> ProviderReport:
    """Builds (or reuses) one embedding space and evaluates the labels against it.

    `cases` exists for the test suite, which runs this whole path over a handful
    of labels against the real catalogue instead of paying for all of them.
    """
    from services import career_service, embeddings, vector_store

    space = prepare_space(provider, index_dir, wait, retries)
    # One cheap probe before the expensive part: if the provider is rate limited or
    # misconfigured, find out here rather than 35 silently empty searches later.
    _with_backoff(
        lambda: embeddings.embed_query("retrieval evaluation preflight probe"),
        "the preflight probe",
        wait,
        retries,
    )
    roles = career_service.get_all_roles()
    roles_by_id = {role["id"]: role for role in roles}
    expectations = list(cases) if cases is not None else load_labels().cases
    validate_against(expectations, roles_by_id)

    outcomes = measure_index(
        expectations, roles_by_id, career_service.SEMANTIC_RECALL_LIMIT, wait, retries
    )
    if outcomes and not any(outcome.neighbours for outcome in outcomes):
        raise RuntimeError(
            "the index returned no neighbours for any labelled profile — that is a "
            "broken measurement, not a recall score, so no numbers are reported"
        )

    expected_total = sum(len(outcome.expected) for outcome in outcomes)
    keyword_total = sum(len(outcome.keyword_expected) for outcome in outcomes)
    meaning_total = sum(len(outcome.meaning_expected) for outcome in outcomes)

    meaning_outcomes = [outcome for outcome in outcomes if outcome.meaning_expected]
    meaning_hits = [
        hit_at_k(outcome.ranked_ids, outcome.meaning_expected, k) for outcome in meaning_outcomes
    ]

    sweep_rows = [
        (outcome.neighbours, outcome.expected, outcome.meaning_expected) for outcome in outcomes
    ]
    sweep = sweep_thresholds(sweep_rows, SWEEP_GRID.get(provider, SWEEP_GRID["local"])) \
        if with_sweep else []

    misses = [
        {
            "case": outcome.case_id,
            "expected": list(outcome.expected),
            "meaning_only": list(outcome.meaning_expected),
            "nearest": [role_id for role_id, _ in outcome.neighbours[:3]],
        }
        for outcome in outcomes
        if not hit_at_k(outcome.ranked_ids, outcome.expected, k)
    ]

    return ProviderReport(
        provider=provider,
        model=embeddings.model_name(),
        collection=space["collection"],
        points=space["points"],
        reused=space["reused"],
        case_count=len(outcomes),
        k=k,
        window=career_service.SEMANTIC_RECALL_LIMIT,
        hit_at_k=_round(_mean([hit_at_k(o.ranked_ids, o.expected, k) for o in outcomes])),
        recall_at_k=_round(_mean([recall_at_k(o.ranked_ids, o.expected, k) for o in outcomes])),
        window_hit=_round(_mean([
            hit_at_k(o.ranked_ids, o.expected, len(o.ranked_ids)) for o in outcomes
        ])),
        mrr=_round(_mean([reciprocal_rank(o.ranked_ids, o.expected, k) for o in outcomes])),
        expected_total=expected_total,
        keyword_expected_total=keyword_total,
        meaning_expected_total=meaning_total,
        meaning_cases=len(meaning_outcomes),
        meaning_hit_at_k=_round(_mean(meaning_hits)) if meaning_hits else None,
        configured_floor=career_service.SEMANTIC_FLOOR.get(
            provider, career_service.SEMANTIC_FLOOR["local"]
        ),
        sweep=sweep,
        best_floor=best_threshold(sweep),
        keyword_only=measure_pipeline(expectations, k, use_index=False),
        with_index=measure_pipeline(expectations, k, use_index=True),
        misses=misses,
    )


# ── Reporting ─────────────────────────────────────────────────────────────────
def _percent(value: Optional[float]) -> str:
    return "  n/a" if value is None else f"{value * 100:5.1f}%"


def format_report(report: ProviderReport, with_sweep: bool = True) -> List[str]:
    """The human-readable report, as lines."""
    k = report.k
    keyword_only = report.keyword_only
    with_index = report.with_index
    lines = [
        "",
        f"══ {report.provider} · {report.model} " + "═" * 6,
        f"   index        {report.collection} · {report.points} points"
        f" ({'reused' if report.reused else 'built now'})",
        f"   labels       {report.case_count} profiles · {report.expected_total} expected roles"
        f" ({report.keyword_expected_total} keyword-reachable,"
        f" {report.meaning_expected_total} meaning-only)",
        f"   index@k      hit@{k} {_percent(report.hit_at_k)} ·"
        f" recall@{k} {_percent(report.recall_at_k)} · MRR {report.mrr:.3f}",
        f"   recall stage an expected role anywhere in the {report.window}-neighbour"
        f" window: {_percent(report.window_hit)}",
        f"   meaning@k    {_percent(report.meaning_hit_at_k)}"
        f" of cases whose label only the vector index can reach"
        f" ({report.meaning_cases} cases)",
        f"   end to end   keyword-only served {_percent(keyword_only['served'])} ·"
        f" served@{k} {_percent(keyword_only[f'served_at_{k}'])}",
        f"                with index   served {_percent(with_index['served'])} ·"
        f" served@{k} {_percent(with_index[f'served_at_{k}'])}",
        f"                meaning-only slots awarded {with_index['meaning_slots']},"
        f" labelled correct {with_index['meaning_slots_expected']}",
    ]

    if with_sweep and report.sweep:
        lines.append("")
        lines.append("   floor sweep (the meaning-only gate)")
        lines.append("     threshold   meaning recall   precision   F1     slots/case")
        for row in report.sweep:
            marker = "  ← configured" if abs(row["threshold"] - report.configured_floor) < 1e-9 else ""
            best = (
                "  ★ best F1"
                if report.best_floor is not None
                and abs(row["threshold"] - report.best_floor) < 1e-9
                and not marker
                else ""
            )
            lines.append(
                f"       {row['threshold']:.2f}"
                f"        {_percent(row['meaning_recall'])}"
                f"        {_percent(row['precision'])}"
                f"      {_percent(row['f1'])}"
                f"      {row['slots_per_case']:5.1f}{marker}{best}"
            )
        lines.append(
            "     'slots/case' is how many extra roles a candidate gets from meaning alone;"
        )
        lines.append(
            "     precision counts unlabelled roles as wrong, so read it *across thresholds*"
            " rather than as an absolute quality."
        )

    if report.misses:
        lines.append("")
        lines.append(f"   missed at {k} ({len(report.misses)}):")
        for miss in report.misses:
            lines.append(
                f"     - {miss['case']}: wanted {', '.join(miss['expected'])}"
                f" (nearest: {', '.join(miss['nearest']) or 'nothing'})"
            )

    delta_served = with_index["served"] - keyword_only["served"]
    delta_top = with_index[f"served_at_{k}"] - keyword_only[f"served_at_{k}"]
    lines.append("")
    lines.append(
        f"   index contribution: served {delta_served * 100:+.1f}pp ·"
        f" served@{k} {delta_top * 100:+.1f}pp"
    )
    return lines


def format_comparison(reports: Sequence[ProviderReport], k: int) -> List[str]:
    """A side-by-side line per metric, so the two embedders are comparable."""
    if len(reports) < 2:
        return []
    lines = ["", "══ comparison " + "═" * 6, f"   {'metric':<22}" + "".join(
        f"{report.provider:>12}" for report in reports
    )]
    rows = [
        (f"hit@{k}", [report.hit_at_k for report in reports], True),
        (f"recall@{k}", [report.recall_at_k for report in reports], True),
        ("MRR", [report.mrr for report in reports], False),
        (f"meaning hit@{k}", [report.meaning_hit_at_k for report in reports], True),
        (f"served@{k}", [report.with_index[f"served_at_{k}"] for report in reports], True),
    ]
    for label, values, is_percent in rows:
        cells = "".join(
            f"{_percent(value):>12}" if is_percent else f"{'  n/a' if value is None else f'{value:.3f}':>12}"
            for value in values
        )
        lines.append(f"   {label:<22}{cells}")
    return lines


# ── CLI ───────────────────────────────────────────────────────────────────────
def _workspace(index_dir: str = "") -> str:
    """A throwaway directory for the eval's database and (unless given) index."""
    workspace = tempfile.mkdtemp(prefix="careercompass_eval_")
    from database import db

    db.DB_PATH = os.path.join(workspace, "eval.db")
    os.environ["QDRANT_PATH"] = index_dir or os.path.join(workspace, "qdrant")
    os.environ.pop("QDRANT_URL", None)
    return workspace


def _route_logs_to_stderr() -> None:
    """Keeps `--json`'s stdout pure.

    `app_logging.get_logger` attaches a *stdout* handler to every named logger, which
    is right for a server and wrong for a tool whose output is meant to be piped
    straight into a JSON parser. Every `careercompass.*` logger that already exists is
    pointed at stderr instead, so the logs stay visible to a human without a single
    stray line breaking the machine-readable path.
    """
    for name, logger in list(logging.Logger.manager.loggerDict.items()):
        if not isinstance(logger, logging.Logger) or not name.startswith("careercompass"):
            continue
        for handler in logger.handlers:
            is_stream = isinstance(handler, logging.StreamHandler)
            if is_stream and not isinstance(handler, logging.FileHandler):
                handler.setStream(sys.stderr)


def main(argv: Optional[Sequence[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument(
        "--provider",
        default="auto",
        choices=("auto", "local", "gemini", "both"),
        help="embedding space to evaluate (default: whichever the app would use)",
    )
    parser.add_argument("--k", type=int, default=5, help="cut-off for hit/recall/served (default: 5)")
    parser.add_argument(
        "--index-dir",
        default="",
        help="reuse an existing index directory instead of building a throwaway one "
             "(stop the API server first — embedded Qdrant locks its directory)",
    )
    parser.add_argument("--no-sweep", action="store_true", help="skip the threshold sweep")
    parser.add_argument(
        "--pace",
        type=float,
        default=RATE_LIMIT_WAIT,
        help="seconds to wait and retry when the embedding provider rate limits us "
             "(0 disables waiting; default: %(default)s)",
    )
    parser.add_argument("--json", action="store_true", help="print the report as JSON only")
    args = parser.parse_args(argv)

    from database import db
    # Importing these is what creates their loggers, so do it before redirecting them.
    from services import career_service, embeddings, vector_store  # noqa: F401

    if args.json:
        _route_logs_to_stderr()

    workspace = _workspace(args.index_dir)
    try:
        db.init_db()  # seeds the catalogue from roles.json into the throwaway database

        if args.provider == "both":
            wanted = ["local", "gemini"]
        elif args.provider == "auto":
            wanted = [embeddings.active_provider()]
        else:
            wanted = [args.provider]

        reports: List[ProviderReport] = []
        unavailable: List[str] = []
        for provider in wanted:
            try:
                reports.append(
                    run_provider(
                        provider,
                        os.environ["QDRANT_PATH"],
                        args.k,
                        not args.no_sweep,
                        args.pace,
                    )
                )
            except embeddings.EmbeddingError as error:
                unavailable.append(f"{provider}: {error}")
                log.warning("Skipping %s (%s)", provider, error)
            except Exception as error:  # noqa: BLE001 - reported, not swallowed
                unavailable.append(f"{provider}: {error}")
                log.warning("Could not evaluate %s (%s)", provider, error)

        if args.json:
            print(json.dumps(
                {
                    "k": args.k,
                    "index_dir": os.environ["QDRANT_PATH"],
                    "reports": [asdict(report) for report in reports],
                    "unavailable": unavailable,
                },
                indent=2,
            ))
        else:
            for report in reports:
                for line in format_report(report, not args.no_sweep):
                    print(line)
            for line in format_comparison(reports, args.k):
                print(line)
            if unavailable:
                print("")
                for reason in unavailable:
                    # The full provider message is in the log; the report gets one line.
                    print(f"   skipped — {reason.splitlines()[0][:200]}")

        if not reports:
            print("\nNothing was measured. Set GEMINI_API_KEY for the gemini space, or run "
                  "--provider local.", file=sys.stderr)
            return 2
        return 0
    finally:
        vector_store.reset_clients()
        if not args.index_dir:
            shutil.rmtree(workspace, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
