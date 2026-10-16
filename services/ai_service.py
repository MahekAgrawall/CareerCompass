"""
AI Service for CareerCompass.
Interfaces with Google Gemini using optimized REST transport and structured schemas.
"""

import os
import json
from typing import Dict, Any, List
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

# Initialize Gemini with REST transport for low latency
api_key = os.getenv("GEMINI_API_KEY", "")
if api_key:
    genai.configure(api_key=api_key, transport="rest")

MODEL_NAME = "gemini-flash-lite-latest"


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
    prompt = f"""
You are an expert technical career advisor for engineering and CS students in India.

A candidate has chosen a target role. Based on their baseline profile and the role requirements,
generate an actionable, personalized skill roadmap.

## Candidate Profile:
- Name: {user_profile.get('name', 'Candidate')}
- Graduation Year: {user_profile.get('grad_year', 'Upcoming')}
- Experience: {user_profile.get('experience', 'Fresher')}
- Current Skills: {', '.join(user_profile.get('current_skills', []))}
- Stated Interests: {', '.join(user_profile.get('interests', []))}
- Target Location: {user_profile.get('location', 'India')}

## Target Role: {role['title']}
- Category: {role['category']}
- Must-Have Skills: {', '.join(role['skills']['must_have'])}
- Good-to-Have Skills: {', '.join(role['skills']['good_to_have'])}

## Rules:
- Do NOT re-teach fundamentals the student already listed in current skills.
- Focus on skills that accelerate interview readiness in the Indian tech market.
- Provide ONE authoritative free learning resource for every skill.

Return your response strictly as a JSON object matching this schema:
{{
  "summary": "2-3 sentence personalized strategic advice for this student",
  "immediate_focus": [
    {{
      "skill": "skill name",
      "why": "concise explanation of why this is high leverage",
      "resource": "Specific free resource (e.g. 'Official docs', 'YouTube channel')",
      "time_estimate": "e.g., 2 weeks"
    }}
  ],
  "next_level": [
    {{
      "skill": "skill name",
      "why": "concise explanation",
      "resource": "Specific free resource",
      "time_estimate": "e.g., 3 weeks"
    }}
  ],
  "good_to_explore": [
    {{
      "skill": "skill name",
      "why": "concise explanation",
      "resource": "Specific free resource"
    }}
  ],
  "projects": [
    {{
      "title": "Project Title",
      "description": "2 sentence overview of what to build and why it proves competency",
      "skills_demonstrated": ["skill1", "skill2"],
      "difficulty": "Beginner / Intermediate / Advanced"
    }}
  ],
  "motivational_message": "One encouraging, authentic message for this candidate."
}}
"""

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

    prompt = f"""
You are a friendly technical career advisor in India.
A candidate with:
- Skills: {', '.join(user_profile.get('current_skills', []))}
- Core Interests: {', '.join(user_profile.get('interests', []))}

Was matched with these specific roles: {', '.join(role_titles)}

Write a concise (3-4 sentences), encouraging, professional statement explaining why these roles align with their indicated interests.
Do not use bullet points. Write in conversational, polished prose.
"""

    try:
        response = get_model().generate_content(prompt)
        return response.text.strip()
    except Exception:
        skills = ", ".join(user_profile.get("current_skills", [])[:3])
        return f"Based on your foundation in {skills} and your indicated interests, these roles align strongly with high-growth engineering opportunities in the Indian market."


def _chat_system_context(
    user_profile: Dict[str, Any],
    role: Dict[str, Any],
    roadmap: Dict[str, Any],
) -> str:
    """Builds the persona/context block injected into every copilot turn."""
    priority_skills = ", ".join(i["skill"] for i in roadmap.get("immediate_focus", []))
    return f"""You are CareerCompass Copilot, a senior engineering mentor.
You are helping {user_profile.get('name', 'a candidate')} navigate their learning roadmap for {role['title']}.

Candidate Context:
- Experience: {user_profile.get('experience')}
- Existing Skills: {', '.join(user_profile.get('current_skills', []))}
- Target Role: {role['title']}
- Priority Skills in Roadmap: {priority_skills}

Guidelines:
- Give concise, highly practical, actionable advice.
- When asked for daily study plans, break down the roadmap realistically.
- Provide direct answers without filler.
"""


def send_chat_message(
    user_profile: Dict[str, Any],
    role: Dict[str, Any],
    roadmap: Dict[str, Any],
    new_message: str,
    chat_history: List[Dict[str, str]],
) -> str:
    """Multi-turn context-aware roadmap copilot conversation (non-streaming)."""
    history = [{"role": m["role"], "parts": [m["content"]]} for m in chat_history]
    chat_model = get_model(system_instruction=_chat_system_context(user_profile, role, roadmap))
    session = chat_model.start_chat(history=history)
    response = session.send_message(new_message)
    return response.text.strip()


def stream_chat_message(
    user_profile: Dict[str, Any],
    role: Dict[str, Any],
    roadmap: Dict[str, Any],
    new_message: str,
    chat_history: List[Dict[str, str]],
):
    """Yields the copilot reply incrementally for a live-typing experience."""
    history = [{"role": m["role"], "parts": [m["content"]]} for m in chat_history]
    chat_model = get_model(system_instruction=_chat_system_context(user_profile, role, roadmap))
    session = chat_model.start_chat(history=history)
    for chunk in session.send_message(new_message, stream=True):
        text = getattr(chunk, "text", None)
        if text:
            yield text
