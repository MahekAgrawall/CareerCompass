import Badge from "./Badge";
import JobClassification from "./JobClassification";
import SaveJobButton from "./SaveJobButton";
import type { JobPosting } from "@/api/types";
import { formatDate, truncate } from "@/lib/format";
import { attributionFor, sourceLabel } from "@/lib/jobs";

/**
 * How the posting words the arrangement, e.g. "Remote · Full Time".
 *
 * "On-site / not stated" is deliberate for the false case (the boards only ever
 * flag the remote ones), and so is "Remote (from the ad)" for a board that
 * publishes no remote flag: Adzuna's API has none, so that marking is read out of
 * the advert's own text (see `REMOTE_WORDS` in `services/job_feed.py`) and the
 * card says so rather than passing a reading off as the advertiser's own field.
 */
function arrangement(posting: JobPosting): string {
  const derived = posting.remote && posting.source === "adzuna";
  return [
    derived ? "Remote (from the ad)" : posting.remote ? "Remote" : "On-site / not stated",
    posting.employment_type.trim(),
  ]
    .filter(Boolean)
    .join(" · ");
}

/**
 * One live posting, as returned by `GET /jobs/search`.
 *
 * Unlike `RoleCard` these carry no fit score — only the index's cosine
 * `similarity` to the search text — so the card shows the posting's own facts and
 * links straight out to the original listing. The words the title carried are
 * shown too: they are what put this card above a posting that merely sits near
 * the query in meaning, and without them that ordering looks arbitrary.
 *
 * Below the excerpt sits what the classifier made of the advert (`JobClassification`)
 * — a reading of the *text*, which is why it is not mixed in with the posting's own
 * badges above, and why a listing nobody has read offers to be read rather than
 * showing an empty verdict.
 *
 * A board that requires attribution gets it here, once per advert and beside the
 * card's own outbound link (see `attributionFor`).
 */
export default function JobCard({ posting }: { posting: JobPosting }) {
  const board = sourceLabel(posting.source);
  const salary = posting.salary_text.trim();
  const level = posting.seniority.join(", ");
  const attribution = attributionFor(posting.source);

  return (
    <div className="card card-hover flex h-full flex-col p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-base font-bold text-slate-900">{posting.title}</h3>
          <p className="mt-0.5 text-xs text-slate-500">
            🏢 {posting.company || "Company not stated"}
          </p>
        </div>
        <Badge variant="muted">🏷️ {board}</Badge>
      </div>

      <div className="mt-3">
        <Badge variant="comp">📍 {posting.location || "Location not stated"}</Badge>
        <Badge variant="future">🧭 {arrangement(posting)}</Badge>
        {salary && <Badge variant="demand">💰 {salary}</Badge>}
        {posting.matched_terms.length > 0 && (
          <Badge variant="match">🎯 Title says: {posting.matched_terms.join(", ")}</Badge>
        )}
      </div>

      {posting.excerpt && (
        <p className="mt-2 text-sm leading-relaxed text-slate-600">
          {truncate(posting.excerpt, 150)}
        </p>
      )}

      <JobClassification posting={posting} />

      <p className="mt-3 text-xs text-slate-500">
        {posting.published
          ? `🕒 Posted ${formatDate(posting.published)}`
          : "🕒 Posting date not provided"}
        {level && (
          <>
            <span className="mx-2 text-slate-300">|</span>
            Level: {level}
          </>
        )}
        <span className="mx-2 text-slate-300">|</span>
        Similarity {posting.similarity.toFixed(2)}
      </p>

      <div className="mt-auto space-y-2 pt-4">
        <a
          href={posting.url}
          target="_blank"
          rel="noreferrer noopener"
          className="btn btn-primary w-full"
        >
          Apply on {board} ↗
        </a>
        <SaveJobButton posting={posting} />
        {attribution && (
          /**
           * Adzuna's terms: every displayed advert carries the word "Adzuna" as a
           * hyperlink to their site, at least 116×23 px. So this is a requirement,
           * not a courtesy, and the size is part of it — hence the explicit minimum
           * rather than whatever the text happens to measure.
           */
          <a
            href={attribution.url}
            target="_blank"
            rel="noreferrer noopener"
            className="flex min-h-[23px] w-full min-w-[116px] items-center justify-center rounded border border-slate-200 px-3 text-xs font-semibold text-slate-600 hover:underline"
          >
            Jobs by {attribution.label}
          </a>
        )}
      </div>
    </div>
  );
}
