"""
Career & Roles Domain Service for CareerCompass.
Handles database queries for roles, market intelligence retrieval, and smart candidate matching.
"""

import json
import re
from functools import lru_cache
from typing import List, Dict, Any, Optional
from app_logging import get_logger
from config import SKILL_OPTIONS
from database.db import get_connection

log = get_logger("careercompass.matching")

# How much each half of the score is worth. Kept here (not in the UI) so the
# explanation a candidate reads can never drift from the ranking they see.
INTEREST_WEIGHT = 65
SKILL_WEIGHT = 35

# Semantic recall tuning. The vector index only ever decides *which* roles get
# scored — it never changes a score — and it can only ever add candidates on top
# of those that qualify on interest keywords, so a missing or stale index cannot
# take a role away from a candidate.
SEMANTIC_RECALL_LIMIT = 40   # neighbours requested from the index
SEMANTIC_EXTRA_LIMIT = 10    # meaning-only roles allowed to reach the results
# Cosine similarity below which "nearest" means "unrelated". The local hashing
# embedder and Gemini live on different similarity scales, so the floor travels
# with the provider rather than being one shared number.
SEMANTIC_FLOOR = {"local": 0.15, "gemini": 0.60}


def _semantic_floor() -> float:
    """Similarity below which "nearest" means "unrelated", for the active embedder."""
    try:
        from services import embeddings
        provider = embeddings.active_provider()
    except Exception:  # pragma: no cover - import guard
        provider = "local"
    return SEMANTIC_FLOOR.get(provider, SEMANTIC_FLOOR["local"])


def _semantic_recall(profile: Dict[str, Any]) -> Dict[str, float]:
    """Nearest roles by meaning, keyed by role id — {} when there is no index.

    Imported lazily and defensively so `/match` keeps working (keyword-only)
    even where the retrieval stack or its optional dependency is unavailable.
    """
    try:
        from services import vector_store
    except Exception as exc:  # pragma: no cover - import guard
        log.warning("Semantic recall unavailable (%s)", exc)
        return {}
    query = vector_store.profile_query(profile)
    return dict(vector_store.semantic_search(query, limit=SEMANTIC_RECALL_LIMIT))


def _row_to_role_dict(row) -> Dict[str, Any]:
    """Converts a SQLite database row into a structured role dictionary."""
    return {
        "id": row["id"],
        "title": row["title"],
        "category": row["category"],
        "icon": row["icon"],
        "market_demand": row["market_demand"],
        "competition_level": row["competition_level"],
        "future_relevance": row["future_relevance"],
        "is_niche": bool(row["is_niche"]),
        "niche_category": row["niche_category"],
        "description": row["description"],
        "responsibilities": json.loads(row["responsibilities_json"] or "[]"),
        "qualifications": json.loads(row["qualifications_json"] or "[]"),
        "growth_path": json.loads(row["growth_path_json"] or "[]"),
        "salary": {
            "fresher_0_1": {"min": row["salary_fresher_min"], "max": row["salary_fresher_max"], "label": "0–1 yr"},
            "mid_1_3": {"min": row["salary_mid_min"], "max": row["salary_mid_max"], "label": "1–3 yrs"},
            "senior_3_plus": {"min": row["salary_senior_min"], "max": row["salary_senior_max"], "label": "3+ yrs"},
            # Provenance for the bands above: what each figure is measured
            # against, where it came from, and when it was last reviewed.
            "as_of": row["salary_as_of"] or "",
            "market_median": row["salary_market_median"],
            "product_median": row["salary_product_median"],
            "sources": json.loads(row["salary_sources_json"] or "[]"),
            "anchor_note": row["salary_anchor_note"] or ""
        },
        "top_companies": json.loads(row["top_companies_json"] or "[]"),
        "skills": {
            "must_have": json.loads(row["skills_must_have_json"] or "[]"),
            "good_to_have": json.loads(row["skills_good_to_have_json"] or "[]"),
            "can_have": json.loads(row["skills_can_have_json"] or "[]")
        },
        "matching_interests": json.loads(row["matching_interests_json"] or "[]"),
        "matching_skills": json.loads(row["matching_skills_json"] or "[]")
    }


def get_all_roles() -> List[Dict[str, Any]]:
    """Retrieves all corporate & modern technology roles from the database."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM roles ORDER BY title ASC;")
        rows = cursor.fetchall()
        return [_row_to_role_dict(r) for r in rows]
    finally:
        conn.close()


def get_role_by_id(role_id: str) -> Optional[Dict[str, Any]]:
    """Fetches a specific role by its unique ID."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM roles WHERE id = ?;", (role_id,))
        row = cursor.fetchone()
        return _row_to_role_dict(row) if row else None
    finally:
        conn.close()


def get_all_categories() -> List[str]:
    """Returns unique categories sorted alphabetically."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT category FROM roles ORDER BY category ASC;")
        return [r["category"] for r in cursor.fetchall()]
    finally:
        conn.close()


def search_and_filter_roles(
    search_query: str = "",
    category: str = "All Categories",
    niche_filter: str = "All Roles"
) -> List[Dict[str, Any]]:
    """Applies database search and category filters."""
    roles = get_all_roles()
    filtered = roles

    if search_query.strip():
        q = search_query.strip().lower()
        filtered = [
            r for r in filtered
            if q in r["title"].lower()
            or q in r["description"].lower()
            or any(q in s.lower() for s in r["skills"]["must_have"])
            or any(q in s.lower() for s in r["matching_skills"])
            or any(q in c.lower() for c in r["top_companies"])
        ]

    if category != "All Categories":
        filtered = [r for r in filtered if r["category"] == category]

    if niche_filter == "Niche Specialists Only 🎯":
        filtered = [r for r in filtered if r["is_niche"]]
    elif niche_filter == "Mainstream Core Only 🏢":
        filtered = [r for r in filtered if not r["is_niche"]]

    return filtered


_WORD_RE = re.compile(r"[a-z0-9+#]+")


@lru_cache(maxsize=None)
def _keywords(text: str) -> frozenset:
    """Lowercase word tokens, keeping symbols used in tech terms (c++, c#).

    Memoised: matching scores every role's skills against every profile chip, and
    the same short strings come up thousands of times per request under the
    test-suite's exhaustive sweeps.
    """
    return frozenset(_WORD_RE.findall(text.lower()))


def _terms_overlap(user_term: str, role_term: str) -> bool:
    """True when a user keyword/phrase is clearly related to a role keyword."""
    u, r = user_term.strip().lower(), role_term.strip().lower()
    if not u or not r:
        return False
    if u in r or r in u:
        return True
    return bool(_keywords(u) & _keywords(r))


def suggested_skills_for(role_skills: List[str], user_skills: List[str]) -> List[str]:
    """
    Profile chips the candidate could add that this role genuinely scores on.

    Relevance uses a *stricter* test than the scorer: whole-token overlap only,
    never substring containment. That keeps the advice honest in both
    directions — a suggestion is always a real scoring keyword of the role
    (adding it therefore cannot lower the skill half of the score), while the
    loose substring rule can never leak a bogus tip such as "Go" for a
    MongoDB role.
    """
    def already_counted(chip: str) -> bool:
        return any(_terms_overlap(chip, user_skill) for user_skill in user_skills)

    def is_scoring_keyword_of_role(chip: str) -> bool:
        tokens = _keywords(chip)
        return any(tokens & _keywords(role_skill) for role_skill in role_skills)

    return [
        chip for chip in SKILL_OPTIONS
        if not already_counted(chip) and is_scoring_keyword_of_role(chip)
    ]


def match_roles_smart(profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Ranks roles by interest fit (65% weight) and existing-skill fit (35% weight).

    Each result is a dict:
        {"role": role, "score": int,
         "interest_score": int, "skill_score": int,
         "matched_interests": [...], "matched_skills": [...],
         "suggested_skills": [...],
         "recalled_by": ["keyword" | "semantic", ...],
         "semantic_similarity": float | None}

    Matching is deliberately explainable: the two component scores are 0-100
    percentages of what the candidate actually supplied, they are what the
    final `score` is computed from, and `suggested_skills` names the profile
    chips that would move the skill half. A candidate can therefore reproduce
    the number on screen by hand.

    Roles with zero genuine interest alignment are excluded, so every result
    reflects at least one interest the candidate explicitly chose. Scores are
    honest — there is no artificial floor or ceiling.

    Two stages feed the ranking. *Recall* decides which roles are worth scoring:
    every role whose interests overlap the candidate's chips, plus a small
    number of roles the vector index finds semantically near the profile (see
    `recalled_by`). *Ranking* is still this transparent scorer, unchanged — so a
    role found purely by meaning still has to earn a non-zero score on real
    skills before it is shown.
    """
    roles = get_all_roles()
    # Original casing is preserved in the output so the explanation can quote the
    # candidate's own chips; every comparison below is case-insensitive anyway.
    user_skills = [s.strip() for s in profile.get("current_skills", []) if s.strip()]
    user_interests = [i.strip() for i in profile.get("interests", []) if i.strip()]

    if not user_interests:
        return []

    semantic_scores = _semantic_recall(profile)
    score_floor = _semantic_floor()
    roles_by_id = {role["id"]: role for role in roles}

    # Stage 1 — recall. Keyword-qualified roles are always candidates.
    candidates: List[tuple] = []
    for role in roles:
        matched = [
            ui for ui in user_interests
            if any(_terms_overlap(ui, ri) for ri in [i.lower() for i in role["matching_interests"]])
        ]
        if matched:
            candidates.append((role, matched))

    # Then the best meaning-only neighbours, capped: a vague profile should not
    # be able to flood the page with roles that share no interest at all.
    keyword_ids = {role["id"] for role, _ in candidates}
    meaning_only = sorted(
        (
            (role_id, similarity)
            for role_id, similarity in semantic_scores.items()
            if role_id not in keyword_ids
            and role_id in roles_by_id
            and similarity >= score_floor
        ),
        key=lambda pair: pair[1],
        reverse=True,
    )[:SEMANTIC_EXTRA_LIMIT]
    for role_id, _similarity in meaning_only:
        candidates.append((roles_by_id[role_id], []))

    results: List[Dict[str, Any]] = []

    for role, matched_interests in candidates:
        role_skills = [s.lower() for s in role["matching_skills"]]

        matched_skills = [
            us for us in user_skills
            if any(_terms_overlap(us, rs) for rs in role_skills)
        ]

        interest_score = int(round(len(matched_interests) / len(user_interests) * 100))
        skill_score = int(round(len(matched_skills) / len(user_skills) * 100)) if user_skills else 0

        # Computed from the rounded percentages the candidate can see, so the
        # displayed components always add up to the displayed score. Integer
        # half-up rounding (not Python's banker's rounding) because that is the
        # arithmetic a reader does in their head.
        score = (interest_score * INTEREST_WEIGHT + skill_score * SKILL_WEIGHT + 50) // 100
        score = max(0, min(100, score))

        similarity = semantic_scores.get(role["id"])
        # A role reached only by meaning has to score on something real; a 0%
        # suggestion would be noise on a ranked page.
        if not matched_interests and score <= 0:
            continue

        recalled_by = []
        if matched_interests:
            recalled_by.append("keyword")
        if similarity is not None:
            recalled_by.append("semantic")

        results.append({
            "role": role,
            "score": score,
            "interest_score": interest_score,
            "skill_score": skill_score,
            "matched_interests": matched_interests,
            "matched_skills": matched_skills,
            "suggested_skills": suggested_skills_for(role_skills, user_skills),
            "recalled_by": recalled_by,
            "semantic_similarity": round(similarity, 4) if similarity is not None else None,
        })

    results.sort(key=lambda item: item["score"], reverse=True)
    return results
