import Badge from "./Badge";
import SaveJobButton from "./SaveJobButton";
import type { JobPosting } from "@/api/types";
import { formatDate, truncate } from "@/lib/format";
import { sourceLabel } from "@/lib/jobs";

/** How the board words the arrangement, e.g. "Remote · Full Time". */
function arrangement(posting: JobPosting): string {
  return [posting.remote ? "Remote" : "On-site / not stated", posting.employment_type.trim()]
    .filter(Boolean)
    .join(" · ");
}

/**
 * One live posting, as returned by `GET /jobs/search`.
 *
 * Unlike `RoleCard` these carry no fit score — only the index's cosine
 * `similarity` to the search text — so the card shows the posting's own facts and
 * links straight out to the original listing.
 */
export default function JobCard({ posting }: { posting: JobPosting }) {
  const board = sourceLabel(posting.source);
  const salary = posting.salary_text.trim();
  const level = posting.seniority.join(", ");

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
      </div>

      {posting.excerpt && (
        <p className="mt-2 text-sm leading-relaxed text-slate-600">
          {truncate(posting.excerpt, 150)}
        </p>
      )}

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
        Relevance {posting.similarity.toFixed(2)}
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
      </div>
    </div>
  );
}
