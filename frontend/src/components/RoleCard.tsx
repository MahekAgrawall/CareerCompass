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

  const matchedBits: string[] = [];
  if (match?.matched_skills?.length) {
    matchedBits.push(`skills: ${match.matched_skills.slice(0, 3).join(", ")}`);
  }
  if (match?.matched_interests?.length) {
    const pretty = match.matched_interests.slice(0, 2).map((i) => i.charAt(0).toUpperCase() + i.slice(1));
    matchedBits.push(`interests: ${pretty.join(", ")}`);
  }

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

      {matchedBits.length > 0 && (
        <p className="mt-2 text-xs text-slate-500">✓ Matched on {matchedBits.join("  ·  ")}</p>
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
