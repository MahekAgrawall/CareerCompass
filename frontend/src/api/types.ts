/**
 * TypeScript mirrors of the FastAPI Pydantic schemas and service payloads.
 * Keep these in sync with `backend/app/schemas.py` and `backend/services/*`.
 */

// ── Auth ──────────────────────────────────────────────────────────────────────
export interface User {
  id: number;
  name: string;
  email: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface MeResponse extends User {
  profile: Partial<Profile> | Record<string, never>;
}

// ── Profile ───────────────────────────────────────────────────────────────────
export interface Profile {
  name: string;
  grad_year: string;
  experience: string;
  location: string;
  current_skills: string[];
  interests: string[];
}

// ── Roles ─────────────────────────────────────────────────────────────────────
export interface SalaryBand {
  min: number;
  max: number;
  label: string;
}

export interface RoleSalary {
  fresher_0_1: SalaryBand;
  mid_1_3: SalaryBand;
  senior_3_plus: SalaryBand;
}

export interface RoleSkills {
  must_have: string[];
  good_to_have: string[];
  can_have: string[];
}

export interface Role {
  id: string;
  title: string;
  category: string;
  icon: string;
  market_demand: string;
  competition_level: string;
  future_relevance: string;
  is_niche: boolean;
  niche_category: string;
  description: string;
  responsibilities: string[];
  qualifications: string[];
  growth_path: string[];
  salary: RoleSalary;
  top_companies: string[];
  skills: RoleSkills;
  matching_interests: string[];
  matching_skills: string[];
}

// ── Matching ──────────────────────────────────────────────────────────────────
export interface MatchResult {
  role: Role;
  score: number;
  matched_interests: string[];
  matched_skills: string[];
}

export interface MatchResponse {
  results: MatchResult[];
  explanation: string;
}

// ── Roadmap ───────────────────────────────────────────────────────────────────
export interface RoadmapPhaseItem {
  skill: string;
  why: string;
  resource: string;
  time_estimate?: string;
}

export interface RoadmapProject {
  title: string;
  description: string;
  skills_demonstrated: string[];
  difficulty: string;
}

export interface Roadmap {
  summary?: string;
  immediate_focus: RoadmapPhaseItem[];
  next_level: RoadmapPhaseItem[];
  good_to_explore: RoadmapPhaseItem[];
  projects: RoadmapProject[];
  motivational_message?: string;
}

export interface SavedRoadmap {
  id: number;
  role_id: string;
  role_title: string;
  roadmap: Roadmap;
  created_at: string;
}

// ── Tracker ───────────────────────────────────────────────────────────────────
export interface StackDimension {
  label: string;
  options: string[];
}

export interface StackSchema {
  dim1: StackDimension;
  dim2: StackDimension;
  dim3: StackDimension;
}

export interface Schedule {
  weekday_hours: number;
  weekend_hours: number;
  weekly_total_hours: number;
  target_languages: string[];
}

export interface Topic {
  id: number;
  category: string;
  topic_name: string;
  subtopics: string[];
  estimated_hours: number;
  is_completed: boolean;
  completed_at: string | null;
}

export interface TrackerMetrics {
  total_topics: number;
  completed_topics: number;
  percentage: number;
  total_hours: number;
  completed_hours: number;
  remaining_hours: number;
  weeks_remaining: number;
}

export interface TrackerState {
  schedule: Schedule;
  topics: Topic[];
  metrics: TrackerMetrics;
}

// ── Chat ──────────────────────────────────────────────────────────────────────
export type ChatRole = "user" | "model";

export interface ChatMessage {
  role: ChatRole;
  content: string;
}
