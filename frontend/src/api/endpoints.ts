/** Typed, endpoint-per-function API surface. */
import { api, apiStream } from "./client";
import type {
  ChatMessage,
  JobSearchResponse,
  MatchResponse,
  MeResponse,
  Profile,
  Roadmap,
  Role,
  RoleJobsResponse,
  SavedRoadmap,
  Schedule,
  StackSchema,
  TokenResponse,
  Topic,
  TrackerState,
  User,
} from "./types";

// ── Meta ──────────────────────────────────────────────────────────────────────
export const getHealth = () =>
  api.get<{
    status: string;
    service: string;
    version: string;
    semantic_index?: {
      provider: string;
      model: string;
      collection: string;
      available: boolean;
      points: number;
      other_collections?: string[];
    };
  }>("/health");

// ── Auth ──────────────────────────────────────────────────────────────────────
export const signup = (name: string, email: string, password: string) =>
  api.post<TokenResponse>("/auth/signup", { name, email, password });

export const login = (email: string, password: string) =>
  api.post<TokenResponse>("/auth/login", { email, password });

export const getMe = () => api.get<MeResponse>("/auth/me");

// ── Profile ───────────────────────────────────────────────────────────────────
export const getProfile = () => api.get<Partial<Profile>>("/profile");
export const saveProfile = (profile: Profile) => api.put<Profile>("/profile", profile);

// ── Roles ─────────────────────────────────────────────────────────────────────
export const listRoles = () => api.get<Role[]>("/roles");
export const listCategories = () => api.get<string[]>("/roles/categories");
export const getRole = (roleId: string) => api.get<Role>(`/roles/${encodeURIComponent(roleId)}`);

// ── Matching ──────────────────────────────────────────────────────────────────
/**
 * `context` only feeds the semantic recall stage (it never enters the score), so
 * the free-text goal can surface roles whose chips do not overlap the profile.
 * The work hub rides along for the same reason: the curated roles are not
 * location-bound, but the index should still know where the candidate is aiming.
 */
export const matchRoles = (
  interests: string[],
  currentSkills: string[],
  explain = true,
  context: { careerGoal?: string; experience?: string; workMode?: string; location?: string } = {},
) =>
  api.post<MatchResponse>("/match", {
    interests,
    current_skills: currentSkills,
    explain,
    career_goal: context.careerGoal ?? "",
    experience: context.experience ?? "",
    work_mode: context.workMode ?? "",
    location: context.location ?? "",
  });

// ── Live jobs ─────────────────────────────────────────────────────────────────
/**
 * `GET /jobs/search` takes a ranking query plus the structured filters the page
 * offers (`q` up to 200 characters, `location`, `experience`, `remote`), and
 * returns `{query, available, count, matched, indexed, results}`. The filters are
 * applied by the vector store, so `matched` counts the whole collection — see
 * `lib/jobs.ts` for how the page's wording maps onto the endpoint's slugs.
 */
export const searchJobs = (params: Record<string, string>, limit = 50) =>
  api.get<JobSearchResponse>(
    `/jobs/search?${new URLSearchParams({ ...params, limit: String(limit) })}`,
  );

/**
 * `POST /jobs/for-role` — the live postings nearest one catalogued role. The
 * questionnaire travels in the body (interests, skills, goal, location), so the
 * ranking is personalised rather than a plain text search for the role title.
 */
export const jobsForRole = (roleId: string, profile: Partial<Profile>, limit = 5) =>
  api.post<RoleJobsResponse>("/jobs/for-role", { role_id: roleId, limit, profile });

// ── Roadmap ───────────────────────────────────────────────────────────────────
export const generateRoadmap = (roleId: string, profile: Partial<Profile>, signal?: AbortSignal) =>
  api.post<Roadmap>("/roadmap", { role_id: roleId, profile }, { signal });

export const listSavedRoadmaps = () => api.get<SavedRoadmap[]>("/roadmaps");

export const deleteSavedRoadmap = (roadmapId: number) =>
  api.del<void>(`/roadmaps/${roadmapId}`);

// ── Tracker ───────────────────────────────────────────────────────────────────
export const getStackSchema = (roleId: string) =>
  api.get<StackSchema>(`/tracker/stack/${encodeURIComponent(roleId)}`);

export const getTracker = (roleId: string) =>
  api.get<TrackerState>(`/tracker/topics/${encodeURIComponent(roleId)}`);

export const getSchedule = (roleId: string) =>
  api.get<Schedule>(`/tracker/schedule/${encodeURIComponent(roleId)}`);

export const saveSchedule = (payload: {
  role_id: string;
  weekday_hours: number;
  weekend_hours: number;
  target_languages: string[];
}) =>
  api.put<{ schedule: Schedule; topics: Topic[]; metrics: TrackerState["metrics"] }>(
    "/tracker/schedule",
    payload,
  );

export const toggleTopic = (topicId: number, isCompleted: boolean) =>
  api.patch<{ id: number; is_completed: boolean }>(`/tracker/topics/${topicId}`, {
    is_completed: isCompleted,
  });

// ── Chat ──────────────────────────────────────────────────────────────────────
export const sendChat = (payload: {
  roleId: string;
  roadmap: Roadmap;
  message: string;
  history: ChatMessage[];
  profile: Partial<Profile>;
}) =>
  api.post<{ reply: string }>("/chat", {
    role_id: payload.roleId,
    roadmap: payload.roadmap,
    new_message: payload.message,
    history: payload.history,
    profile: payload.profile,
  });

export const streamChat = (
  payload: {
    roleId: string;
    roadmap: Roadmap;
    message: string;
    history: ChatMessage[];
    profile: Partial<Profile>;
  },
  onChunk: (text: string) => void,
  signal?: AbortSignal,
) =>
  apiStream(
    "/chat/stream",
    {
      role_id: payload.roleId,
      roadmap: payload.roadmap,
      new_message: payload.message,
      history: payload.history,
      profile: payload.profile,
    },
    onChunk,
    signal,
  );

export type { User };
