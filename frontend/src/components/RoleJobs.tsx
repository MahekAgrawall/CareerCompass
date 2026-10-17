import { useQuery } from "@tanstack/react-query";

import Alert from "@/components/Alert";
import * as endpoints from "@/api/endpoints";
import { formatDate } from "@/lib/format";
import { sourceLabel } from "@/lib/jobs";
import { useProfile } from "@/state/ProfileContext";

/**
 * The live postings nearest one catalogued role, ranked with the candidate's
 * questionnaire answers folded into the query (`POST /jobs/for-role`).
 *
 * Small on purpose: it renders a short list of links straight out to the board
 * that published each posting — CareerCompass stores the postings but never
 * applies on the candidate's behalf. The role card mounts it lazily (only when
 * the section is opened); the role detail page shows it in full.
 */
export default function RoleJobs({ roleId, limit = 5 }: { roleId: string; limit?: number }) {
  const { profile } = useProfile();

  const query = useQuery({
    queryKey: ["role-jobs", roleId, limit, profile ?? {}],
    queryFn: () => endpoints.jobsForRole(roleId, profile ?? {}, limit),
    staleTime: 5 * 60 * 1000,
  });

  if (query.isLoading) {
    return <p className="caption">Looking for live openings on the job boards…</p>;
  }

  if (query.error) {
    return <Alert tone="error">Could not load live openings right now.</Alert>;
  }

  const data = query.data;
  if (!data) return null;

  if (!data.available) {
    return (
      <Alert tone="info">
        This server has no job index yet — postings are loaded by an explicit migration:{" "}
        <code className="rounded bg-white px-1.5 py-0.5 text-xs">
          python -m scripts.ingest_jobs
        </code>
      </Alert>
    );
  }

  if (data.count === 0) {
    return <p className="caption">No live openings matched this role right now.</p>;
  }

  return (
    <ul className="space-y-2">
      {data.results.map((posting) => (
        <li key={posting.id} className="text-sm leading-relaxed">
          <a
            href={posting.url}
            target="_blank"
            rel="noreferrer noopener"
            className="font-semibold text-brand-700 hover:underline"
          >
            {posting.title} ↗
          </a>
          <span className="text-slate-500">
            {" — "}
            {posting.company || "Company not stated"}
            {posting.location ? ` · ${posting.location}` : ""}
            {posting.published ? ` · ${formatDate(posting.published)}` : ""}
            {` · ${sourceLabel(posting.source)}`}
          </span>
        </li>
      ))}
    </ul>
  );
}
