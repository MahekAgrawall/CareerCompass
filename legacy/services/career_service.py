"""
Career & Roles Domain Service for CareerCompass.
Handles database queries for roles, market intelligence retrieval, and smart candidate matching.
"""

import json
import re
from typing import List, Dict, Any, Optional
from database.db import get_connection


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


def match_roles_smart(profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Ranks roles by interest fit (65% weight) and existing-skill fit (35% weight).

    Each result is a dict:
        {"role": role, "score": int,
         "matched_interests": [...], "matched_skills": [...]}

    Roles with zero genuine interest alignment are excluded, so every result
    reflects at least one interest the candidate explicitly chose. Scores are
    honest — there is no artificial floor or ceiling.
    """
    roles = get_all_roles()
    user_skills = [s.strip().lower() for s in profile.get("current_skills", []) if s.strip()]
    user_interests = [i.strip().lower() for i in profile.get("interests", []) if i.strip()]

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

        interest_score = len(matched_interests) / len(user_interests)
        skill_score = (len(matched_skills) / len(user_skills)) if user_skills else 0.0

        score = int(round(interest_score * 65 + skill_score * 35))
        score = max(0, min(100, score))

        results.append({
            "role": role,
            "score": score,
            "matched_interests": matched_interests,
            "matched_skills": matched_skills,
        })

    results.sort(key=lambda item: item["score"], reverse=True)
    return results
