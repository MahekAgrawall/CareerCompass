import { Link, useLocation } from "react-router-dom";

import type { JobPosting } from "@/api/types";
import { stageOf } from "@/lib/applications";
import { useSavedJob } from "@/state/useSavedJob";

/**
 * The "keep this one" control on a job card, with one state per reality:
 *
 * * **signed out** — a way in, rather than a button that would 401;
 * * **not filed yet** — one click files it, through an endpoint that is
 *   idempotent by posting id, so a double click cannot create two rows;
 * * **already filed** — it reports the stage the application reached and points
 *   at the tracker. It deliberately does *not* toggle the row off: the Jobs page
 *   is a place to find work, and removing a saved job belongs next to the
 *   application it removes.
 */
export default function SaveJobButton({ posting }: { posting: JobPosting }) {
  const location = useLocation();
  const { signedIn, saved, save } = useSavedJob(posting);

  if (!signedIn) {
    return (
      <Link
        to="/auth"
        state={{ from: `${location.pathname}${location.search}` }}
        className="btn btn-secondary w-full"
      >
        🔑 Sign in to save
      </Link>
    );
  }

  if (saved) {
    const stage = stageOf(saved.status);
    return (
      <Link to="/applications" className="btn btn-secondary w-full">
        {stage.icon} {stage.label} · View tracker →
      </Link>
    );
  }

  return (
    <>
      <button
        type="button"
        className="btn btn-secondary w-full"
        disabled={save.isPending}
        onClick={() => save.mutate()}
      >
        {save.isPending ? "Saving…" : "🔖 Save job"}
      </button>
      {save.isError && (
        <p className="mt-1 text-xs text-rose-600">
          Could not save this job: {save.error.message}
        </p>
      )}
    </>
  );
}
