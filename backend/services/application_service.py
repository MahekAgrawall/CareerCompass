"""
Saved jobs and application tracking.

The live postings feed (`services.job_feed`) is a stream a candidate passes
through; this module is what makes it something they come back to. A posting is
saved, and then moved along the stages of a real search — applied, interview,
offer — with the date of the last move and a free-text note.

Three deliberate choices, all of them about not losing the candidate's work:

* **A snapshot, not a reference.** The posting's own fields are copied into the
  row when it is saved. The boards rotate: a listing disappears when it is
  filled, the harvest is refreshed, and the `job_role` index is rebuilt from
  scratch on a re-ingest. A row holding only a `posting_id` would become a blank
  line at exactly the moment the candidate most needs to know what they applied
  to.
* **Saving twice is a no-op.** The insert conflicts on `(user_id, posting_id)`
  and does nothing, so pressing Save again on a card the candidate has already
  advanced cannot reset their stage. The row is read back after the write either
  way, so the client always sees the truth rather than assuming its own.
* **Every read and write is scoped to one `user_id`.** Looking up another
  candidate's row returns `None` rather than raising, so the router can answer
  "not found" and never has to reveal that the row exists at all.

The vocabulary of stages lives here, next to the column that stores it;
`app/schemas.py` mirrors it as a literal for the request body, and a test pins
the two together so they cannot drift.
"""

from typing import Any, Dict, List, Optional, Tuple

from database.db import get_connection

#: The stages a posting moves through, in order. Every row starts at `saved`
#: (the bookmark), then follows the search as far as it actually got. `rejected`
#: is a first-class stage rather than a deletion, because a tracker with no exit
#: for applications that went nowhere quietly fills up with dead rows in
#: `applied` and stops being trustworthy.
STATUSES = ("saved", "applied", "interview", "offer", "rejected")

_COLUMNS = (
    "id, posting_id, title, company, location, remote, employment_type, salary_text,"
    " published, url, source, status, note, created_at, updated_at"
)


def _row_to_dict(row) -> Dict[str, Any]:
    """One saved posting as the API returns it. SQLite stores the flag as 0/1."""
    return {
        "id": row["id"],
        "posting_id": row["posting_id"],
        "title": row["title"],
        "company": row["company"] or "",
        "location": row["location"] or "",
        "remote": bool(row["remote"]),
        "employment_type": row["employment_type"] or "",
        "salary_text": row["salary_text"] or "",
        "published": row["published"] or "",
        "url": row["url"] or "",
        "source": row["source"] or "",
        "status": row["status"],
        "note": row["note"] or "",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _fetch(conn, application_id: int, user_id: int):
    return conn.execute(
        f"SELECT {_COLUMNS} FROM saved_jobs WHERE id = ? AND user_id = ?;",
        (application_id, user_id),
    ).fetchone()


def save_application(user_id: int, posting: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    """Saves a posting for a candidate, or hands back the row already saved.

    `posting` is the snapshot body (`schemas.ApplicationCreate.model_dump()`),
    so its shape is validated at the edge rather than trusted here; the status is
    checked because a bad one would be written straight into the column.

    Returns `(row, created)` — `created` is False when the candidate had already
    saved this posting, which is what lets the endpoint answer 200 instead of
    201 without a second query.
    """
    status = posting.get("status") or "saved"
    if status not in STATUSES:
        raise ValueError(f"Unknown application status: {status!r}")

    conn = get_connection()
    try:
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO saved_jobs (
                    user_id, posting_id, title, company, location, remote,
                    employment_type, salary_text, published, url, source, status, note
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (user_id, posting_id) DO NOTHING;
                """,
                (
                    user_id,
                    posting["posting_id"],
                    posting["title"],
                    posting.get("company", ""),
                    posting.get("location", ""),
                    1 if posting.get("remote") else 0,
                    posting.get("employment_type", ""),
                    posting.get("salary_text", ""),
                    posting.get("published", ""),
                    posting.get("url", ""),
                    posting.get("source", ""),
                    status,
                    posting.get("note", ""),
                ),
            )
            created = cursor.rowcount > 0
        row = conn.execute(
            f"SELECT {_COLUMNS} FROM saved_jobs WHERE user_id = ? AND posting_id = ?;",
            (user_id, posting["posting_id"]),
        ).fetchone()
        return _row_to_dict(row), created
    finally:
        conn.close()


def list_applications(user_id: int) -> List[Dict[str, Any]]:
    """The candidate's saved postings, most recently *touched* first.

    Ordered by `updated_at` rather than `created_at` so a posting they just moved
    to "interview" rises to the top of the page, which is the row they came back
    to see.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            f"SELECT {_COLUMNS} FROM saved_jobs WHERE user_id = ?"
            " ORDER BY updated_at DESC, id DESC;",
            (user_id,),
        ).fetchall()
        return [_row_to_dict(row) for row in rows]
    finally:
        conn.close()


def update_application(
    user_id: int,
    application_id: int,
    status: Optional[str] = None,
    note: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Moves a saved posting along the stages, or edits its note.

    Only the fields actually given are written, so a stage change cannot wipe a
    note. Returns `None` when no row matched — which covers "no such row" and
    "someone else's row" alike, because a candidate has no business telling the
    two apart.
    """
    assignments, values = [], []
    if status is not None:
        if status not in STATUSES:
            raise ValueError(f"Unknown application status: {status!r}")
        assignments.append("status = ?")
        values.append(status)
    if note is not None:
        assignments.append("note = ?")
        values.append(note)
    if not assignments:
        raise ValueError("Nothing to update: give a status, a note, or both.")

    conn = get_connection()
    try:
        with conn:
            conn.execute(
                f"UPDATE saved_jobs SET {', '.join(assignments)},"
                " updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?;",
                (*values, application_id, user_id),
            )
        row = _fetch(conn, application_id, user_id)
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def delete_application(user_id: int, application_id: int) -> bool:
    """Forgets a saved posting. False when there was no such row for this user."""
    conn = get_connection()
    try:
        with conn:
            cursor = conn.execute(
                "DELETE FROM saved_jobs WHERE id = ? AND user_id = ?;",
                (application_id, user_id),
            )
        return cursor.rowcount > 0
    finally:
        conn.close()
