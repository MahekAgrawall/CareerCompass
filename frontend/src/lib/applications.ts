/**
 * The application board's vocabulary: the five stages, in the candidate's words,
 * and the snapshot rule that turns a job card into a stored row.
 *
 * The stage list is the page's single source of truth. The API validates the
 * same five slugs (`backend/services/application_service.py`), and mapping them
 * to labels in one place means a stage cannot be renamed in a heading while a
 * select still submits the old value.
 */
import type { ApplicationInput, ApplicationStatus, JobPosting, SavedJob } from "@/api/types";

/** The one React Query key under which a candidate's saved jobs live. */
export const APPLICATIONS_KEY = ["applications"] as const;

export interface Stage {
  status: ApplicationStatus;
  label: string;
  icon: string;
  /** What the stage means, in one line — used as the section caption. */
  hint: string;
}

/** In order: the sequence a real search follows, with `rejected` as its exit. */
export const STAGES: readonly Stage[] = [
  { status: "saved", label: "Saved", icon: "🔖", hint: "Filed, not applied to yet." },
  {
    status: "applied",
    label: "Applied",
    icon: "📤",
    hint: "Application sent — waiting to hear back.",
  },
  {
    status: "interview",
    label: "Interview",
    icon: "🗣️",
    hint: "Talking to them: a screen, a task or a full loop.",
  },
  { status: "offer", label: "Offer", icon: "🎉", hint: "An offer, or a decision to make." },
  {
    status: "rejected",
    label: "Closed",
    icon: "🚫",
    hint: "Rejected or withdrawn — kept so the board stays honest.",
  },
];

/** A status from the API rendered as its stage; unknown values fall back safely. */
export function stageOf(status: ApplicationStatus): Stage {
  return STAGES.find((stage) => stage.status === status) ?? STAGES[0];
}

/** How many of `rows` sit at each stage, including the empty stages. */
export function stageCounts(rows: SavedJob[]): Map<ApplicationStatus, number> {
  const counts = new Map<ApplicationStatus, number>();
  for (const stage of STAGES) counts.set(stage.status, 0);
  for (const row of rows) counts.set(row.status, (counts.get(row.status) ?? 0) + 1);
  return counts;
}

/** The rows grouped by stage, in stage order — empty stages included. */
export function groupByStage(rows: SavedJob[]): { stage: Stage; rows: SavedJob[] }[] {
  return STAGES.map((stage) => ({
    stage,
    rows: rows.filter((row) => row.status === stage.status),
  }));
}

/**
 * The snapshot the API stores: every field the card showed, so the row still
 * says what the candidate applied to after the listing is taken down.
 *
 * `similarity` is deliberately left out — it is the cosine score against one
 * particular search, not a property of the posting.
 */
export function applicationInput(posting: JobPosting): ApplicationInput {
  return {
    posting_id: posting.id,
    title: posting.title,
    company: posting.company,
    location: posting.location,
    remote: posting.remote,
    employment_type: posting.employment_type,
    salary_text: posting.salary_text,
    published: posting.published,
    url: posting.url,
    source: posting.source,
  };
}
