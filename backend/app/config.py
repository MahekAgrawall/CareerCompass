"""Application settings loaded from environment variables."""
import os

from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# JWT_SECRET is REQUIRED: there is deliberately no development fallback, so a
# misconfigured deployment fails loudly at startup instead of silently signing
# tokens with a publicly known key.
_INSECURE_JWT_SECRETS = {
    "dev-insecure-change-me",
    "change_this_to_a_long_random_string",
    "some_long_random_string",
    "replace_me",
    "change-me",
    "changeme",
    "secret",
    "your-secret-key",
}

JWT_SECRET = os.getenv("JWT_SECRET", "").strip()
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))

if len(JWT_SECRET) < 32 or JWT_SECRET.lower() in _INSECURE_JWT_SECRETS:
    raise RuntimeError(
        "JWT_SECRET is missing or insecure (minimum 32 characters, no known "
        "placeholders). Set a long, random value in the environment or backend/.env.\n"
        'Generate one with:  python -c "import secrets; print(secrets.token_urlsafe(48))"'
    )

CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]

# The AI endpoints (roadmap, copilot, match explanation) spend a paid quota and
# are open to guests, so each caller gets its own budget per rolling window. Keyed
# by user id when a bearer token resolves, otherwise by client address. Sized well
# above human use: generating plans and chatting rarely exceeds a handful a minute.
AI_RATE_LIMIT = int(os.getenv("AI_RATE_LIMIT", "15"))
AI_RATE_WINDOW_SECONDS = float(os.getenv("AI_RATE_WINDOW_SECONDS", "60"))

API_TITLE = "CareerCompass API"
API_VERSION = "1.0.0"
