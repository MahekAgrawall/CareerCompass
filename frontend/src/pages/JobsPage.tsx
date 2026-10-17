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
  ARRANGEMENT_OPTIONS,
  EXPERIENCE_OPTIONS,
  LOCATION_MAX_LENGTH,
  QUERY_MAX_LENGTH,
  SEARCH_LIMIT,
  arrangementFromParam,
  hasAnyFilter,
  locationSuggestions,
  postingParams,
  profileQuery,
  remoteParam,
} from "@/lib/jobs";
import { useDocumentTitle } from "@/lib/hooks";
import { useProfile } from "@/state/ProfileContext";

/**
 * Live postings collected from the public job boards (see `backend/services/
 * job_feed.py`) and served by `GET /jobs/search`.
 *
 * Every field on the form is a real endpoint parameter: the backend applies the
 * filters to the whole `job_role` collection and reports how many postings are
 * left (`matched`), so the page no longer filters a ranked window down and then
 * has to explain why its numbers only covered fifty postings.
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
    arrangement: arrangementFromParam(params.get("remote")),
  };
}

export default function JobsPage() {
  useDocumentTitle("Live jobs");

  const { profile } = useProfile();
  const [params, setParams] = useSearchParams();
  const committed = useMemo(() => filtersFromParams(params), [params]);
  const { role, location, experience, arrangement } = committed;

  // The form mirrors the URL and follows it when it changes underneath us —
  // e.g. a second "Explore Jobs" click on an already-mounted page.
  const [draft, setDraft] = useState<JobFilters>(committed);
  useEffect(() => {
    setDraft({ role, location, experience, arrangement });
  }, [role, location, experience, arrangement]);

  const searchParams = useMemo(() => postingParams(committed), [committed]);

  const jobsQuery = useQuery({
    queryKey: ["jobs", searchParams],
    queryFn: () => endpoints.searchJobs(searchParams, SEARCH_LIMIT),
    enabled: hasAnyFilter(committed),
    staleTime: 5 * 60 * 1000,
  });

  const ranked = jobsQuery.data?.results ?? [];
  const suggestions = useMemo(() => locationSuggestions(ranked), [ranked]);

  const update = (patch: Partial<JobFilters>) => setDraft({ ...draft, ...patch });

  const commit = (filters: JobFilters) => {
    const next = new URLSearchParams();
    if (filters.role.trim()) next.set("role", filters.role.trim());
    if (filters.location.trim()) next.set("location", filters.location.trim());
    if (filters.experience !== ANY_EXPERIENCE) next.set("experience", filters.experience);
    const remote = remoteParam(filters.arrangement);
    if (remote) next.set("remote", remote);
    setParams(next);
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    commit(draft);
  };

  // The questionnaire answers the semantic role match already runs on, pointed at
  // the live boards: one click searches with them instead of typing a role.
  const canPersonalise = Boolean(profile?.interests?.length);
  const searchWithProfile = () => {
    const role = profileQuery(profile ?? {});
    setDraft((current) => ({ ...current, role }));
    commit({ ...draft, role });
  };

  const clearFilters = () => {
    const next = new URLSearchParams();
    if (role.trim()) next.set("role", role.trim());
    setParams(next);
  };

  const data = jobsQuery.data;
  const searching = hasAnyFilter(committed);

  return (
    <div>
      <h1 className="section-title">💼 Live Tech Jobs</h1>
      <p className="caption mt-1">
        Currently-open postings collected from the public Himalayas and Arbeitnow job
        boards — live listings, not the curated role catalog.
      </p>

      <form
        onSubmit={submit}
        className="card mt-5 mb-3 grid gap-3 p-4 lg:grid-cols-[2fr_1.2fr_1.2fr_1.2fr_auto] lg:items-end"
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
            maxLength={LOCATION_MAX_LENGTH}
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

        <SelectField
          label="Work arrangement"
          value={draft.arrangement}
          options={ARRANGEMENT_OPTIONS}
          onChange={(value) => update({ arrangement: value })}
        />

        <div className="flex flex-col gap-2">
          <button type="submit" className="btn btn-primary w-full" disabled={!hasAnyFilter(draft)}>
            🔎 Search jobs
          </button>
          {canPersonalise && (
            <button type="button" className="btn btn-secondary w-full" onClick={searchWithProfile}>
              ✨ Use my profile
            </button>
          )}
        </div>
      </form>

      <p className="caption mb-5">
        Every field above is a real filter on the live board collection, applied by the
        backend before anything is ranked — so the counts below cover every posting held,
        not just the page you see. “Relevance” is the semantic similarity to your search
        text (or, when the search box is empty, to the filters) — not a career-fit score.
      </p>

      {!searching ? (
        <EmptyState
          icon="💼"
          title="Search the live boards"
          description="Type a role above, or open Jobs from any card in My Matches to start from a role you already matched. A filter on its own is enough — you do not have to type a role."
          action={
            canPersonalise ? (
              <button type="button" className="btn btn-primary" onClick={searchWithProfile}>
                ✨ Search with my profile
              </button>
            ) : (
              <Link to="/matches" className="btn btn-primary">
                Go to My Matches
              </Link>
            )
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
          ) : data && data.results.length === 0 ? (
            <EmptyState
              icon="🔍"
              title="No postings matched"
              description={
                data.matched === 0
                  ? `These filters were applied to all ${data.indexed} indexed postings and none of them match. Try a broader location, or drop the experience and arrangement filters.`
                  : `${data.matched} postings match your filters, but none of them ranked against that search text. Try broader words.`
              }
              action={
                <button type="button" onClick={clearFilters} className="btn btn-primary">
                  Clear filters
                </button>
              }
            />
          ) : (
            <>
              <p className="mb-1 text-sm font-semibold text-slate-700">
                Showing {data?.count ?? 0} of {data?.matched ?? 0} postings matching your
                filters · {data?.indexed ?? 0} postings indexed
              </p>
              <p className="caption mb-4">
                Ranked by similarity to “{data?.query}”. Each card links straight to the
                board that published it.
              </p>

              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {ranked.map((posting) => (
                  <JobCard key={posting.id} posting={posting} />
                ))}
              </div>
            </>
          )}
        </QueryState>
      )}

      <div className="mt-8 border-t border-slate-200 pt-5">
        <p className="caption">
          CareerCompass stores the postings locally and never applies on your behalf.
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
