"""Shared test harness: isolation bootstrap plus small API helpers.

Importing this module runs three side effects *before* the application is loaded:

1. it puts the ``backend`` directory on ``sys.path`` and makes that the cwd;
2. it supplies a test-only ``JWT_SECRET`` (``app.config`` requires one and has no
   development fallback); and
3. it redirects persistence to a throwaway SQLite database in a temporary
   directory and creates its schema.

Because of (3) no test can ever read or mutate a developer's real
``backend/data/career_compass.db``. The temporary directory is deleted when the
test process exits.
"""
import atexit
import os
import shutil
import sys
import tempfile
import uuid
import warnings

warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.chdir(ROOT)

os.environ.setdefault("JWT_SECRET", "test-only-secret-" + "0" * 40)

import database.db as db  # noqa: E402

TMP_DIR = tempfile.mkdtemp(prefix="careercompass_tests_")
db.DB_PATH = os.path.join(TMP_DIR, "career_compass_test.db")
atexit.register(shutil.rmtree, TMP_DIR, True)

db.init_db()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def unique_email() -> str:
    """A fresh address, so tests never collide on the unique email constraint."""
    return f"test_{uuid.uuid4().hex[:10]}@example.com"


def signup(name: str = "Test User") -> dict:
    """Creates a fresh account and returns an Authorization header for it."""
    email = unique_email()
    r = client.post("/auth/signup", json={"name": name, "email": email, "password": "password123"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
