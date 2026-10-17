import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import Alert from "@/components/Alert";
import EmptyState from "@/components/EmptyState";
import JobCard from "@/components/JobCard";
import SelectField from "@/components/SelectField";
import { QueryState } from "@/components/QueryState";
import * as endpoints from "@/api/endpoints";
import type { JobFilters } from "@/lib/jobs";
import {
  ANY_EXPERIENCE,
  EXPERIENCE_OPTIONS,
  QUERY_MAX_LENGTH,
  SEARCH_LIMIT,
  buildQuery,
  hasNarrowingFilters,
  locationSuggestions,
  refinePostings,
} from "@/lib/jobs";
import { useDocumentTitle } from "@/lib/hooks";

/**
 * Live postings collected from the public job boards (see `backend/services/
 * job_feed.py`) and served by `GET /jobs/search`.
 *
 * The URL is the committed search — `/jobs?role=…&location=…&experience=…` — so
 * the "Explore Jobs" action on a match card can prefill it, the page survives a
 * refresh, and links to it are shareable. Submitting the form rewrites the URL;
 * the fields stay local until then, so typing costs no requests.
 */
function filtersFromParams(params: URLSearchParams): JobFilters {
  return {
    role: params.get("role") ?? "",
    location: params.get("location") ?? "",
    experience: params.get("experience") || ANY_EXPERIENCE,
  };
}

export default function JobsPage() {
  useDocumentTitle("Live jobs");

  const [params, setParams] = useSearchParams();
  const committed = useMemo(() => filtersFromParams(params), [params]);
  const { role, location, experience } = committed;

  // The form mirrors the URL and follows it when it changes underneath us —
  // e.g. a second "Explore Jobs" click on an already-mounted page.
  const [draft, setDraft] = useState<JobFilters>(committed);
  useEffect(() => {
    setDraft({ role, location, experience });
  }, [role, location, experience]);

  const query = buildQuery(committed);

  const jobsQuery = useQuery({
    queryKey: ["jobs", query],
    queryFn: () => endpoints.searchJobs(query, SEARCH_LIMIT),
    enabled: query.length > 0,
    staleTime: 5 * 60 * 1000,
  });

  const ranked = useMemo(() => jobsQuery.data?.results ?? [], [jobsQuery.data]);
  const visible = useMemo(() => refinePostings(ranked, committed), [ranked, committed]);
  const suggestions = useMemo(() => locationSuggestions(ranked), [ranked]);

  const update = (patch: Partial<JobFilters>) => setDraft({ ...draft, ...patch });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const next = new URLSearchParams();
    if (draft.role.trim()) next.set("role", draft.role.trim());
    if (draft.location.trim()) next.set("location", draft.location.trim());
    if (draft.experience !== ANY_EXPERIENCE) next.set("experience", draft.experience);
    setParams(next);
  };

  const clearNarrowing = () => {
    const next = new URLSearchParams();
    if (role.trim()) next.set("role", role.trim());
    setParams(next);
  };

  const data = jobsQuery.data;
  const filteredAway = data ? data.results.length - visible.length : 0;

  return (
    <div>
      <h1 className="section-title">💼 Live Tech Jobs</h1>
      <p className="caption mt-1">
        Currently-open postings collected from the public Himalayas and Arbeitnow job
        boards — live listings, not the curated role catalog.
      </p>

      <form
        onSubmit={submit}
        className="card mt-5 mb-3 grid gap-3 p-4 lg:grid-cols-[2fr_1.4fr_1.4fr_auto] lg:items-end"
      >
        <label className="block">
          <span className="label">Role or keywords</span>
          <input
            className="input"
            value={draft.role}
            maxLength={QUERY_MAX_LENGTH}
            placeholder="e.g. Kubernetes Engineer, Data Analyst"
            onChange={(event) => update({ role: event.target.value })}
          />
        </label>

        <label className="block">
          <span className="label">Location</span>
          <input
            className="input"
            value={draft.location}
            list="job-location-suggestions"
            placeholder="e.g. Berlin, Remote"
            onChange={(event) => update({ location: event.target.value })}
          />
          <datalist id="job-location-suggestions">
            {suggestions.map((value) => (
              <option key={value} value={value} />
            ))}
          </datalist>
        </label>

        <SelectField
          label="Experience"
          value={draft.experience}
          options={EXPERIENCE_OPTIONS}
          onChange={(value) => update({ experience: value })}
        />

        <div>
          <button type="submit" className="btn btn-primary w-full" disabled={!buildQuery(draft)}>
            🔎 Search jobs
          </button>
        </div>
      </form>

      <p className="caption mb-5">
        The backend takes one search string, so all three fields steer the semantic ranking
        together; location and experience then narrow the ranked postings shown below.
        “Relevance” is the similarity to your search text (0–1), not a career-fit score.
      </p>

      {!query ? (
        <EmptyState
          icon="💼"
          title="Search the live boards"
          description="Type a role above, or open Jobs from any card in My Matches to start from a role you already matched."
          action={
            <Link to="/matches" className="btn btn-primary">
              Go to My Matches
            </Link>
          }
        />
      ) : (
        <QueryState
          isLoading={jobsQuery.isLoading}
          error={jobsQuery.error}
          loadingLabel="Searching live postings…"
        >
          {data && !data.available ? (
            <Alert tone="info" title="The job index has not been built on this server">
              Postings are collected by an explicit migration, so there is nothing to search
              until someone runs{" "}
              <code className="rounded bg-white px-1.5 py-0.5 text-xs">
                python -m scripts.ingest_jobs
              </code>{" "}
              on the backend.
            </Alert>
          ) : data && data.count === 0 ? (
            <EmptyState
              icon="🔍"
              title="No postings matched that search"
              description="The index ranks the whole collection by meaning, so try broader words or drop the filters."
            />
          ) : (
            <>
              <p className="mb-3 text-sm font-semibold text-slate-700">
                Showing {visible.length} of {data?.count ?? 0} ranked postings for “
                {data?.query}”
              </p>

              {visible.length > 0 && filteredAway > 0 && hasNarrowingFilters(committed) && (
                <div className="mb-4">
                  <Alert tone="warning">
                    Your location/experience filters removed {filteredAway} of these{" "}
                    {data?.results.length} ranked postings.{" "}
                    <button
                      type="button"
                      onClick={clearNarrowing}
                      className="font-semibold underline"
                    >
                      Clear location &amp; experience
                    </button>
                  </Alert>
                </div>
              )}

              {visible.length === 0 ? (
                <EmptyState
                  icon="🧭"
                  title="Nothing left after filtering"
                  description={`None of the ${data?.count ?? 0} postings the index ranked match your location and experience filters — those filters only see that ranked window. Clear them, or reword your search.`}
                  action={
                    <button type="button" onClick={clearNarrowing} className="btn btn-primary">
                      Clear location &amp; experience
                    </button>
                  }
                />
              ) : (
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {visible.map((posting) => (
                    <JobCard key={posting.id} posting={posting} />
                  ))}
                </div>
              )}
            </>
          )}
        </QueryState>
      )}

      <div className="mt-8 border-t border-slate-200 pt-5">
        <p className="caption">
          Each card links straight to the board that published it. CareerCompass stores the
          postings locally and never applies on your behalf.
        </p>
        <div className="mt-4 flex flex-wrap gap-3">
          <Link to="/matches" className="btn btn-secondary">
            ← My Matches
          </Link>
          <Link to="/roles" className="btn btn-secondary">
            Explore All Roles →
          </Link>
        </div>
      </div>
    </div>
  );
}
