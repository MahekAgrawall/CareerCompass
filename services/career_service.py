"""
Career & Roles Domain Service for CareerCompass.
Handles database queries for roles, market intelligence retrieval, and smart candidate matching.
"""

import json
from typing import List, Dict, Any, Optional, Tuple
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


def match_roles_smart(profile: Dict[str, Any]) -> List[Tuple[int, Dict[str, Any]]]:
    """
    Ranks roles strictly prioritizing candidate's explicit interests (65% weight)
    and technical baseline (35% weight). Excludes roles with zero interest synergy.
    """
    roles = get_all_roles()
    user_skills = [s.strip().lower() for s in profile.get("current_skills", [])]
    user_interests = [i.strip().lower() for i in profile.get("interests", [])]

    if not user_interests:
        return []

    scored_roles = []

    for role in roles:
        role_skills = [s.strip().lower() for s in role["matching_skills"]]
        role_interests = [i.strip().lower() for i in role["matching_interests"]]

        # 1. Interest Match (65% weight)
        interest_hits = 0
        for ui in user_interests:
            for ri in role_interests:
                if ui in ri or ri in ui or any(word in ri for word in ui.split()):
                    interest_hits += 1
                    break

        # STRICT FILTER: Role must have at least one genuine interest alignment
        if interest_hits == 0:
            continue

        interest_score = min(1.0, interest_hits / max(1, min(len(user_interests), 3)))

        # 2. Skill Match (35% weight)
        skill_hits = 0
        for us in user_skills:
            for rs in role_skills:
                if us in rs or rs in us:
                    skill_hits += 1
                    break

        skill_score = min(1.0, skill_hits / max(1, min(len(user_skills), 4)))

        # Composite match percentage
        match_pct = int((interest_score * 65) + (skill_score * 35))
        match_pct = max(45, min(98, match_pct))

        scored_roles.append((match_pct, role))

    scored_roles.sort(key=lambda x: x[0], reverse=True)
    return scored_roles
