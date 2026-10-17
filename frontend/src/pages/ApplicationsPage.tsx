import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import EmptyState from "@/components/EmptyState";
import { QueryState } from "@/components/QueryState";
import * as endpoints from "@/api/endpoints";
import type { ApplicationStatus, SavedJob } from "@/api/types";
import { APPLICATIONS_KEY, STAGES, groupByStage, stageCounts } from "@/lib/applications";
import { formatDate } from "@/lib/format";
import { useDocumentTitle } from "@/lib/hooks";

/** How the row words the arrangement, e.g. "Remote · Full Time". */
function arrangement(application: SavedJob): string {
  return [
    application.remote ? "Remote" : "On-site / not stated",
    application.employment_type.trim(),
  ]
    .filter(Boolean)
    .join(" · ");
}

/**
 * One filed posting: what it was, where it got to, and the two things the
 * candidate can still change about it.
 *
 * The note is local state until it is saved, so typing does not fire a request
 * per keystroke; every mutation invalidates the list, and the row re-reads the
 * server's copy afterwards rather than assuming the write went as planned.
 */
function ApplicationRow({ application }: { application: SavedJob }) {
  const queryClient = useQueryClient();
  const [note, setNote] = useState(application.note);

  useEffect(() => {
    setNote(application.note);
  }, [application.id, application.note]);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: APPLICATIONS_KEY });

  const move = useMutation({
    mutationFn: (status: ApplicationStatus) =>
      endpoints.updateApplication(application.id, { status }),
    onSuccess: invalidate,
  });
  const saveNote = useMutation({
    mutationFn: () => endpoints.updateApplication(application.id, { note }),
    onSuccess: invalidate,
  });
  const remove = useMutation({
    mutationFn: () => endpoints.deleteApplication(application.id),
    onSuccess: invalidate,
  });

  const moved = application.updated_at !== application.created_at;
  const failure = move.error ?? saveNote.error ?? remove.error;

  return (
    <div className="card p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-sm font-bold text-slate-900">{application.title}</h3>
          <p className="mt-1 text-xs text-slate-500">
            🏢 {application.company || "Company not stated"}
            <span className="mx-1.5 text-slate-300">|</span>
            📍 {application.location || "Location not stated"}
            <span className="mx-1.5 text-slate-300">|</span>
            🧭 {arrangement(application)}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            🕒 Filed {formatDate(application.created_at)}
            {moved && <> · Last moved {formatDate(application.updated_at)}</>}
            {application.salary_text.trim() && (
              <>
                <span className="mx-1.5 text-slate-300">|</span>
                💰 {application.salary_text.trim()}
              </>
            )}
          </p>
        </div>

        <div className="flex items-center gap-2">
          {application.url && (
            <a
              href={application.url}
              target="_blank"
              rel="noreferrer noopener"
              className="btn btn-secondary"
            >
              Open posting ↗
            </a>
          )}
          <button
            type="button"
            className="btn btn-secondary"
            disabled={remove.isPending}
            onClick={() => remove.mutate()}
          >
            {remove.isPending ? "Removing…" : "Remove"}
          </button>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-end gap-3">
        <label className="block w-full sm:w-52">
          <span className="label">Stage</span>
          <select
            className="input"
            value={application.status}
            disabled={move.isPending}
            onChange={(event) => move.mutate(event.target.value as ApplicationStatus)}
          >
            {STAGES.map((stage) => (
              <option key={stage.status} value={stage.status}>
                {stage.icon} {stage.label}
              </option>
            ))}
          </select>
        </label>

        <label className="block min-w-[16rem] flex-1">
          <span className="label">Note</span>
          <input
            className="input"
            value={note}
            maxLength={1000}
            placeholder="Recruiter call on Tuesday, asked for salary expectations…"
            onChange={(event) => setNote(event.target.value)}
          />
        </label>

        <button
          type="button"
          className="btn btn-secondary"
          disabled={note === application.note || saveNote.isPending}
          onClick={() => saveNote.mutate()}
        >
          {saveNote.isPending ? "Saving…" : "Save note"}
        </button>
      </div>

      {failure && (
        <p className="mt-2 text-xs text-rose-600">
          That change did not save: {failure.message}
        </p>
      )}
    </div>
  );
}

/**
 * Saved jobs and application tracking — the board a candidate comes back to.
 *
 * The live **Jobs** page is a stream they pass through; this page is the record
 * of what they kept from it and how far each application got. Every row is a
 * snapshot taken at save time (`lib/applications.ts` says why), so the board
 * still makes sense after the listing is filled and the index is rebuilt.
 *
 * The whole page is one query over one endpoint: the API returns the candidate's
 * rows and the page groups them by stage, so the counts at the top can never
 * disagree with the sections below them.
 */
export default function ApplicationsPage() {
  useDocumentTitle("Applications");

  const applications = useQuery({
    queryKey: APPLICATIONS_KEY,
    queryFn: endpoints.listApplications,
  });
  const rows = applications.data?.results ?? [];
  const counts = stageCounts(rows);
  const groups = groupByStage(rows);

  return (
    <div>
      <h1 className="section-title">📋 Applications</h1>
      <p className="caption mt-1">
        Every posting you saved from the live boards, and how far each one got. Each row keeps a copy
        of the posting as it looked when you saved it — the boards rotate their listings, and a saved
        job should not turn into a blank line when one disappears.
      </p>

      <QueryState
        isLoading={applications.isLoading}
        error={applications.error}
        loadingLabel="Loading your applications…"
      >
        {rows.length === 0 ? (
          <EmptyState
            icon="🔖"
            title="No saved jobs yet"
            description="Search the live boards and press “Save job” on anything worth keeping. From here you can move it along as the application progresses — applied, interview, offer."
            action={
              <Link to="/jobs" className="btn btn-primary">
                💼 Browse live jobs
              </Link>
            }
          />
        ) : (
          <>
            <div className="mt-5 flex flex-wrap items-center gap-2">
              {STAGES.map((stage) => {
                const count = counts.get(stage.status) ?? 0;
                return (
                  <span
                    key={stage.status}
                    className={`badge ${count > 0 ? "badge-match" : "badge-muted"}`}
                  >
                    {stage.icon} {stage.label}: {count}
                  </span>
                );
              })}
              <span className="text-xs text-slate-500">
                {rows.length} saved {rows.length === 1 ? "posting" : "postings"} in total.
              </span>
            </div>

            {groups
              .filter((group) => group.rows.length > 0)
              .map(({ stage, rows: stageRows }) => (
                <section key={stage.status} className="mt-7">
                  <h2 className="text-sm font-bold uppercase tracking-wide text-slate-600">
                    {stage.icon} {stage.label}{" "}
                    <span className="font-semibold text-slate-400">({stageRows.length})</span>
                  </h2>
                  <p className="caption">{stage.hint}</p>
                  <div className="mt-3 space-y-3">
                    {stageRows.map((row) => (
                      <ApplicationRow key={row.id} application={row} />
                    ))}
                  </div>
                </section>
              ))}
          </>
        )}
      </QueryState>

      <div className="mt-10 border-t border-slate-200 pt-5">
        <p className="caption">
          Saved jobs are private to your account, and CareerCompass never applies on your behalf. The
          study side of the same plan lives in the{" "}
          <Link to="/tracker" className="font-semibold text-brand-700 hover:underline">
            study tracker
          </Link>
          .
        </p>
        <div className="mt-4 flex flex-wrap gap-3">
          <Link to="/jobs" className="btn btn-secondary">
            💼 More live jobs
          </Link>
          <Link to="/tracker" className="btn btn-secondary">
            📅 Study tracker
          </Link>
        </div>
      </div>
    </div>
  );
}
