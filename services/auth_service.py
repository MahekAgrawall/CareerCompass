"""
Authentication & User Persistence Service for CareerCompass.
Handles credentials, user session persistence, profiles, and saved roadmaps.
"""

import hashlib
import json
import uuid
from typing import Optional, Dict, Any, Tuple, List
from database.db import get_connection


def _hash_password(password: str) -> str:
    """Hashes passwords securely with SHA-256."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def signup_user(name: str, email: str, password: str) -> Tuple[bool, str]:
    """Registers a new user in the database."""
    name = name.strip()
    email = email.strip().lower()

    if not name or not email or not password:
        return False, "All fields are required."
    if len(password) < 4:
        return False, "Password must be at least 4 characters."

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

        if row["password_hash"] != _hash_password(password):
            return False, "Incorrect password."

        user_data = {
            "id": row["id"],
            "name": row["name"],
            "email": row["email"],
            "profile": get_user_profile(row["id"])
        }
        return True, user_data
    finally:
        conn.close()


def remember_session(email: str):
    """Saves session token in SQLite to remember user across restarts."""
    conn = get_connection()
    try:
        with conn:
            conn.execute("DELETE FROM user_sessions;")
            token = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO user_sessions (session_token, user_email) VALUES (?, ?);",
                (token, email.strip().lower())
            )
    finally:
        conn.close()


def clear_saved_session():
    """Removes stored session token upon logout."""
    conn = get_connection()
    try:
        with conn:
            conn.execute("DELETE FROM user_sessions;")
    finally:
        conn.close()


def get_remembered_session() -> Optional[Dict[str, Any]]:
    """Retrieves the remembered user session if present."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT user_email FROM user_sessions ORDER BY created_at DESC LIMIT 1;")
        row = cursor.fetchone()
        if not row:
            return None

        email = row["user_email"]
        cursor.execute("SELECT id, name, email FROM users WHERE email = ?;", (email,))
        u = cursor.fetchone()
        if not u:
            return None

        return {
            "id": u["id"],
            "name": u["name"],
            "email": u["email"],
            "profile": get_user_profile(u["id"])
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
                    current_skills_json, interests_json, updated_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP
                );
            """, (
                user_id,
                profile.get("name", ""),
                profile.get("grad_year", ""),
                profile.get("experience", ""),
                profile.get("location", ""),
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
            SELECT name, grad_year, experience, location, current_skills_json, interests_json
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
