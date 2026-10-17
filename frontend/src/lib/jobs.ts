/**
 * Filters, query building and matching for the Jobs page.
 *
 * `GET /jobs/search` exposes exactly one free-text query (`q`) and a page size —
 * no location or experience parameters — so the three filters work in two
 * stages, and the page says so out loud:
 *
 * 1. **Ranking.** Every filled field is folded into `q`. Location, seniority and
 *    contract wording are part of the text embedded for each posting, so this
 *    genuinely steers which postings come back.
 * 2. **Refinement.** Location and experience then filter the returned window
 *    using the structured fields the endpoint *does* return (`location`,
 *    `remote`, `seniority`, `employment_type`, `title`).
 *
 * Stage 2 can only ever inspect the postings the server ranked (the
 * `SEARCH_LIMIT` closest), which is why the page reports both numbers rather
 * than implying the filters swept the whole collection.
 */
import type { JobPosting } from "@/api/types";

/** The endpoint accepts 1–50; ask for the widest window so refinement has material. */
export const SEARCH_LIMIT = 50;

/** `q` is capped at 200 characters by the endpoint, so the composed query is too. */
export const QUERY_MAX_LENGTH = 200;

export const ANY_EXPERIENCE = "Any experience";

/**
 * Experience buckets, chosen from what the boards actually publish. Their
 * `seniority` field is empty for most postings (only one of the two boards sends
 * one), so each bucket also matches the posting title and contract wording —
 * which is why there are three meaningful levels rather than a flat list of
 * seniority labels.
 */
export const EXPERIENCE_OPTIONS = [
  ANY_EXPERIENCE,
  "Internship / student",
  "Entry level / junior",
  "Senior / lead",
] as const;

export type ExperienceOption = (typeof EXPERIENCE_OPTIONS)[number];

export interface JobFilters {
  role: string;
  location: string;
  experience: string;
}

export const EMPTY_FILTERS: JobFilters = {
  role: "",
  location: "",
  experience: ANY_EXPERIENCE,
};

interface ExperienceRule {
  /** Substrings looked for in the posting title. */
  title: string[];
  /** Substrings looked for in the board's own seniority labels. */
  seniority: string[];
  /** Substrings looked for in the board's own contract wording. */
  contract: string[];
}

const EXPERIENCE_RULES: Record<string, ExperienceRule> = {
  "Internship / student": {
    title: ["intern", "working student", "werkstudent", "praktik", "trainee"],
    seniority: [],
    contract: ["intern", "working student", "werkstudent", "praktik"],
  },
  "Entry level / junior": {
    title: ["junior", "entry level", "entry-level", "graduate"],
    seniority: ["entry-level"],
    contract: [],
  },
  "Senior / lead": {
    title: ["senior", "sr.", "lead", "principal", "staff", "head of", "director"],
    seniority: ["senior", "director", "executive"],
    contract: [],
  },
};

function includesAny(haystack: string, needles: string[]): boolean {
  return needles.some((needle) => haystack.includes(needle));
}

/** The single query string sent to the endpoint; "" when nothing was asked for. */
export function buildQuery(filters: JobFilters): string {
  const experience = filters.experience === ANY_EXPERIENCE ? "" : filters.experience;
  return [filters.role, filters.location, experience]
    .map((value) => value.trim())
    .filter(Boolean)
    .join(" ")
    .slice(0, QUERY_MAX_LENGTH);
}

/** True when the posting's own location text (or remote flag) satisfies the term. */
export function matchesLocation(posting: JobPosting, term: string): boolean {
  const needle = term.trim().toLowerCase();
  if (!needle) return true;
  // "Remote" is a work arrangement, not a place name, so it uses the flag too.
  if (needle.startsWith("remote")) {
    return posting.remote || posting.location.toLowerCase().includes("remote");
  }
  return posting.location.toLowerCase().includes(needle);
}

/** True when the posting satisfies the chosen experience bucket. */
export function matchesExperience(posting: JobPosting, experience: string): boolean {
  if (!experience || experience === ANY_EXPERIENCE) return true;
  const rule = EXPERIENCE_RULES[experience];
  if (!rule) return true;
  return (
    includesAny(posting.title.toLowerCase(), rule.title) ||
    includesAny(posting.seniority.join(" ").toLowerCase(), rule.seniority) ||
    includesAny(posting.employment_type.toLowerCase(), rule.contract)
  );
}

export function matchesFilters(posting: JobPosting, filters: JobFilters): boolean {
  return (
    matchesLocation(posting, filters.location) &&
    matchesExperience(posting, filters.experience)
  );
}

/** The postings that survive the structured filters. */
export function refinePostings(postings: JobPosting[], filters: JobFilters): JobPosting[] {
  return postings.filter((posting) => matchesFilters(posting, filters));
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

/** True when location or experience would narrow the ranked window. */
export function hasNarrowingFilters(filters: JobFilters): boolean {
  return Boolean(filters.location.trim()) || filters.experience !== ANY_EXPERIENCE;
}
