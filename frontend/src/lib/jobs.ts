/**
 * The Jobs page's filters, and the vocabulary they translate into.
 *
 * `GET /jobs/search` takes a ranking query (`q`) plus the structured filters the
 * backend applies as a Qdrant payload filter — so the filters narrow the whole
 * `job_role` collection, and the response's `matched` is a count of that
 * collection rather than of the window a search happened to rank. Nothing here
 * filters postings any more: the page can only report what the server looked at,
 * which is the point of moving the rules to `services/job_service.py`.
 *
 * Two vocabularies meet here, deliberately:
 *
 * * the page shows, and puts in the URL, *human* wording ("Senior / lead"), so a
 *   link stays readable and an existing `/jobs?experience=…` bookmark keeps
 *   working;
 * * the endpoint takes stable slugs (`experience=senior`, `remote=true`), so its
 *   contract does not move when a label is reworded.
 */
import type { JobPosting, Profile } from "@/api/types";

/** The endpoint accepts 1–50; ask for the widest page it will give. */
export const SEARCH_LIMIT = 50;

/** The endpoint caps both of these, so the fields do too. */
export const QUERY_MAX_LENGTH = 200;
export const LOCATION_MAX_LENGTH = 80;

export const ANY_EXPERIENCE = "Any experience";

/**
 * Experience buckets, chosen from what the boards actually publish: their
 * `seniority` field is blank for most postings (only one of the two boards sends
 * one at all), so each bucket also matches the title and the contract wording —
 * which is why there are three meaningful levels rather than a flat list of
 * seniority labels. The rules themselves live beside the filter they build, in
 * `backend/services/job_service.py`.
 */
export const EXPERIENCE_OPTIONS = [
  ANY_EXPERIENCE,
  "Internship / student",
  "Entry level / junior",
  "Senior / lead",
] as const;

export type ExperienceOption = (typeof EXPERIENCE_OPTIONS)[number];

/** Label shown in the page -> the slug the endpoint validates. */
const EXPERIENCE_SLUGS: Record<string, string> = {
  "Internship / student": "internship",
  "Entry level / junior": "entry",
  "Senior / lead": "senior",
};

export const ANY_ARRANGEMENT = "Any arrangement";

/**
 * "On-site / not stated" is deliberate: the boards only ever flag the *remote*
 * postings, so a false flag means the listing said nothing, not that the job is
 * office-based. Filtering on it is still useful — it is how a candidate hides
 * the hundred remote rows they cannot take.
 */
export const ARRANGEMENT_OPTIONS = [
  ANY_ARRANGEMENT,
  "Remote only",
  "On-site / not stated",
] as const;

export type ArrangementOption = (typeof ARRANGEMENT_OPTIONS)[number];

/** The endpoint takes a boolean flag; the page shows wording. */
const ARRANGEMENT_SLUGS: Record<string, string> = {
  "Remote only": "true",
  "On-site / not stated": "false",
};

/** An arrangement label as the endpoint takes it: "true", "false", or "". */
export function remoteParam(arrangement: string): string {
  return ARRANGEMENT_SLUGS[arrangement] ?? "";
}

/** The reverse, for reading the value back out of the URL. */
export function arrangementFromParam(value: string | null): string {
  for (const [label, slug] of Object.entries(ARRANGEMENT_SLUGS)) {
    if (slug === value) return label;
  }
  return ANY_ARRANGEMENT;
}

export interface JobFilters {
  role: string;
  location: string;
  experience: string;
  arrangement: string;
}

/** The endpoint's inputs, as the URL carries them. Empty fields are left out. */
export function postingParams(filters: JobFilters): Record<string, string> {
  const params: Record<string, string> = { q: filters.role.trim() };
  if (filters.location.trim()) params.location = filters.location.trim();
  const experience = EXPERIENCE_SLUGS[filters.experience];
  if (experience) params.experience = experience;
  const remote = remoteParam(filters.arrangement);
  if (remote) params.remote = remote;
  return params;
}

/** True when the page has something to ask the endpoint. */
export function hasAnyFilter(filters: JobFilters): boolean {
  return Boolean(
    filters.role.trim() ||
      filters.location.trim() ||
      EXPERIENCE_SLUGS[filters.experience] ||
      ARRANGEMENT_SLUGS[filters.arrangement],
  );
}

/** Locations actually present in the results, offered as datalist suggestions. */
export function locationSuggestions(postings: JobPosting[], max = 40): string[] {
  const unique = new Set<string>();
  for (const posting of postings) {
    const value = posting.location.trim();
    if (value) unique.add(value);
  }
  return [...unique].sort((a, b) => a.localeCompare(b)).slice(0, max);
}

const SOURCE_LABELS: Record<string, string> = {
  himalayas: "Himalayas",
  arbeitnow: "Arbeitnow",
};

/** A readable board name for a posting's `source`. */
export function sourceLabel(source: string): string {
  if (!source) return "Unknown board";
  return SOURCE_LABELS[source] ?? source.charAt(0).toUpperCase() + source.slice(1);
}

/**
 * A search string built from the questionnaire answers.
 *
 * The same answers the semantic role match runs on — interests, current skills
 * and the stated goal — are joined into one ranking query and pointed at the
 * live boards. Duplicates are dropped and the result is truncated to the
 * endpoint's limit; location is deliberately left out because the Jobs page has
 * a field of its own for it.
 */
export function profileQuery(profile: Partial<Profile>): string {
  const seen = new Set<string>();
  const parts: string[] = [];
  for (const raw of [
    ...(profile.interests ?? []),
    ...(profile.current_skills ?? []),
    profile.career_goal ?? "",
  ]) {
    const value = raw.trim();
    if (value && !seen.has(value.toLowerCase())) {
      seen.add(value.toLowerCase());
      parts.push(value);
    }
  }
  return parts.join(", ").slice(0, QUERY_MAX_LENGTH);
}
