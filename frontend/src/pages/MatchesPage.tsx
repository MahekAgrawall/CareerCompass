import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import Alert from "@/components/Alert";
import EmptyState from "@/components/EmptyState";
import RoleCard from "@/components/RoleCard";
import SelectField from "@/components/SelectField";
import { QueryState } from "@/components/QueryState";
import * as endpoints from "@/api/endpoints";
import type { MatchResult } from "@/api/types";
import { demandRank } from "@/lib/format";
import { useDocumentTitle } from "@/lib/hooks";
import { useFlash } from "@/lib/useFlash";
import { useProfile } from "@/state/ProfileContext";
import { useCompare } from "@/state/CompareContext";

type SortKey = "Best match" | "Fresher salary (high → low)" | "Market demand";
const SORT_OPTIONS: SortKey[] = ["Best match", "Fresher salary (high → low)", "Market demand"];

export default function MatchesPage() {
  useDocumentTitle("My matches");
  const { profile } = useProfile();
  const { count } = useCompare();
  const { message, flash } = useFlash();
  const [query, setQuery] = useState("");
  const [sortBy, setSortBy] = useState<SortKey>("Best match");

  const interestsKey = profile?.interests.join("|") ?? "";
  const skillsKey = profile?.current_skills.join("|") ?? "";
  // Extra context for the semantic recall stage only: it decides which roles
  // surface, never how they score (that stays the published 65/35 formula).
  const recallContext = {
    careerGoal: profile?.career_goal ?? "",
    experience: profile?.experience ?? "",
    workMode: profile?.work_mode ?? "",
  };
  const contextKey = Object.values(recallContext).join("|");
  const canMatch = Boolean(profile && profile.interests.length > 0);

  // Matching itself is deterministic and instant — fetch it on its own.
  const resultsQuery = useQuery({
    queryKey: ["matches", interestsKey, skillsKey, contextKey],
    queryFn: () => endpoints.matchRoles(profile!.interests, profile!.current_skills, false, recallContext),
    enabled: canMatch,
    staleTime: Infinity,
  });

  // The AI-written assessment is supplementary: load it separately so a slow or
  // unavailable model never blocks the ranked results.
  const explanationQuery = useQuery({
    queryKey: ["match-explanation", interestsKey, skillsKey, contextKey],
    queryFn: () => endpoints.matchRoles(profile!.interests, profile!.current_skills, true, recallContext),
    enabled: canMatch,
    staleTime: Infinity,
    retry: 0,
    select: (data) => data.explanation,
  });

  const display = useMemo(() => {
    const results = resultsQuery.data?.results ?? [];
    const q = query.trim().toLowerCase();

    const filtered = q
      ? results.filter((item) => {
          const r = item.role;
          const haystack = [r.title, r.description, r.category, ...r.skills.must_have, ...r.top_companies];
          return haystack.some((value) => String(value).toLowerCase().includes(q));
        })
      : results;

    const sorted = [...filtered];
    if (sortBy === "Fresher salary (high → low)") {
      sorted.sort((a, b) => b.role.salary.fresher_0_1.max - a.role.salary.fresher_0_1.max);
    } else if (sortBy === "Market demand") {
      sorted.sort((a, b) => demandRank(b.role.market_demand) - demandRank(a.role.market_demand));
    }
    return sorted;
  }, [resultsQuery.data, query, sortBy]);

  if (!profile || profile.interests.length === 0) {
    return (
      <EmptyState
        icon="🎯"
        title="No profile yet"
        description="Build your candidate profile first — matching is driven strictly by the interests you choose."
        action={
          <Link to="/profile" className="btn btn-primary">
            Build Candidate Profile
          </Link>
        }
      />
    );
  }

  const results = resultsQuery.data?.results ?? [];
  const explanation = explanationQuery.data;

  return (
    <div>
      <h1 className="section-title">🎯 Step 2 — Roles Matched for {profile.name || "You"}</h1>
      <p className="caption mt-1">
        Filtered strictly according to your selected career interests and current technical baseline.
      </p>
      {resultsQuery.data && (
        <p className="caption mt-1">
          Every match is explained: score = {resultsQuery.data.interest_weight}% interest fit +{" "}
          {resultsQuery.data.skill_weight}% skill fit. Open “Why this matched” on any card to check the arithmetic.
        </p>
      )}

      <div className="my-4 space-y-3">
        {message && <Alert tone="warning">{message}</Alert>}
        {explanation && (
          <Alert tone="info" title="Strategic Fit Assessment">
            {explanation}
          </Alert>
        )}
      </div>

      <QueryState isLoading={resultsQuery.isLoading} error={resultsQuery.error} loadingLabel="Matching roles…">
        {results.length === 0 ? (
          <EmptyState
            icon="🔍"
            title="No strict matches"
            description="No roles strictly matched your selected interest combination. Try broadening your interests or explore the full catalog."
            action={
              <div className="flex flex-wrap justify-center gap-3">
                <Link to="/profile" className="btn btn-secondary">
                  ← Edit Interests
                </Link>
                <Link to="/roles" className="btn btn-primary">
                  Browse All Roles
                </Link>
              </div>
            }
          />
        ) : (
          <>
            <div className="mb-4 grid gap-3 sm:grid-cols-[2.4fr_1.4fr]">
              <input
                className="input"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="🔎 Search your matches by role, skill, or company…"
                aria-label="Filter matches"
              />
              <SelectField
                label="Sort matches"
                value={sortBy}
                options={SORT_OPTIONS}
                onChange={(value) => setSortBy(value as SortKey)}
              />
            </div>

            <p className="mb-4 text-sm font-semibold text-slate-700">
              Showing {display.length} of {results.length} matched roles
            </p>

            {display.length === 0 ? (
              <Alert tone="warning">
                None of your matches match that search. Clear the filter to see all matches again.
              </Alert>
            ) : (
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {display.map((item: MatchResult) => (
                  <RoleCard
                    key={item.role.id}
                    role={item.role}
                    match={item}
                    onCompareFull={() => flash("Comparison max is 3 roles.")}
                  />
                ))}
              </div>
            )}
          </>
        )}
      </QueryState>

      <hr className="my-7 border-slate-200" />

      <div className="flex flex-wrap gap-3">
        <Link to="/profile" className="btn btn-secondary">
          ← Modify Profile
        </Link>
        {count > 0 && (
          <Link to="/compare" className="btn btn-primary">
            Compare Selected Roles ({count})
          </Link>
        )}
        <Link to="/roles" className="btn btn-secondary ml-auto">
          Explore All Roles Catalog →
        </Link>
      </div>
    </div>
  );
}
