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
  EMPLOYMENT_OPTIONS,
  EXPERIENCE_OPTIONS,
  LOCATION_MAX_LENGTH,
  QUERY_MAX_LENGTH,
  SEARCH_LIMIT,
  arrangementFromParam,
  employmentFromParam,
  employmentParam,
  harvestNote,
  hasAnyFilter,
  locationOptionLabel,
  postingParams,
  preferredLocationLabel,
  profileQuery,
  providerNote,
  relaxedNote,
  remoteParam,
  staleNote,
} from "@/lib/jobs";
import { useDocumentTitle } from "@/lib/hooks";
import { useProfile } from "@/state/ProfileContext";

/**
 * Live postings collected from the public job boards (see `backend/services/
 * job_feed.py`) and served by `GET /jobs/search`.
 *
 * Every field on the form is a real endpoint parameter: the backend applies the
 * filters and the words to the whole `job_role` collection and reports how many
 * postings are left (`matched`), so the page no longer filters a ranked window
 * down and then has to explain why its numbers only covered fifty postings. The
 * location field's suggestions are the collection's own place vocabulary
 * (`GET /jobs/locations`), not the places the last search happened to return — and
 * that same read carries the Indian hubs, offered as preferences so the home
 * market is visible without typing it.
 *
 * Two of the filters read fields no board publishes a vocabulary for.
 * *Experience* and *employment type* are translations of the boards' own wording
 * ("full time, permanent" answers both of those buckets), and their rules live in
 * `services/job_service.py`.
 *
 * Each card carries the classifier's reading of its advert and offers to make one
 * for a listing nobody has read yet (`services/classification.py`). That reading is
 * deliberately *not* a filter here: it exists for a small share of the feed — the
 * classifier reads one advert per request, on demand — so a category search would
 * answer from almost nothing and read as "no such jobs" when the truth is "not read
 * yet". The form above narrows on the fields the boards themselves publish.
 *
 * The response also says what each provider contributed and why any of them is
 * missing (`sources`), which is shown as a notice: Adzuna needs a key, and a feed
 * with no Indian postings and no explanation would read as "there are none".
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
    employment: employmentFromParam(params.get("employment_type")),
  };
}

export default function JobsPage() {
  useDocumentTitle("Live jobs");

  const { profile } = useProfile();
  const [params, setParams] = useSearchParams();
  const committed = useMemo(() => filtersFromParams(params), [params]);
  const { role, location, experience, arrangement, employment } = committed;

  // The form mirrors the URL and follows it when it changes underneath us —
  // e.g. a second "Explore Jobs" click on an already-mounted page.
  const [draft, setDraft] = useState<JobFilters>(committed);
  useEffect(() => {
    setDraft({ role, location, experience, arrangement, employment });
  }, [role, location, experience, arrangement, employment]);

  const searchParams = useMemo(() => postingParams(committed), [committed]);

  const jobsQuery = useQuery({
    queryKey: ["jobs", searchParams],
    queryFn: () => endpoints.searchJobs(searchParams, SEARCH_LIMIT),
    enabled: hasAnyFilter(committed),
    staleTime: 5 * 60 * 1000,
  });

  const ranked = jobsQuery.data?.results ?? [];

  // The place vocabulary comes from the collection, not from this page's results:
  // suggestions built from the fifty postings a search happened to return offered
  // whatever ran last, and nothing at all on a fresh page.
  const locationsQuery = useQuery({
    queryKey: ["job-locations"],
    queryFn: endpoints.jobLocations,
    staleTime: 30 * 60 * 1000,
  });
  const places = locationsQuery.data?.locations ?? [];
  // The Indian hubs, offered whether or not the boards carry them — see the note
  // under the row. A preference with a count of 0 is stated, not clickable.
  const preferred = locationsQuery.data?.preferred ?? [];

  const update = (patch: Partial<JobFilters>) => setDraft({ ...draft, ...patch });

  const commit = (filters: JobFilters) => {
    const next = new URLSearchParams();
    if (filters.role.trim()) next.set("role", filters.role.trim());
    if (filters.location.trim()) next.set("location", filters.location.trim());
    if (filters.experience !== ANY_EXPERIENCE) next.set("experience", filters.experience);
    const remote = remoteParam(filters.arrangement);
    if (remote) next.set("remote", remote);
    const employment = employmentParam(filters.employment);
    if (employment) next.set("employment_type", employment);
    setParams(next);
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    commit(draft);
  };

  // A preference is a one-click search, like "Use my profile": picking one fills
  // the location field and commits it, so the reader does not also have to press
  // Search. Only the places the feed actually holds are pickable — a hub with no
  // postings says so rather than leading to an empty page.
  const pickLocation = (value: string) => {
    setDraft((current) => ({ ...current, location: value }));
    commit({ ...draft, location: value });
  };

  // The questionnaire answers the semantic role match already runs on, pointed at
  // the live boards: one click searches with the goal, the interests and a few
  // skills (see `profileQuery`) instead of typing a role.
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
  // Live postings age silently, so the results carry their own harvest date —
  // and an explicit warning once the backend judges it too old to trust.
  const harvest = harvestNote(data?.freshness);
  const stale = staleNote(data?.freshness);
  // The words are a condition, so the page can be smaller than what was asked
  // for — and says so rather than letting the reader assume it searched the lot.
  const loosened = relaxedNote(data?.relaxed, committed.role);
  // A board the harvest could not read is a fact about the feed, so it is stated
  // where the feed is: without this, "no postings in India" and "this server has
  // no Adzuna key" look exactly the same to the person reading the page.
  const providers = providerNote(data?.sources);

  return (
    <div>
      <h1 className="section-title">💼 Live Tech Jobs</h1>
      <p className="caption mt-1">
        Live postings from the public job boards — <strong>Adzuna</strong>, which covers
        the Indian market, plus Himalayas and Arbeitnow. The boards rotate their
        openings, so each search shows when the postings were harvested.
      </p>

      <form
        onSubmit={submit}
        className="card mt-5 mb-3 grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-3"
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
            placeholder="e.g. Bangalore, India, Remote"
            onChange={(event) => update({ location: event.target.value })}
          />
          <datalist id="job-location-suggestions">
            {places.map((place) => (
              <option
                key={place.value}
                value={place.value}
                label={locationOptionLabel(place.count)}
              />
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

        <SelectField
          label="Employment type"
          value={draft.employment}
          options={EMPLOYMENT_OPTIONS}
          onChange={(value) => update({ employment: value })}
        />

        <div className="flex flex-col gap-2 sm:col-span-2 lg:col-span-3">
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

      {preferred.length > 0 && (
        <div className="mb-5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="label">Indian market</span>
            {preferred.map((place) => {
              const live = place.count > 0;
              return (
                <button
                  key={place.value}
                  type="button"
                  className={`chip chip-off ${live ? "" : "cursor-not-allowed opacity-60"}`}
                  disabled={!live}
                  onClick={() => pickLocation(place.value)}
                >
                  {place.value}
                  <span className="ml-1.5 text-xs font-normal text-slate-500">
                    {preferredLocationLabel(place.count)}
                  </span>
                </button>
              );
            })}
          </div>
          <p className="caption mt-2">Counts are live — click a hub to search it.</p>
        </div>
      )}

      <p className="caption mb-5">
        Every word you type must appear in the posting. Nothing here is a career-fit
        score — that is what{" "}
        <Link className="font-semibold text-brand-700 hover:underline" to="/matches">
          My Matches
        </Link>{" "}
        is for.
      </p>

      {providers && (
        <div className="mb-5">
          <Alert tone="warning" title="A job provider could not be read">
            {providers}
          </Alert>
        </div>
      )}

      {!searching ? (
        <EmptyState
          icon="💼"
          title="Search the live boards"
          description="Type a role above, or open Jobs from any card in My Matches. A filter on its own is enough."
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
                  ? `None of the ${data.indexed} indexed postings match. Try a broader location, fewer words, or drop a filter.`
                  : `${data.matched} postings match, but none were returned for this page. Try broader words.`
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
                search · {data?.indexed ?? 0} postings indexed
              </p>
              <p className="caption">
                Ranked by similarity to “{data?.query}”. Cards link straight to the board
                that published them.
              </p>
              {loosened && (
                <div className="mt-3">
                  <Alert tone="info" title="No posting says all of your words">
                    {loosened}
                  </Alert>
                </div>
              )}
              {harvest && <p className="caption mt-1">🗓️ {harvest}</p>}
              {stale && (
                <div className="mt-3">
                  <Alert tone="warning" title="These postings are getting old">
                    {stale}
                  </Alert>
                </div>
              )}

              <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
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
