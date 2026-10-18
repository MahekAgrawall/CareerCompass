"""
AI Service for CareerCompass.
Interfaces with Google Gemini using optimized REST transport and structured schemas.
"""

import os
import json
from typing import Dict, Any, List, Optional
import google.generativeai as genai
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError, field_validator

from app_logging import get_logger
from config import CANONICAL_ROLES, OTHER_CATEGORY, ROLE_CATEGORY_OF, UNCLASSIFIED_ROLE
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

#: The templates behind `classify_listing`, hashed onto every stored classification
#: for the same reason: a verdict is only reproducible alongside the wording that
#: produced it.
LISTING_CLASSIFY_TEMPLATES = ("system/classify_listing.md", "user/classify_listing.md")


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


# ── Listing classification ────────────────────────────────────────────────────
class ListingClassificationError(RuntimeError):
    """The model answered, but not with something readable as a classification.

    Deliberately not an HTTP error: a listing whose advert cannot be classified is
    still a listing, so the pipeline reports it as Unclassified instead of failing
    a page over it. A missing API key is a different thing entirely and keeps
    raising `AIConfigurationError`.
    """


class MinimumExperienceAnswer(BaseModel):
    """What the advert says about how much experience it wants.

    `years` is a number only where the advert states one; `as_written` carries the
    advert's own phrasing ("3+ years", "fresher to 2 years") so a card can quote it
    instead of showing a precision nobody published.
    """

    years: Optional[float] = None
    as_written: str = ""

    @field_validator("years", mode="before")
    @classmethod
    def _only_a_stated_number(cls, value):
        """A phrasing where a number was asked for is not an error — it is null.

        "3+ years" is a *phrase* and the schema offers `as_written` for it, so a
        model that puts it in `years` anyway loses the number and nothing else. A
        range ("2-4 years") lands the same way rather than being read as one end of
        it, which would be this pipeline inventing a figure.
        """
        try:
            return None if value in (None, "") else float(value)
        except (TypeError, ValueError):
            return None

    @field_validator("as_written", mode="before")
    @classmethod
    def _text(cls, value):
        return value if isinstance(value, str) else ""


class ListingAnswer(BaseModel):
    """The answer `classify_listing` must get back, field for field.

    The schema in `system/classify_listing.md` and this model are the same contract
    written twice, and `tests/test_prompts.py` pins the two together so neither can
    drift.

    Lenient about *shape* — a bare string where a list was wanted, an experience
    figure as text — because that is a formatting slip, not a wrong answer. Strict
    about *content*, which is where a wrong answer can actually mislead someone: the
    role name is checked against the declared vocabulary in `_parse_listing_answer`.

    Every field defaults, so a partial answer is validated rather than thrown away:
    what the model did say is kept, and `services/classification.py` decides whether
    what it left out makes the verdict Unclassified.
    """

    primary_category: str = ""
    canonical_role: str = ""
    original_title: str = ""
    related_role_titles: List[str] = []
    required_skills: List[str] = []
    preferred_skills: List[str] = []
    minimum_experience: MinimumExperienceAnswer = Field(
        default_factory=MinimumExperienceAnswer
    )
    seniority_level: str = ""
    work_arrangement: str = ""
    classification_confidence: float = 0.0
    short_match_explanation: str = ""

    @field_validator(
        "related_role_titles", "required_skills", "preferred_skills", mode="before"
    )
    @classmethod
    def _one_label_is_still_a_list(cls, value):
        if isinstance(value, str):
            return [value] if value.strip() else []
        return value if isinstance(value, list) else []

    @field_validator("minimum_experience", mode="before")
    @classmethod
    def _experience_is_an_object(cls, value):
        """A bare number or phrase reads as the one field it could have meant."""
        if value is None:
            return {}
        if isinstance(value, (int, float)):
            return {"years": value}
        if isinstance(value, str):
            return {"as_written": value}
        return value

    @field_validator(
        "primary_category", "canonical_role", "original_title", mode="before"
    )
    @classmethod
    def _is_text(cls, value):
        return value if isinstance(value, str) else ""

    @field_validator("classification_confidence", mode="before")
    @classmethod
    def _confidence_is_a_number(cls, value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def resolved_role(self) -> Optional[str]:
        """The declared family this answer names, or None when it named none.

        Matching ignores case and padding, so "site reliability engineering" is the
        declared family rather than an invented role, while a genuinely unknown name
        ("Quantum SRE") stays unknown and is treated as an unreadable answer.
        """
        wanted = sanitize.single_line(self.canonical_role, 120).casefold()
        if not wanted:
            return None
        if wanted == UNCLASSIFIED_ROLE.casefold():
            return UNCLASSIFIED_ROLE
        for role in ROLE_CATEGORY_OF:
            if role.casefold() == wanted:
                return role
        return None

    @property
    def role_is_known(self) -> bool:
        """True when the answer named a declared family, or honestly said Unclassified."""
        return self.resolved_role() is not None


def classify_prompt_version() -> str:
    """Fingerprint of the classification prompt pair, stored beside every verdict."""
    return prompts.fingerprint(*LISTING_CLASSIFY_TEMPLATES)


def classification_vocabulary() -> str:
    """The declared vocabulary, written out for the prompt — one line per category.

    Rendered from `config.CANONICAL_ROLES` rather than typed into the template, so
    the list the model chooses from and the list the validator accepts are the same
    list by construction. A vocabulary that could drift from its own validator would
    make a valid answer look invalid, or worse, let an undeclared role be stored.

    The Unclassified line is spelled out with the category it pairs with, because
    "say you cannot tell" has to be as concrete an option as any family — otherwise
    the cheapest way to satisfy the schema is to guess a family.
    """
    lines = [
        f"- {category}: {', '.join(roles)}"
        for category, roles in CANONICAL_ROLES.items()
    ]
    lines.append(
        f"- {OTHER_CATEGORY}: {UNCLASSIFIED_ROLE}, with no skills and low confidence — "
        "only when the advert does not say enough to place it, or describes a job "
        "outside every family above"
    )
    return "\n".join(lines)


def classify_listing(values: Dict[str, str]) -> ListingAnswer:
    """Classifies one advert into the declared vocabulary, or says it cannot.

    `values` is already-scrubbed advert text (`services/classification.py` builds
    it), so no untrusted value is ever interpolated into the *system* half of the
    prompt — the advert travels only inside the user half, and the system half says
    that it is data rather than instructions.

    Two attempts, both at a low temperature. The retry exists for an answer that
    could not be read at all; a second, *different* answer is never fished for,
    because a confident wrong answer is a prompting problem, not a sampling one, and
    re-rolling for a friendlier verdict is how a classifier starts lying.

    Raises `ListingClassificationError` when neither attempt was readable, and
    `AIConfigurationError` when there is no key — the API reports that as its own
    problem, never as something about the advert.
    """
    prompt = "\n\n".join(
        (
            prompts.render(
                "system/classify_listing.md",
                canonical_roles=classification_vocabulary(),
            ),
            prompts.render("user/classify_listing.md", **values),
        )
    )

    last_error = None
    for temperature in (0.1, 0.0):
        response = get_model().generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                temperature=temperature,
            ),
        )
        try:
            return _parse_listing_answer(response.text)
        except (ValidationError, ValueError) as e:
            last_error = e

    raise ListingClassificationError(
        f"The AI returned something that is not a listing classification ({last_error})."
    ) from last_error


def _parse_listing_answer(raw_text: str) -> ListingAnswer:
    """The model's text as a validated answer, or a `ValueError` worth re-asking.

    The vocabulary check lives here rather than in the pipeline because it is the
    line between "the model answered" and "the model answered with something we
    cannot use". An invented role name is re-asked once and then reported as
    unclassifiable — it is never stored as a role of its own.
    """
    answer = ListingAnswer.model_validate(_extract_json(raw_text))
    if not answer.role_is_known:
        raise ValueError(
            f"the answer named no declared role (canonical_role={answer.canonical_role!r})"
        )
    return answer


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
