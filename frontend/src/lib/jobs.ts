/**
 * The Jobs page's filters, and the vocabulary they translate into.
 *
 * `GET /jobs/search` takes the caller's words (`q`) plus the structured filters,
 * and the backend applies both to the whole `job_role` collection — so a posting
 * comes back only when it satisfies every condition, and the response's `matched`
 * is a count of that collection rather than of the window a search happened to
 * rank. Nothing here filters postings any more: the page can only report what the
 * server looked at, which is the point of moving the rules to
 * `services/job_service.py`.
 *
 * Two vocabularies meet here, deliberately:
 *
 * * the page shows, and puts in the URL, *human* wording ("Senior / lead"), so a
 *   link stays readable and an existing `/jobs?experience=…` bookmark keeps
 *   working;
 * * the endpoint takes stable slugs (`experience=senior`, `remote=true`), so its
 *   contract does not move when a label is reworded.
 */
import { formatDate, truncate } from "@/lib/format";
import type { HarvestFreshness, Profile } from "@/api/types";

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

/**
 * The count beside a suggested place, phrased for a datalist option's label.
 *
 * The number is the backend's: `GET /jobs/locations` counts each option with the
 * very filter a search for it applies, so a suggestion advertises what choosing
 * it will actually return — which is the only reason the number is worth showing.
 */
export function locationOptionLabel(count: number): string {
  return count === 1 ? "1 posting" : `${count} postings`;
}

/**
 * The label beside one of the Indian hubs offered as a *preference*.
 *
 * A preference is listed whether or not the boards carry it, so its count can be
 * zero — and "0 postings" beside a place the page invited the reader to look at
 * reads like a bug rather than a fact about the data. The zero case is worded as
 * what it is; the row's own note explains why the Indian market is thin here.
 */
export function preferredLocationLabel(count: number): string {
  return count === 0 ? "no live postings" : locationOptionLabel(count);
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
 * One line saying when the postings were pulled.
 *
 * The date comes straight from the server's `harvested_at` (UTC), so the page
 * never has to guess, and it is sliced rather than run through the browser's
 * timezone: the day the harvest happened is a fact about the data, and shifting
 * it a day to match a local clock would misdate it. Returns "" only when there is
 * no freshness block at all; an index that recorded no date says so instead of
 * staying quiet, because silence is how postings age unnoticed.
 */
export function harvestNote(freshness: HarvestFreshness | undefined): string {
  if (!freshness) return "";
  if (!freshness.harvested_at) return "Harvest date not recorded for this index.";
  const day = formatDate(freshness.harvested_at);
  const age = freshness.age_days;
  if (age === null || age === undefined) return `Harvested on ${day}.`;
  if (age <= 0) return `Harvested on ${day} (today).`;
  if (age === 1) return `Harvested on ${day} (yesterday).`;
  return `Harvested on ${day} (${age} days ago).`;
}

/**
 * The staleness warning, or "" while the harvest is still young.
 *
 * The judgement is the backend's (`freshness.stale`), and its threshold is used
 * in the wording, so the page cannot invent either one. The point is not to
 * apologise for the data but to stop a candidate treating a three-week-old
 * listing as something they can still apply to.
 */
export function staleNote(freshness: HarvestFreshness | undefined): string {
  if (!freshness?.stale) return "";
  const weeks = Math.round(freshness.stale_after_days / 7);
  return (
    `These postings were harvested ${freshness.age_days} days ago — older than the ` +
    `${weeks}-week mark. Boards fill, withdraw and re-post their listings, so some of ` +
    "what you see here has almost certainly gone. Re-run the harvest to refresh it."
  );
}

/**
 * The line shown when the search had to loosen its words, or "" when it did not.
 *
 * The backend requires every word typed and only falls back to requiring some of
 * them when nothing carries all of them (a goal sentence, for instance, is not a
 * keyword). Saying so is the difference between a loosened search and a misleading
 * one: the page found less than it was asked for, and the reader should know which
 * words to drop or fix. The query is truncated because a profile search can be a
 * whole sentence, and it is quoted back only to make the point concrete.
 */
export function relaxedNote(relaxed: boolean | undefined, role: string): string {
  if (!relaxed) return "";
  const words = role.trim();
  if (!words) return "";
  return (
    `No posting says every word of “${truncate(words, 60)}”, so these are the ` +
    "postings that say any of it. Drop a word or two for exact matches."
  );
}

/** How much of a profile a board search carries (see `profileQuery`). */
const PROFILE_INTERESTS = 3;
const PROFILE_SKILLS = 3;
const PROFILE_QUERY_MAX_LENGTH = 120;

/** The non-empty values of a profile field, trimmed and de-duplicated. */
function tidy(values: readonly string[]): string[] {
  const seen = new Set<string>();
  const kept: string[] = [];
  for (const raw of values) {
    const value = raw.trim();
    const key = value.toLowerCase();
    if (value && !seen.has(key)) {
      seen.add(key);
      kept.push(value);
    }
  }
  return kept;
}

/**
 * A search string built from the questionnaire answers, for the live boards.
 *
 * The same answers the semantic role match runs on, but pointed at listings
 * rather than at the catalogued roles — and deliberately short. The goal leads,
 * the interests follow, and the skills come last, because those say what the
 * candidate *wants* while a full list of skills turns the box into a pile of
 * technologies. Three of each, and only while they fit: this string is the
 * ranking text, and the page lifts postings whose titles carry its words, so a
 * tighter query gives a sharper page than a long one.
 *
 * Location is left out — the Jobs page has a field of its own for it — and a goal
 * long enough to fill the budget on its own still gives the box something to run.
 */
export function profileQuery(profile: Partial<Profile>): string {
  const goal = (profile.career_goal ?? "").trim();
  const wanted = [
    goal,
    ...tidy(profile.interests ?? []).slice(0, PROFILE_INTERESTS),
    ...tidy(profile.current_skills ?? []).slice(0, PROFILE_SKILLS),
  ];

  const seen = new Set<string>();
  const parts: string[] = [];
  for (const value of wanted) {
    const key = value.toLowerCase();
    if (!value || seen.has(key)) continue;
    if ([...parts, value].join(", ").length > PROFILE_QUERY_MAX_LENGTH) continue;
    seen.add(key);
    parts.push(value);
  }
  const query = parts.join(", ");
  return query || goal.slice(0, PROFILE_QUERY_MAX_LENGTH);
}
