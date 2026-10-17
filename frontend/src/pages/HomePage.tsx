import { Link } from "react-router-dom";

import SectionCard from "@/components/SectionCard";
import { useDocumentTitle } from "@/lib/hooks";

const pillars = [
  {
    icon: "🎯",
    title: "Smart Interest Matching",
    body: "Ranks roles strictly on the interests and skills you actually have — 65% interest fit, 35% skill fit — and shows the arithmetic. Semantic recall can surface a role that matches the meaning of your profile, never a score you cannot check.",
  },
  {
    icon: "📊",
    title: "Market Intelligence",
    body: "Accurate Indian CTC trajectories (0-1y, 1-3y, 3+y), market competition levels, and 10-year AI relevance ratings.",
  },
  {
    icon: "📅",
    title: "Personalized Study Tracker",
    body: "Configurable study pace (weekdays vs weekends) with subtopic checklists and timeline completion projections.",
  },
];

export default function HomePage() {
  useDocumentTitle();

  return (
    <div>
      <section className="hero-card">
        <h1 className="mb-2.5 text-3xl font-extrabold tracking-[-0.02em] sm:text-[2.6rem]">
          Navigate Your Tech Career with Precision
        </h1>
        <p className="max-w-3xl text-lg leading-relaxed text-slate-400">
          CareerCompass maps your skills and interests to high-demand corporate and modern engineering
          roles in India — complete with compensation benchmarks, AI-generated roadmaps, and custom
          study trackers.
        </p>
      </section>

      <div className="grid gap-4 sm:grid-cols-3">
        {pillars.map((pillar) => (
          <SectionCard key={pillar.title} className="p-5" hover>
            <h3 className="text-base font-bold text-slate-900">
              <span aria-hidden="true">{pillar.icon}</span> {pillar.title}
            </h3>
            <p className="mt-2 text-sm leading-relaxed text-slate-500">{pillar.body}</p>
          </SectionCard>
        ))}
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-[1.6fr_1fr]">
        <SectionCard className="flex flex-col p-6" hover>
          <h3 className="text-lg font-bold text-slate-900">✨ Step 1: Discover Your Role Fit</h3>
          <p className="mt-2 text-sm text-slate-500">
            Take a 2-minute profile questionnaire to get matched with corporate tech specializations.
          </p>
          <Link to="/profile" className="btn btn-primary mt-5 w-full">
            Build Candidate Profile
          </Link>
        </SectionCard>

        <SectionCard className="flex flex-col p-6" hover>
          <h3 className="text-lg font-bold text-slate-900">📚 Explore All Roles</h3>
          <p className="mt-2 text-sm text-slate-500">
            Browse the catalog by category, demand or salary — then open any role for its
            roadmap and study tracker.
          </p>
          <Link to="/roles" className="btn btn-secondary mt-5 w-full">
            Open Role Directory
          </Link>
        </SectionCard>
      </div>
    </div>
  );
}
