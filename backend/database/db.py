"""
Database Connection & Schema Management for CareerCompass.
Uses SQLite for zero-config, embedded, relational persistence.
"""

import os
import sqlite3
import json
from typing import Optional, List, Dict, Any

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DB_PATH = os.path.join(DATA_DIR, "career_compass.db")
ROLES_JSON_PATH = os.path.join(DATA_DIR, "roles.json")


def get_connection() -> sqlite3.Connection:
    """Creates and returns a connection with foreign keys enabled and row factories set."""
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initializes all database tables and seeds roles data if empty."""
    conn = get_connection()
    with conn:
        # 1. Users Table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        conn.execute("""
            INSERT OR IGNORE INTO users (id, name, email, password_hash)
            VALUES (0, 'Guest Candidate', 'guest@careercompass.local', 'none');
        """)

        # 2. Profiles Table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS profiles (
                user_id INTEGER PRIMARY KEY,
                name TEXT,
                grad_year TEXT,
                experience TEXT,
                location TEXT,
                work_mode TEXT,
                open_to_relocate TEXT,
                career_goal TEXT,
                current_skills_json TEXT,
                interests_json TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            );
        """)

        # 3. Roles Table (Persisted in DB instead of hardcoded)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS roles (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                icon TEXT NOT NULL,
                market_demand TEXT,
                competition_level TEXT,
                future_relevance TEXT,
                is_niche INTEGER DEFAULT 0,
                niche_category TEXT,
                description TEXT,
                responsibilities_json TEXT,
                qualifications_json TEXT,
                growth_path_json TEXT,
                salary_fresher_min REAL,
                salary_fresher_max REAL,
                salary_mid_min REAL,
                salary_mid_max REAL,
                salary_senior_min REAL,
                salary_senior_max REAL,
                top_companies_json TEXT,
                skills_must_have_json TEXT,
                skills_good_to_have_json TEXT,
                skills_can_have_json TEXT,
                matching_interests_json TEXT,
                matching_skills_json TEXT
            );
        """)

        # 4. Saved Roadmaps Table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS roadmaps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                role_id TEXT NOT NULL,
                role_title TEXT NOT NULL,
                roadmap_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
                FOREIGN KEY (role_id) REFERENCES roles (id) ON DELETE CASCADE
            );
        """)

        # 5. Study Schedule / Tracker Table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS study_schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                role_id TEXT NOT NULL,
                weekday_hours REAL NOT NULL,
                weekend_hours REAL NOT NULL,
                weekly_total_hours REAL NOT NULL,
                target_languages_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, role_id),
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
                FOREIGN KEY (role_id) REFERENCES roles (id) ON DELETE CASCADE
            );
        """)

        # 6. Tracker Topics & Subtopics Checklist
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tracker_topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                role_id TEXT NOT NULL,
                category TEXT NOT NULL,
                topic_name TEXT NOT NULL,
                subtopics_json TEXT NOT NULL,
                estimated_hours REAL DEFAULT 4.0,
                is_completed INTEGER DEFAULT 0,
                completed_at TIMESTAMP,
                sort_order INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
                FOREIGN KEY (role_id) REFERENCES roles (id) ON DELETE CASCADE
            );
        """)

        # 7. Upgrade databases created before the questionnaire grew: existing
        # rows are kept and the new columns are appended in place.
        _add_missing_columns(conn, "profiles", {
            "work_mode": "TEXT",
            "open_to_relocate": "TEXT",
            "career_goal": "TEXT",
        })

    # Seed roles into SQLite if table is empty
    _seed_roles_if_empty(conn)
    conn.close()


def _add_missing_columns(conn: sqlite3.Connection, table: str, columns: Dict[str, str]):
    """Appends columns that were introduced after a table was first created.

    SQLite has no migration tooling, so `CREATE TABLE IF NOT EXISTS` leaves older
    databases untouched; this brings them up to date without losing any rows.
    """
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table});")}
    for name, declaration in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration};")


def _seed_roles_if_empty(conn: sqlite3.Connection):
    """Loads roles from roles.json into the SQLite database on first startup."""
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM roles;")
    count = cursor.fetchone()[0]

    if count > 0:
        return

    if not os.path.exists(ROLES_JSON_PATH):
        return

    with open(ROLES_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
        roles_list = data.get("roles", [])

    with conn:
        for r in roles_list:
            sal = r.get("salary", {})
            fresher = sal.get("fresher_0_1", {"min": 4.0, "max": 9.0})
            mid = sal.get("mid_1_3", {"min": 9.0, "max": 18.0})
            senior = sal.get("senior_3_plus", {"min": 18.0, "max": 40.0})

            conn.execute("""
                INSERT OR REPLACE INTO roles (
                    id, title, category, icon, market_demand, competition_level,
                    future_relevance, is_niche, niche_category, description,
                    responsibilities_json, qualifications_json, growth_path_json,
                    salary_fresher_min, salary_fresher_max,
                    salary_mid_min, salary_mid_max,
                    salary_senior_min, salary_senior_max,
                    top_companies_json, skills_must_have_json, skills_good_to_have_json,
                    skills_can_have_json, matching_interests_json, matching_skills_json
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                );
            """, (
                r["id"],
                r["title"],
                r.get("category", "Development"),
                r.get("icon", "💼"),
                r.get("market_demand", "High"),
                r.get("competition_level", "Moderate"),
                r.get("future_relevance", "High"),
                1 if r.get("is_niche") else 0,
                r.get("niche_category", "Core"),
                r.get("description", ""),
                json.dumps(r.get("responsibilities", [])),
                json.dumps(r.get("qualifications", [])),
                json.dumps(r.get("growth_path", [])),
                float(fresher.get("min", 4.0)),
                float(fresher.get("max", 9.0)),
                float(mid.get("min", 9.0)),
                float(mid.get("max", 18.0)),
                float(senior.get("min", 18.0)),
                float(senior.get("max", 40.0)),
                json.dumps(r.get("top_companies", [])),
                json.dumps(r.get("skills", {}).get("must_have", [])),
                json.dumps(r.get("skills", {}).get("good_to_have", [])),
                json.dumps(r.get("skills", {}).get("can_have", [])),
                json.dumps(r.get("matching_interests", [])),
                json.dumps(r.get("matching_skills", []))
            ))
