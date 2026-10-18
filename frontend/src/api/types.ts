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
  work_mode: string;
  open_to_relocate: string;
  career_goal: string;
  current_skills: string[];
  interests: string[];
}

// ── Roles ─────────────────────────────────────────────────────────────────────
export interface SalaryBand {
  min: number;
  max: number;
  label: string;
}

export interface SalarySource {
  /** "market" = job-posting data, "product" = verified product-company offers, "report" = published industry report. */
  kind: "market" | "product" | "report";
  name: string;
  url: string;
  /** ISO month the source was published, e.g. "2026-10-12". */
  as_of: string;
  /** How much data the figure rests on, quoted for the reader. */
  sample: string;
}

export interface RoleSalary {
  fresher_0_1: SalaryBand;
  mid_1_3: SalaryBand;
  senior_3_plus: SalaryBand;
  /** Month the bands were last reviewed, e.g. "2026-10". */
  as_of: string;
  /** Median across India job postings (₹LPA); null when no page exists for the title. */
  market_median: number | null;
  /** Median across verified product-company offers (₹LPA); null when proxied by a family. */
  product_median: number | null;
  sources: SalarySource[];
  /** Why a title with no dedicated market page was positioned where it is; "" when it has one. */
  anchor_note: string;
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
  /** 0-100: share of the candidate's interests this role covers. */
  interest_score: number;
  /** 0-100: share of the candidate's skills this role uses. */
  skill_score: number;
  matched_interests: string[];
  matched_skills: string[];
  /** Profile chips that would raise the skill half of this match. */
  suggested_skills: string[];
  /** How the role was found: "keyword" (interest chips) and/or "semantic" (role index). */
  recalled_by: Array<"keyword" | "semantic">;
  /** Cosine similarity from the semantic index, when it helped recall this role. */
  semantic_similarity: number | null;
}

export interface MatchResponse {
  results: MatchResult[];
  explanation: string;
  interest_weight: number;
  skill_weight: number;
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
  /** The model that generated the plan; "" for plans saved before provenance. */
  model: string;
  /** Fingerprint of the prompt templates in force when it was generated; "" if unknown. */
  prompt_version: string;
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

// ── Live job postings ─────────────────────────────────────────────────────────
/**
 * One posting from the public job boards, exactly as `GET /jobs/search` returns
 * it (see `backend/app/schemas.py` → `JobPosting`). These are live listings, not
 * catalogued roles: there is no fit score, only the index's cosine `similarity`
 * and the query words the title happened to carry.
 */
export interface JobPosting {
  id: string;
  title: string;
  company: string;
  location: string;
  /** The board's own remote flag; false means "not stated as remote". */
  remote: boolean;
  /** The board's own wording, e.g. "Full Time", "Internship"; "" when blank. */
  employment_type: string;
  /** The board's seniority labels; empty for boards that do not publish one. */
  seniority: string[];
  categories: string[];
  /** Pre-rendered by the ingest, e.g. "EUR 80000-100000 / annual"; "" when undisclosed. */
  salary_text: string;
  /** Publication date (YYYY-MM-DD), or "" when the board gave none. */
  published: string;
  /** The board's own listing — the original application link. */
  url: string;
  /** Which board it came from, e.g. "himalayas" or "arbeitnow". */
  source: string;
  excerpt: string;
  /**
   * Cosine similarity to the search text — how near the posting is *in meaning*.
   * `GET /jobs/search` ranks title matches above it (see `matched_terms`), so the
   * cards are not always in descending order of this number.
   */
  similarity: number;
  /**
   * The query words this posting's title carries, in the order they were typed.
   *
   * The words are matched against the whole posting, so a result can be here
   * without any of them appearing in its title — this badge reports the hits a
   * reader can see for themselves. Empty on `/jobs/for-role`, which ranks by
   * meaning alone.
   */
  matched_terms: string[];
}

/**
 * When the live postings were pulled, and whether that is getting old.
 *
 * Recorded by the ingest beside the collection, not derived from the postings:
 * a board keeps serving a listing after the job is filled, so a posting's own
 * `published` date says when the job was posted, never when we last looked at
 * the board. Empty strings mean "not recorded" (a `QDRANT_URL` deployment keeps
 * that file next to the ingest), and `age_days`/`stale` are the backend's own
 * reading so the page cannot disagree with it about what counts as old.
 */
export interface HarvestFreshness {
  /** UTC ISO 8601, or "" when nothing recorded it. */
  harvested_at: string;
  /** When that harvest was loaded into the index. */
  ingested_at: string;
  /** Whole days since the harvest, or null when there is no usable date. */
  age_days: number | null;
  /** True once the harvest is at least `stale_after_days` old. */
  stale: boolean;
  /** The threshold `stale` was decided with. */
  stale_after_days: number;
}

export interface JobSearchResponse {
  /**
   * The text the ranking actually ran on (echoed back). It is the caller's own
   * query, or their filter terms when they typed none — a filter-only browse
   * still needs something to rank on.
   */
  query: string;
  /** False when the `job_role` index has not been built on this server. */
  available: boolean;
  /**
   * True when no posting said *all* of the caller's words, so the search fell
   * back to requiring only some of them. Worth showing: the page then found less
   * than it was asked for, and saying so is the difference between a loosened
   * search and a misleading one.
   */
  relaxed: boolean;
  /** How many postings this page returned (never more than the limit asked for). */
  count: number;
  /** How many the words and filters leave in the whole collection. */
  matched: number;
  /** How many postings the collection holds in total. */
  indexed: number;
  /** When this data was harvested, and whether that is old enough to warn about. */
  freshness: HarvestFreshness;
  results: JobPosting[];
}

/**
 * `GET /jobs/locations` — the place vocabulary of the live postings, commonest
 * first. The Jobs page's location field suggests from this rather than from the
 * results it happens to be showing, so a fresh page still offers real places.
 */
export interface JobLocationOption {
  value: string;
  /**
   * How many postings a search for this place matches — counted by the backend
   * with the very filter that search applies, so it is the `matched` a click on
   * the option will report.
   */
  count: number;
}

export interface JobLocationsResponse {
  /** False when the `job_role` index has not been built on this server. */
  available: boolean;
  locations: JobLocationOption[];
}

/**
 * `POST /jobs/for-role` — the postings nearest one catalogued role, best first.
 * The candidate's questionnaire answers are folded into the ranking server-side,
 * so the same role can come back in a different order for two people.
 */
export interface RoleJobsResponse {
  role_id: string;
  role_title: string;
  /** False when the `job_role` index has not been built on this server. */
  available: boolean;
  count: number;
  results: JobPosting[];
}

// ── Saved jobs & application tracking ─────────────────────────────────────────
/**
 * The stages a saved posting moves through, in the order a search really goes.
 * `saved` is the bookmark every row starts at; `rejected` is a stage rather than
 * a deletion, so an application that went nowhere stops cluttering the ones that
 * are still live. Mirrors `backend/services/application_service.py`.
 */
export type ApplicationStatus = "saved" | "applied" | "interview" | "offer" | "rejected";

/**
 * One saved posting. The fields are a *snapshot* taken when it was filed, not a
 * live reference: the boards rotate and the index is rebuilt, so this is what the
 * candidate applied to even after the listing is gone.
 */
export interface SavedJob {
  id: number;
  posting_id: string;
  title: string;
  company: string;
  location: string;
  remote: boolean;
  employment_type: string;
  salary_text: string;
  published: string;
  url: string;
  source: string;
  status: ApplicationStatus;
  note: string;
  /** When it was filed, and when it was last moved or edited. */
  created_at: string;
  updated_at: string;
}

/** The snapshot body `POST /applications` takes (the posting, as the card showed it). */
export interface ApplicationInput {
  posting_id: string;
  title: string;
  company?: string;
  location?: string;
  remote?: boolean;
  employment_type?: string;
  salary_text?: string;
  published?: string;
  url?: string;
  source?: string;
  status?: ApplicationStatus;
  note?: string;
}

export interface ApplicationListResponse {
  count: number;
  results: SavedJob[];
}

// ── Chat ──────────────────────────────────────────────────────────────────────
export type ChatRole = "user" | "model";

export interface ChatMessage {
  role: ChatRole;
  content: string;
}
