"""
AI Service for CareerCompass.
Interfaces with Google Gemini using optimized REST transport and structured schemas.
"""

import os
import json
from typing import Dict, Any, List
import google.generativeai as genai
from dotenv import load_dotenv

from app_logging import get_logger
from services import prompts, sanitize

load_dotenv()

log = get_logger("careercompass.ai")

# Initialize Gemini with REST transport for low latency
api_key = os.getenv("GEMINI_API_KEY", "")
if api_key:
    genai.configure(api_key=api_key, transport="rest")

# A floating alias by default: whatever "latest" means today. Pin it in the
# environment (GEMINI_MODEL) when reproducibility matters more than freshness, and
# note that every saved roadmap records the model it was generated with either way.
MODEL_NAME = os.getenv("GEMINI_MODEL", "").strip() or "gemini-flash-lite-latest"

#: The templates behind `generate_roadmap`, hashed onto every saved roadmap.
ROADMAP_PROMPT_TEMPLATES = ("system/roadmap.md", "user/roadmap.md")


class AIConfigurationError(RuntimeError):
    """Raised when the Gemini API key is missing or misconfigured."""


def is_configured() -> bool:
    """True when a Gemini API key is available to the app."""
    return bool(api_key)


def _ensure_configured():
    """Fails fast with a friendly, actionable message when no key is set."""
    if not api_key:
        raise AIConfigurationError(
            "No Gemini API key found. Copy .env.example to .env, paste your free key "
            "from https://aistudio.google.com, then restart the app."
        )


def get_model(system_instruction: str = None) -> genai.GenerativeModel:
    """Returns a configured Gemini GenerativeModel instance."""
    _ensure_configured()
    if system_instruction:
        return genai.GenerativeModel(MODEL_NAME, system_instruction=system_instruction)
    return genai.GenerativeModel(MODEL_NAME)


def roadmap_prompt_version() -> str:
    """Fingerprint of the roadmap prompt pair, stored beside every saved plan."""
    return prompts.fingerprint(*ROADMAP_PROMPT_TEMPLATES)


_ROADMAP_LIST_FIELDS = ("immediate_focus", "next_level", "good_to_explore", "projects")


def _extract_json(raw_text: str) -> Dict[str, Any]:
    """Pulls the first JSON object out of a model response, tolerating code fences."""
    text = (raw_text or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.strip().rstrip("`").strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("No JSON object found in the model response.")
    return json.loads(text[start:end + 1])


def _validate_roadmap(data: Any) -> None:
    """Ensures the parsed roadmap contains the fields the UI renders."""
    if not isinstance(data, dict):
        raise ValueError("Roadmap response was not a JSON object.")
    for field in _ROADMAP_LIST_FIELDS:
        if not isinstance(data.get(field), list):
            raise ValueError(f"Roadmap field '{field}' is missing or not a list.")


def generate_roadmap(user_profile: Dict[str, Any], role: Dict[str, Any]) -> Dict[str, Any]:
    """Generates a personalized, structured 3-phase skill roadmap and portfolio projects."""
    # Wording lives in prompts/system/roadmap.md + prompts/user/roadmap.md. The two
    # halves are joined into one message here to keep the model call identical to
    # the inline prompt this replaced. The profile arrives from the browser, so it
    # is scrubbed down to single-line values and plain labels first.
    prompt = "\n\n".join(
        (
            prompts.render("system/roadmap.md"),
            prompts.render(
                "user/roadmap.md",
                name=sanitize.single_line(user_profile.get("name"), 80) or "Candidate",
                grad_year=sanitize.single_line(user_profile.get("grad_year"), 40) or "Upcoming",
                experience=sanitize.single_line(user_profile.get("experience"), 60) or "Fresher",
                current_skills=", ".join(sanitize.labels(user_profile.get("current_skills"))) or "None stated",
                interests=", ".join(sanitize.labels(user_profile.get("interests"))) or "Still exploring",
                location=sanitize.single_line(user_profile.get("location"), 60) or "India",
                role_title=role["title"],
                role_category=role["category"],
                must_have=", ".join(role["skills"]["must_have"]),
                good_to_have=", ".join(role["skills"]["good_to_have"]),
            ),
        )
    )

    last_error = None
    for attempt in range(2):
        response = get_model().generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.7 if attempt == 0 else 0.2,
            ),
        )
        try:
            data = _extract_json(response.text)
            _validate_roadmap(data)
            return data
        except (json.JSONDecodeError, ValueError) as e:
            last_error = e

    raise RuntimeError(
        "The AI returned a roadmap in an unexpected format. Please try generating again."
    ) from last_error


def generate_role_match_explanation(user_profile: Dict[str, Any], matched_roles: List[Dict[str, Any]]) -> str:
    """Explains why the matched roles fit the candidate's stated interests and skills."""
    role_titles = [r["title"] for r in matched_roles[:4]]

    prompt = "\n\n".join(
        (
            prompts.render("system/match_explanation.md"),
            prompts.render(
                "user/match_explanation.md",
                skills=", ".join(sanitize.labels(user_profile.get("current_skills"))) or "none stated",
                interests=", ".join(sanitize.labels(user_profile.get("interests"))) or "none stated",
                role_titles=", ".join(role_titles),
            ),
        )
    )

    try:
        response = get_model().generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        log.warning("Role match explanation failed, falling back to template: %s", e)
        skills = ", ".join(sanitize.labels(user_profile.get("current_skills"), limit=3)) or "your current skills"
        return f"Based on your foundation in {skills} and your indicated interests, these roles align strongly with high-growth engineering opportunities in the Indian market."


def _chat_system_context(
    user_profile: Dict[str, Any],
    role: Dict[str, Any],
    roadmap: Dict[str, Any],
) -> str:
    """Builds the persona/context block injected into every copilot turn.

    Everything here is echoed back from the caller's browser, and it lands in a
    *system* instruction — the strongest position in the prompt. It is therefore
    reduced to plain labels first: the roadmap is expected to be the shape the app
    generated, but nothing about it is trusted, so a malformed or crafted roadmap
    can neither break the call nor smuggle in instructions.
    """
    focus = roadmap.get("immediate_focus")
    focus_items = focus if isinstance(focus, list) else []
    priority_skills = ", ".join(
        sanitize.labels([item.get("skill") for item in focus_items if isinstance(item, dict)])
    )
    return prompts.render(
        "system/copilot.md",
        name=sanitize.single_line(user_profile.get("name"), 80) or "a candidate",
        experience=sanitize.single_line(user_profile.get("experience"), 60) or "not stated",
        current_skills=", ".join(sanitize.labels(user_profile.get("current_skills"))) or "none stated",
        role_title=role["title"],
        priority_skills=priority_skills or "not stated",
    )


def _chat_history(chat_history: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """The history as the SDK wants it, with malformed or spoofed turns dropped."""
    return [{"role": m["role"], "parts": [m["content"]]} for m in sanitize.chat_history(chat_history)]


def send_chat_message(
    user_profile: Dict[str, Any],
    role: Dict[str, Any],
    roadmap: Dict[str, Any],
    new_message: str,
    chat_history: List[Dict[str, str]],
) -> str:
    """Multi-turn context-aware roadmap copilot conversation (non-streaming)."""
    chat_model = get_model(system_instruction=_chat_system_context(user_profile, role, roadmap))
    session = chat_model.start_chat(history=_chat_history(chat_history))
    response = session.send_message(sanitize.message(new_message))
    return response.text.strip()


def stream_chat_message(
    user_profile: Dict[str, Any],
    role: Dict[str, Any],
    roadmap: Dict[str, Any],
    new_message: str,
    chat_history: List[Dict[str, str]],
):
    """Yields the copilot reply incrementally for a live-typing experience."""
    chat_model = get_model(system_instruction=_chat_system_context(user_profile, role, roadmap))
    session = chat_model.start_chat(history=_chat_history(chat_history))
    for chunk in session.send_message(sanitize.message(new_message), stream=True):
        text = getattr(chunk, "text", None)
        if text:
            yield text
