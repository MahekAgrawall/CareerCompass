"""
Career & Roles Domain Service for CareerCompass.
Handles database queries for roles, market intelligence retrieval, and smart candidate matching.
"""

import json
import re
from typing import List, Dict, Any, Optional
from config import SKILL_OPTIONS
from database.db import get_connection

# How much each half of the score is worth. Kept here (not in the UI) so the
# explanation a candidate reads can never drift from the ranking they see.
INTEREST_WEIGHT = 65
SKILL_WEIGHT = 35


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
            "senior_3_plus": {"min": row["salary_senior_min"], "max": row["salary_senior_max"], "label": "3+ yrs"}
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


def _keywords(text: str) -> set:
    """Lowercase word tokens, keeping symbols used in tech terms (c++, c#, .net)."""
    return set(_WORD_RE.findall(text.lower()))


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
         "suggested_skills": [...]}

    Matching is deliberately explainable: the two component scores are 0-100
    percentages of what the candidate actually supplied, they are what the
    final `score` is computed from, and `suggested_skills` names the profile
    chips that would move the skill half. A candidate can therefore reproduce
    the number on screen by hand.

    Roles with zero genuine interest alignment are excluded, so every result
    reflects at least one interest the candidate explicitly chose. Scores are
    honest — there is no artificial floor or ceiling.
    """
    roles = get_all_roles()
    # Original casing is preserved in the output so the explanation can quote the
    # candidate's own chips; every comparison below is case-insensitive anyway.
    user_skills = [s.strip() for s in profile.get("current_skills", []) if s.strip()]
    user_interests = [i.strip() for i in profile.get("interests", []) if i.strip()]

    if not user_interests:
        return []

    results: List[Dict[str, Any]] = []

    for role in roles:
        role_skills = [s.lower() for s in role["matching_skills"]]
        role_interests = [i.lower() for i in role["matching_interests"]]

        matched_interests = [
            ui for ui in user_interests
            if any(_terms_overlap(ui, ri) for ri in role_interests)
        ]
        if not matched_interests:
            continue  # strict: no interest synergy, no recommendation

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

        results.append({
            "role": role,
            "score": score,
            "interest_score": interest_score,
            "skill_score": skill_score,
            "matched_interests": matched_interests,
            "matched_skills": matched_skills,
            "suggested_skills": suggested_skills_for(role_skills, user_skills),
        })

    results.sort(key=lambda item: item["score"], reverse=True)
    return results
