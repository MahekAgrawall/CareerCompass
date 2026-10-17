import { Link } from "react-router-dom";

import Badge from "./Badge";
import type { MatchResult, Role } from "@/api/types";
import { truncate } from "@/lib/format";
import { useCompare } from "@/state/CompareContext";

interface RoleCardProps {
  role: Role;
  match?: MatchResult;
  /** Disables the compare control when the comparison tray is full. */
  onCompareFull?: () => void;
}

/** One component of the match score, shown as a 0-100 bar. */
function ScoreBar({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-[4.5rem] shrink-0 text-slate-500">{label}</span>
      <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-200">
        <span className="block h-full rounded-full bg-brand-500" style={{ width: `${value}%` }} />
      </span>
      <span className="w-8 shrink-0 text-right font-semibold text-slate-700">{value}%</span>
    </div>
  );
}

export default function RoleCard({ role, match, onCompareFull }: RoleCardProps) {
  const { isSelected, add, toggle, count, max } = useCompare();
  const selected = isSelected(role.id);

  const handleCompare = () => {
    if (selected) {
      toggle(role);
      return;
    }
    if (count >= max) {
      onCompareFull?.();
      return;
    }
    if (!add(role)) onCompareFull?.();
  };

  const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;
  const matchSummary = match
    ? `${plural(match.matched_interests.length, "interest")} · ${plural(match.matched_skills.length, "skill")}`
    : "";
  const extraSuggestions = match ? match.suggested_skills.length - 4 : 0;

  const sal = role.salary;

  return (
    <div className="card card-hover flex h-full flex-col p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-base font-bold text-slate-900">
            <span aria-hidden="true">{role.icon}</span> {role.title}
          </h3>
          <p className="mt-0.5 text-xs text-slate-500">
            {role.category} • {role.niche_category || "Engineering"}
          </p>
        </div>
        {match ? (
          <Badge variant="match">⭐ {match.score}% Match</Badge>
        ) : role.is_niche ? (
          <Badge variant="niche">🎯 Niche</Badge>
        ) : null}
      </div>

      <div className="mt-3">
        <Badge variant="demand">{role.market_demand}</Badge>
        <Badge variant="comp">{role.competition_level}</Badge>
        <Badge variant="future">AI Future: {role.future_relevance.split("(")[0].trim()}</Badge>
      </div>

      <p className="mt-2 text-sm leading-relaxed text-slate-600">{truncate(role.description, 125)}</p>

      {match && (
        <details className="mt-2.5 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs">
          <summary className="cursor-pointer font-semibold text-slate-600">
            Why this matched · {matchSummary}
          </summary>
          <div className="mt-2 space-y-2 text-slate-600">
            <ScoreBar label="Interests" value={match.interest_score} />
            <ScoreBar label="Skills" value={match.skill_score} />
            <p>
              <span className="font-semibold text-slate-700">Interests matched: </span>
              {match.matched_interests.join(", ")}
            </p>
            <p>
              <span className="font-semibold text-slate-700">Skills this role uses: </span>
              {match.matched_skills.length > 0 ? match.matched_skills.join(", ") : "none of your current skills yet"}
            </p>
            {match.suggested_skills.length > 0 && (
              <p>
                <span className="font-semibold text-slate-700">Add to raise this match: </span>
                {match.suggested_skills.slice(0, 4).join(", ")}
                {extraSuggestions > 0 && ` +${extraSuggestions} more`}
              </p>
            )}
            {match.recalled_by.includes("semantic") && (
              <p>
                <span className="font-semibold text-slate-700">How it was found: </span>
                {match.recalled_by.includes("keyword")
                  ? "your interests, and by meaning in the role index"
                  : "by meaning in the role index — your interests do not overlap this role yet"}
                {match.semantic_similarity !== null &&
                  ` · similarity ${match.semantic_similarity.toFixed(2)}`}
              </p>
            )}
          </div>
        </details>
      )}

      <p className="mt-3 text-sm font-semibold text-slate-700">
        💰 Fresher: ₹{sal.fresher_0_1.min}–{sal.fresher_0_1.max} LPA
        <span className="mx-2 font-normal text-slate-300">|</span>
        1–3y: ₹{sal.mid_1_3.min}–{sal.mid_1_3.max} LPA
      </p>

      <div className="mt-auto flex gap-2 pt-4">
        <Link to={`/roles/${role.id}`} className="btn btn-primary flex-1">
          View Specs & Roadmap
        </Link>
        <button
          type="button"
          onClick={handleCompare}
          className="btn btn-secondary flex-1"
          aria-pressed={selected}
        >
          {selected ? "✓ Added" : "⚖️ Compare"}
        </button>
      </div>
    </div>
  );
}
