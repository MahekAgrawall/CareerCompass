import { Link, useNavigate } from "react-router-dom";

import EmptyState from "@/components/EmptyState";
import SectionCard from "@/components/SectionCard";
import { useDocumentTitle } from "@/lib/hooks";
import { useCompare } from "@/state/CompareContext";

export default function ComparePage() {
  useDocumentTitle("Compare roles");
  const navigate = useNavigate();
  const { roles, clear } = useCompare();

  if (roles.length === 0) {
    return (
      <EmptyState
        icon="⚖️"
        title="Nothing to compare yet"
        description="Select up to 3 roles from the directory or your matches to benchmark them side by side."
        action={
          <Link to="/roles" className="btn btn-primary">
            Browse Roles Directory
          </Link>
        }
      />
    );
  }

  return (
    <div>
      <h1 className="section-title">⚖️ Compare Selected Roles Side-by-Side</h1>
      <p className="caption mt-1">Benchmarking {roles.length} technology career paths</p>
      <hr className="my-5 border-slate-200" />

      <div
        className="grid gap-4"
        style={{ gridTemplateColumns: `repeat(${Math.min(roles.length, 3)}, minmax(0, 1fr))` }}
      >
        {roles.map((role) => (
          <SectionCard key={role.id} className="flex flex-col p-5" hover>
            <h2 className="text-base font-bold text-slate-900">
              {role.icon} {role.title}
            </h2>
            <p className="caption mt-0.5">{role.category}</p>

            <hr className="my-3 border-slate-100" />
            <p className="text-sm text-slate-700">
              <strong>🔥 Demand:</strong> {role.market_demand}
            </p>
            <p className="text-sm text-slate-700">
              <strong>⚔️ Competition:</strong> {role.competition_level}
            </p>
            <p className="text-sm text-slate-700">
              <strong>🚀 10-Yr AI Future:</strong> {role.future_relevance.split("(")[0].trim()}
            </p>

            <hr className="my-3 border-slate-100" />
            <p className="text-sm font-semibold text-slate-800">💰 CTC (India)</p>
            <ul className="mt-1 space-y-0.5 text-sm text-slate-600">
              <li>• Fresher: ₹{role.salary.fresher_0_1.min}–{role.salary.fresher_0_1.max} LPA</li>
              <li>• 1–3 Yrs: ₹{role.salary.mid_1_3.min}–{role.salary.mid_1_3.max} LPA</li>
              <li>• 3+ Yrs: ₹{role.salary.senior_3_plus.min}–{role.salary.senior_3_plus.max} LPA</li>
            </ul>

            <hr className="my-3 border-slate-100" />
            <p className="text-sm font-semibold text-slate-800">🛠️ Must-Have Foundations</p>
            <ul className="mt-1 space-y-0.5 text-sm text-slate-600">
              {role.skills.must_have.slice(0, 4).map((skill) => (
                <li key={skill}>• {skill}</li>
              ))}
            </ul>

            <hr className="my-3 border-slate-100" />
            <p className="text-sm font-semibold text-slate-800">🏢 Top Hiring Firms</p>
            <p className="mt-1 text-sm text-slate-600">{role.top_companies.slice(0, 4).join(", ")}</p>

            <Link to={`/roadmap/${role.id}`} className="btn btn-primary mt-4 w-full">
              Generate Roadmap
            </Link>
          </SectionCard>
        ))}
      </div>

      <hr className="my-6 border-slate-200" />
      <div className="flex flex-wrap gap-3">
        <button type="button" onClick={() => navigate(-1)} className="btn btn-secondary">
          ← Back
        </button>
        <button type="button" onClick={clear} className="btn btn-danger ml-auto">
          🗑️ Clear Comparison
        </button>
      </div>
    </div>
  );
}
