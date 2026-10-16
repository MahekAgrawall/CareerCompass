import os
import json
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"), transport="rest")

MODEL_NAME = "gemini-flash-lite-latest"

def get_model(system_instruction=None):
    if system_instruction:
        return genai.GenerativeModel(MODEL_NAME, system_instruction=system_instruction)
    return genai.GenerativeModel(MODEL_NAME)


def generate_roadmap(user_profile: dict, role: dict) -> dict:
    """
    Sends user profile + selected role to Gemini.
    Returns a structured roadmap as a Python dictionary.
    """

    prompt = f"""
You are an expert career advisor for B.Tech CSE students and early-career professionals in India.

A student has selected a target role. Based on their current profile and the role requirements, 
generate a personalized, actionable skill roadmap.

## Student Profile:
- Name: {user_profile.get('name', 'the student')}
- Graduation Year: {user_profile.get('grad_year')}
- Experience Level: {user_profile.get('experience')}
- Current Skills (self-reported): {', '.join(user_profile.get('current_skills', []))}
- Interests: {', '.join(user_profile.get('interests', []))}
- Preferred Location: {user_profile.get('location')}

## Target Role: {role['title']}
- Must-Have Skills: {', '.join(role['skills']['must_have'])}
- Good-to-Have Skills: {', '.join(role['skills']['good_to_have'])}
- Can-Have Skills: {', '.join(role['skills']['can_have'])}

## Your Task:
Generate a personalized roadmap. Be specific and practical. 
- Do NOT recommend skills the student already knows well.
- Prioritize what will get them hired fastest.
- For each skill, suggest ONE specific free learning resource (YouTube channel, official docs, or free course).
- Keep language simple and encouraging.

Return your response as a valid JSON object with this exact structure:
{{
  "summary": "2-3 sentence personalized summary of the student's situation and what they need to focus on",
  "immediate_focus": [
    {{
      "skill": "skill name",
      "why": "one sentence on why this is critical for this role",
      "resource": "specific free resource (e.g., 'Official React docs at react.dev', 'CS50P on edX (free)', 'Traversy Media on YouTube')",
      "time_estimate": "e.g., 2-3 weeks"
    }}
  ],
  "next_level": [
    {{
      "skill": "skill name",
      "why": "one sentence",
      "resource": "specific free resource",
      "time_estimate": "e.g., 3-4 weeks"
    }}
  ],
  "good_to_explore": [
    {{
      "skill": "skill name",
      "why": "one sentence",
      "resource": "specific free resource"
    }}
  ],
  "projects": [
    {{
      "title": "project title",
      "description": "2-3 sentence description of what to build and why it demonstrates the skills needed for this role",
      "skills_demonstrated": ["skill1", "skill2", "skill3"],
      "difficulty": "Beginner / Intermediate / Advanced"
    }}
  ],
  "motivational_message": "One short, genuine, personalized encouraging message for this student."
}}

Return ONLY the JSON object. No explanation, no markdown, no extra text.
"""

    response = get_model().generate_content(
        prompt,
        generation_config=genai.GenerationConfig(
            response_mime_type="application/json",
            temperature=0.7,
        ),
    )

    raw_text = response.text.strip()
    if raw_text.startswith("```json"):
        raw_text = raw_text[7:]
    elif raw_text.startswith("```"):
        raw_text = raw_text[3:]
    if raw_text.endswith("```"):
        raw_text = raw_text[:-3]

    roadmap = json.loads(raw_text.strip())
    return roadmap


def generate_role_match_explanation(user_profile: dict, matched_roles: list) -> str:
    """
    Generates a short natural language explanation of why these roles match the user.
    """

    role_titles = [r["title"] for r in matched_roles[:5]]

    prompt = f"""
You are a friendly career advisor for B.Tech CSE students in India.

A student with these details just completed their profile:
- Experience: {user_profile.get('experience')}
- Current Skills: {', '.join(user_profile.get('current_skills', []))}
- Interests: {', '.join(user_profile.get('interests', []))}

Based on their profile, these roles were matched for them: {', '.join(role_titles)}

Write a SHORT (3-4 sentences), friendly, encouraging message explaining why these roles suit them.
Mention 1-2 specific skills or interests they have that make them a good fit.
Do not use bullet points. Write in plain conversational English.
"""

    try:
        response = get_model().generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        skills = ", ".join(user_profile.get("current_skills", [])[:3])
        return f"Based on your background in {skills} and your indicated interests, these roles align strongly with current high-demand engineering opportunities in the Indian tech market."


def send_chat_message(
    user_profile: dict,
    role: dict,
    roadmap: dict,
    new_message: str,
    chat_history: list,
) -> str:
    """
    Sends a message to Gemini in a context-aware chat session.

    The AI always knows:
      - Who the student is (profile)
      - Which role they chose
      - What their personalized roadmap contains

    chat_history: list of {"role": "user" | "model", "content": "..."} dicts
                  representing the conversation so far (EXCLUDING the new message).

    Returns the assistant's reply as a plain string.
    """

    # Build the system context that gets injected into every conversation.
    # This is what makes every answer personalized — the AI always "remembers"
    # exactly who it is talking to and what their roadmap says.
    system_context = f"""You are a friendly and knowledgeable personal career advisor.
You are helping {user_profile.get('name', 'a student')} navigate their career journey.
You already know everything about them — their profile, their chosen role, and their 
personalized roadmap. ALWAYS answer based on their specific context. Never give generic advice.

━━━━━━━━━━━ STUDENT PROFILE ━━━━━━━━━━━
Name            : {user_profile.get('name')}
Graduation Year : {user_profile.get('grad_year')}
Experience      : {user_profile.get('experience')}
Current Skills  : {', '.join(user_profile.get('current_skills', []))}
Interests       : {', '.join(user_profile.get('interests', []))}
Preferred City  : {user_profile.get('location')}

━━━━━━━━━━━ TARGET ROLE ━━━━━━━━━━━
Role        : {role['title']}
Description : {role['description']}
Must-Have   : {', '.join(role['skills']['must_have'])}

━━━━━━━━━━━ THEIR PERSONALIZED ROADMAP ━━━━━━━━━━━
Phase 1 – Immediate Focus : {', '.join([i['skill'] for i in roadmap.get('immediate_focus', [])])}
Phase 2 – Level Up        : {', '.join([i['skill'] for i in roadmap.get('next_level', [])])}
Phase 3 – Good to Explore : {', '.join([i['skill'] for i in roadmap.get('good_to_explore', [])])}

Recommended Projects:
{chr(10).join([f"  • {p['title']} ({p['difficulty']}): {p['description']}" for p in roadmap.get('projects', [])])}

━━━━━━━━━━━ HOW TO RESPOND ━━━━━━━━━━━
- Be concise, warm, and practical. No fluff.
- If they say they already know a skill in the roadmap, adjust your advice to skip it.
- If they ask how long something takes, give a realistic estimate based on their experience level.
- If they ask interview tips, tailor them to their specific role and current skill set.
- Use bullet points only when listing multiple things.
- End responses with a short encouraging line when appropriate.
"""

    # Build Gemini-compatible chat history from our stored messages
    gemini_history = []
    for msg in chat_history:
        gemini_history.append(
            {
                "role": msg["role"],       # "user" or "model"
                "parts": [msg["content"]],
            }
        )

    # Create a fresh chat model with system context baked in
    chat_model = get_model(system_instruction=system_context)

    # Resume the conversation from stored history, then send the new message
    chat_session = chat_model.start_chat(history=gemini_history)
    response = chat_session.send_message(new_message)
    return response.text.strip()
