"""
Authentication & User Persistence Service for CareerCompass.
Handles credentials, user session persistence, profiles, and saved roadmaps.
"""

import hashlib
import hmac
import json
import secrets
from typing import Optional, Dict, Any, Tuple, List
from database.db import get_connection


PBKDF2_ITERATIONS = 200_000


def _hash_password(password: str) -> str:
    """Hashes a password with PBKDF2-HMAC-SHA256 and a per-user random salt."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    """Verifies a password against a stored hash (also accepts legacy SHA-256)."""
    if not stored:
        return False
    if stored.startswith("pbkdf2_sha256$"):
        try:
            _, iterations, salt_hex, digest_hex = stored.split("$")
            digest = hashlib.pbkdf2_hmac(
                "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
            )
            return hmac.compare_digest(digest.hex(), digest_hex)
        except (ValueError, TypeError):
            return False
    # Legacy unsalted SHA-256 — upgraded automatically on next successful login.
    legacy = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return hmac.compare_digest(legacy, stored)


def _upgrade_password_hash(user_id: int, password: str):
    """Re-hashes a legacy password with the current algorithm."""
    conn = get_connection()
    try:
        with conn:
            conn.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?;",
                (_hash_password(password), user_id)
            )
    finally:
        conn.close()


def signup_user(name: str, email: str, password: str) -> Tuple[bool, str]:
    """Registers a new user in the database."""
    name = name.strip()
    email = email.strip().lower()

    if not name or not email or not password:
        return False, "All fields are required."
    if len(password) < 8:
        return False, "Password must be at least 8 characters."

    conn = get_connection()
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE email = ?;", (email,))
            if cursor.fetchone():
                return False, "An account with this email already exists."

            pwd_hash = _hash_password(password)
            cursor.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?);",
                (name, email, pwd_hash)
            )
            return True, "Account registered successfully! Please log in."
    except Exception as e:
        return False, f"Registration failed: {str(e)}"
    finally:
        conn.close()


def authenticate_user(email: str, password: str) -> Tuple[bool, Any]:
    """Authenticates credentials against the users table."""
    email = email.strip().lower()
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, email, password_hash FROM users WHERE email = ?;", (email,))
        row = cursor.fetchone()
        if not row:
            return False, "No account found with this email."

        if not _verify_password(password, row["password_hash"]):
            return False, "Incorrect password."

        # Opportunistically upgrade legacy hashes to the salted format.
        if not row["password_hash"].startswith("pbkdf2_sha256$"):
            _upgrade_password_hash(row["id"], password)

        user_data = {
            "id": row["id"],
            "name": row["name"],
            "email": row["email"],
            "profile": get_user_profile(row["id"])
        }
        return True, user_data
    finally:
        conn.close()


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    """Loads a user (with profile) by primary key — used for JWT auth."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, email FROM users WHERE id = ?;", (user_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "name": row["name"],
            "email": row["email"],
            "profile": get_user_profile(row["id"]),
        }
    finally:
        conn.close()


def save_user_profile(user_id: int, profile: Dict[str, Any]):
    """Persists candidate's questionnaire answers into the profiles table."""
    conn = get_connection()
    try:
        with conn:
            conn.execute("""
                INSERT OR REPLACE INTO profiles (
                    user_id, name, grad_year, experience, location,
                    work_mode, open_to_relocate, career_goal,
                    current_skills_json, interests_json, updated_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP
                );
            """, (
                user_id,
                profile.get("name", ""),
                profile.get("grad_year", ""),
                profile.get("experience", ""),
                profile.get("location", ""),
                profile.get("work_mode", ""),
                profile.get("open_to_relocate", ""),
                profile.get("career_goal", ""),
                json.dumps(profile.get("current_skills", [])),
                json.dumps(profile.get("interests", []))
            ))
    finally:
        conn.close()


def get_user_profile(user_id: int) -> Optional[Dict[str, Any]]:
    """Loads a candidate's saved profile."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT name, grad_year, experience, location,
                   work_mode, open_to_relocate, career_goal,
                   current_skills_json, interests_json
            FROM profiles WHERE user_id = ?;
        """, (user_id,))
        row = cursor.fetchone()
        if not row:
            return None

        return {
            "name": row["name"],
            "grad_year": row["grad_year"],
            "experience": row["experience"],
            "location": row["location"],
            # Rows written before these questions existed hold NULL.
            "work_mode": row["work_mode"] or "",
            "open_to_relocate": row["open_to_relocate"] or "",
            "career_goal": row["career_goal"] or "",
            "current_skills": json.loads(row["current_skills_json"] or "[]"),
            "interests": json.loads(row["interests_json"] or "[]")
        }
    finally:
        conn.close()


def save_roadmap(user_id: int, role_id: str, role_title: str, roadmap: Dict[str, Any]):
    """Saves generated roadmap to user's history."""
    conn = get_connection()
    try:
        with conn:
            conn.execute("""
                INSERT INTO roadmaps (user_id, role_id, role_title, roadmap_json)
                VALUES (?, ?, ?, ?);
            """, (user_id, role_id, role_title, json.dumps(roadmap)))
    finally:
        conn.close()


def get_saved_roadmaps(user_id: int) -> List[Dict[str, Any]]:
    """Retrieves all past generated roadmaps for a user."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, role_id, role_title, roadmap_json, created_at
            FROM roadmaps WHERE user_id = ? ORDER BY created_at DESC;
        """, (user_id,))
        results = []
        for r in cursor.fetchall():
            results.append({
                "id": r["id"],
                "role_id": r["role_id"],
                "role_title": r["role_title"],
                "roadmap": json.loads(r["roadmap_json"]),
                "created_at": r["created_at"]
            })
        return results
    finally:
        conn.close()


def delete_saved_roadmap(roadmap_id: int, user_id: int):
    """Deletes a single saved roadmap, scoped to its owner."""
    conn = get_connection()
    try:
        with conn:
            conn.execute(
                "DELETE FROM roadmaps WHERE id = ? AND user_id = ?;",
                (roadmap_id, user_id)
            )
    finally:
        conn.close()
