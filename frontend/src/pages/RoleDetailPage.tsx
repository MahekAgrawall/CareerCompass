import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import Badge from "@/components/Badge";
import MetricCard from "@/components/MetricCard";
import SectionCard from "@/components/SectionCard";
import { QueryState } from "@/components/QueryState";
import * as endpoints from "@/api/endpoints";
import { useDocumentTitle } from "@/lib/hooks";
import { useCompare } from "@/state/CompareContext";

export default function RoleDetailPage() {
  const { roleId = "" } = useParams();
  const { isSelected, add, toggle, count, max } = useCompare();

  const roleQuery = useQuery({
    queryKey: ["role", roleId],
    queryFn: () => endpoints.getRole(roleId),
    enabled: Boolean(roleId),
  });

  useDocumentTitle(roleQuery.data ? roleQuery.data.title : "Role details");

  const role = roleQuery.data;
  const selected = role ? isSelected(role.id) : false;

  const handleCompare = () => {
    if (!role) return;
    if (selected) {
      toggle(role);
      return;
    }
    if (count >= max || !add(role)) return;
  };

  return (
    <QueryState isLoading={roleQuery.isLoading} error={roleQuery.error} loadingLabel="Loading role…">
      {role && (
        <div>
          <h1 className="section-title">
            {role.icon} {role.title}
          </h1>
          <p className="caption mt-1">
            {role.category} • {role.niche_category || "Specialization"}
          </p>

          <div className="my-4 grid grid-cols-2 gap-4 rounded-xl border border-slate-200 bg-slate-50 px-5 py-4 text-center sm:grid-cols-4">
            <div>
              <p className="text-xs font-semibold uppercase text-slate-500">Market Demand</p>
              <p className="mt-1 font-bold text-red-600">{role.market_demand}</p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase text-slate-500">Competition Level</p>
              <p className="mt-1 font-bold text-amber-600">{role.competition_level}</p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase text-slate-500">10-yr AI Relevance</p>
              <p className="mt-1 font-bold text-green-600">{role.future_relevance}</p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase text-slate-500">Role Type</p>
              <p className="mt-1 font-bold text-purple-700">
                {role.is_niche ? "Niche Specialist 🎯" : "Mainstream Core 🏢"}
              </p>
            </div>
          </div>

          <p className="text-base leading-relaxed text-slate-600">{role.description}</p>

          <hr className="my-6 border-slate-200" />

          <h2 className="text-lg font-bold text-slate-900">💰 Compensation Benchmark (India)</h2>
          <div className="mt-3 grid gap-3 sm:grid-cols-3">
            <MetricCard label={`🌱 ${role.salary.fresher_0_1.label}`} value={`₹${role.salary.fresher_0_1.min}–${role.salary.fresher_0_1.max} LPA`} />
            <MetricCard label={`📈 ${role.salary.mid_1_3.label}`} value={`₹${role.salary.mid_1_3.min}–${role.salary.mid_1_3.max} LPA`} />
            <MetricCard label={`🚀 ${role.salary.senior_3_plus.label}`} value={`₹${role.salary.senior_3_plus.min}–${role.salary.senior_3_plus.max} LPA`} />
          </div>
          <p className="mt-2 text-xs italic text-slate-400">
            Source: Aggregated enterprise data from AmbitionBox, Glassdoor, and LinkedIn Indian Tech Index.
          </p>

          <hr className="my-6 border-slate-200" />

          <div className="grid gap-6 md:grid-cols-2">
            <div>
              <h2 className="text-lg font-bold text-slate-900">📋 Primary Responsibilities</h2>
              <ul className="mt-2 space-y-1.5 text-sm text-slate-600">
                {role.responsibilities.map((item) => (
                  <li key={item} className="flex gap-2">
                    <span className="text-brand-400">•</span>
                    <span>{item}</span>
                  </li>
                ))}
              </ul>

              <h2 className="mt-6 text-lg font-bold text-slate-900">🎓 Recommended Qualifications</h2>
              <ul className="mt-2 space-y-1.5 text-sm text-slate-600">
                {role.qualifications.map((item) => (
                  <li key={item} className="flex gap-2">
                    <span className="text-brand-400">•</span>
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div>
              <h2 className="text-lg font-bold text-slate-900">📈 Career Progression</h2>
              <ol className="mt-2 space-y-1.5 text-sm text-slate-600">
                {role.growth_path.map((step, index) => (
                  <li key={step} className="flex gap-2">
                    <span className="text-brand-400">
                      {index === 0 ? "🟢 Entry:" : index === role.growth_path.length - 1 ? "⭐ Apex:" : "↗️"}
                    </span>
                    <span>{step}</span>
                  </li>
                ))}
              </ol>

              <h2 className="mt-6 text-lg font-bold text-slate-900">🏢 Hiring Companies in India</h2>
              <p className="mt-2 text-sm text-slate-600">{role.top_companies.join(", ")}</p>
            </div>
          </div>

          <hr className="my-6 border-slate-200" />

          <h2 className="text-lg font-bold text-slate-900">🛠️ Required Technical Competencies</h2>
          <div className="mt-3 grid gap-4 sm:grid-cols-3">
            {[
              { title: "✅ Must-Have Foundations", items: role.skills.must_have },
              { title: "⭐ Competitive Accelerators", items: role.skills.good_to_have },
              { title: "💡 Advanced Niche Strengths", items: role.skills.can_have },
            ].map((group) => (
              <SectionCard key={group.title} className="p-4">
                <h3 className="text-sm font-bold text-slate-800">{group.title}</h3>
                <ul className="mt-2 space-y-1.5 text-sm text-slate-600">
                  {group.items.map((item) => (
                    <li key={item} className="flex gap-2">
                      <span className="text-brand-400">•</span>
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              </SectionCard>
            ))}
          </div>

          {role.is_niche && (
            <div className="mt-4">
              <Badge variant="niche">🎯 Niche Specialist role</Badge>
            </div>
          )}

          <hr className="my-6 border-slate-200" />

          <div className="flex flex-wrap gap-3">
            <Link to={`/roadmap/${role.id}`} className="btn btn-primary flex-1 sm:flex-none">
              Generate AI Skill Roadmap
            </Link>
            <Link to={`/tracker/${role.id}`} className="btn btn-secondary">
              📅 Open Study Hours Tracker
            </Link>
            <button type="button" onClick={handleCompare} className="btn btn-secondary" aria-pressed={selected}>
              {selected ? "✓ Added" : "⚖️ Compare"}
            </button>
            <Link to="/roles" className="btn btn-ghost ml-auto">
              ← Back
            </Link>
          </div>
        </div>
      )}
    </QueryState>
  );
}
