import os
import json
import hashlib

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
SESSION_FILE = os.path.join(DATA_DIR, "session.json")

def _init_storage():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)

def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def get_all_users() -> dict:
    _init_storage()
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_users(users: dict):
    _init_storage()
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2)

def signup_user(name: str, email: str, password: str) -> tuple[bool, str]:
    email = email.strip().lower()
    if not name or not email or not password:
        return False, "All fields are required."
    if len(password) < 4:
        return False, "Password must be at least 4 characters long."

    users = get_all_users()
    if email in users:
        return False, "An account with this email already exists."

    users[email] = {
        "name": name.strip(),
        "email": email,
        "password_hash": _hash_password(password),
        "profile": {},
        "saved_roadmaps": []
    }
    save_users(users)
    return True, "Account created successfully! You can now log in."

def authenticate_user(email: str, password: str) -> tuple[bool, dict | str]:
    email = email.strip().lower()
    users = get_all_users()
    if email not in users:
        return False, "No account found with this email."

    user = users[email]
    if user.get("password_hash") != _hash_password(password):
        return False, "Incorrect password."

    return True, user

def remember_session(user_email: str):
    _init_storage()
    try:
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump({"logged_in_email": user_email}, f)
    except Exception:
        pass

def clear_saved_session():
    _init_storage()
    if os.path.exists(SESSION_FILE):
        try:
            os.remove(SESSION_FILE)
        except Exception:
            pass

def get_remembered_session() -> dict | None:
    _init_storage()
    if not os.path.exists(SESSION_FILE):
        return None
    try:
        with open(SESSION_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            email = data.get("logged_in_email")
            if email:
                users = get_all_users()
                return users.get(email)
    except Exception:
        return None
    return None

def update_user_profile(email: str, profile_data: dict):
    users = get_all_users()
    if email in users:
        users[email]["profile"] = profile_data
        save_users(users)

def save_user_roadmap(email: str, role_title: str, roadmap: dict):
    users = get_all_users()
    if email in users:
        if "saved_roadmaps" not in users[email]:
            users[email]["saved_roadmaps"] = []
        users[email]["saved_roadmaps"].append({
            "role_title": role_title,
            "roadmap": roadmap
        })
        save_users(users)
