# 🧭 CareerCompass

> AI-powered career guidance for B.Tech CSE students and early-career professionals in India.

---

## What is CareerCompass?

CareerCompass helps B.Tech CSE students and freshers figure out **which tech career path suits them best** — and exactly **what to learn to get there**.

### How it works:
1. **Tell us about yourself** — your skills, interests, experience, and preferred location
2. **Explore matching roles** — see 15+ curated tech roles ranked for your profile
3. **Compare roles** — salary ranges, responsibilities, growth paths (India-specific)
4. **Get your AI skill roadmap** — Gemini generates a personalized learning plan with free resources and project ideas

---

## Features

- 🎯 **Smart role matching** — roles ranked by how well they fit your skills and interests
- 💰 **India salary data** — ranges sourced from Glassdoor, AmbitionBox, LinkedIn (2024–25)
- 🤖 **AI-powered roadmaps** — Google Gemini generates a personalized, step-by-step skill roadmap
- 🛠️ **Project recommendations** — 3 hands-on projects to build for your chosen role
- ⚖️ **Role comparison** — compare up to 3 roles side by side
- 🆓 **Completely free** — uses Gemini 1.5 Flash free tier

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.x |
| UI Framework | Streamlit |
| AI Model | Google Gemini 1.5 Flash |
| AI SDK | google-generativeai |
| Data | Curated JSON (15 roles) |
| Deployment | Streamlit Community Cloud |

---

## Setup & Run Locally

### 1. Clone the repository
```bash
git clone https://github.com/YOUR_USERNAME/career-compass.git
cd career-compass
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Get your free Gemini API key
- Go to [aistudio.google.com](https://aistudio.google.com)
- Sign in with Google → Click **Get API Key** → **Create API Key**
- Copy the key

### 4. Set up your API key
```bash
# Create a .env file
cp .env.example .env
# Open .env and replace 'your_api_key_here' with your actual key
```

### 5. Run the app
```bash
streamlit run app.py
```

Open your browser at `http://localhost:8501`

---

## Project Structure

```
career-compass/
│
├── app.py                  ← Main Streamlit app (6 pages)
├── gemini_client.py        ← Gemini API integration
├── data/
│   └── roles.json          ← 15 curated roles with salary, skills, growth paths
├── .env.example            ← Template for API key
├── requirements.txt
└── README.md
```

---

## Roles Covered

| Category | Roles |
|---|---|
| Development | Backend Dev, Frontend Dev, Full Stack Dev, Android Dev |
| AI / ML | AI/GenAI Engineer, ML Engineer, Data Scientist |
| Data & Analytics | Data Analyst |
| Infrastructure | Cloud Engineer, DevOps Engineer |
| Business | Business Analyst, Associate Product Manager, Tech Consultant |
| Quality | QA / Test Engineer |
| Security | Cybersecurity Analyst |

---

## AI Integration Details

- **Role match explanation** — Gemini analyzes your profile and explains why certain roles suit you, in natural language
- **Personalized roadmap** — Gemini generates a 3-phase skill roadmap (Immediate → Level Up → Explore) tailored to your existing skills
- **Structured output** — Uses `response_mime_type="application/json"` for reliable, parseable AI responses
- **Project ideas** — Gemini recommends 3 hands-on projects specific to your chosen role

---

## License

MIT License — free to use, modify, and share.
