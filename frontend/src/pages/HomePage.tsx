import { Link } from "react-router-dom";

import FeatureExplorer from "@/components/FeatureExplorer";
import SectionCard from "@/components/SectionCard";
import { useDocumentTitle } from "@/lib/hooks";
import { useProfile } from "@/state/ProfileContext";

/** The loop the product implements, in the order a candidate meets it. */
const steps = [
  {
    title: "Answer the questionnaire",
    body: "Interests, existing skills, experience and where you want to work. Two minutes, and it works without an account.",
  },
  {
    title: "See where you actually fit",
    body: "100 roles ranked on your interests and skills, each one showing the arithmetic behind the score and what the role pays.",
  },
  {
    title: "Plan the skills you are missing",
    body: "A three-phase Gemini roadmap with free resources and portfolio projects, on a study pace you choose.",
  },
  {
    title: "Apply to real openings",
    body: "Search live postings from the public boards, apply at the source, and move each one through to the offer.",
  },
];

export default function HomePage() {
  useDocumentTitle();
  const { hasProfile } = useProfile();

  const startHref = hasProfile ? "/matches" : "/profile";
  const startLabel = hasProfile ? "See my matches" : "Build your profile";

  return (
    <div>
      <section className="hero-card">
        <h1 className="mb-3 text-3xl font-extrabold tracking-[-0.02em] sm:text-[2.6rem]">
          Navigate Your Tech Career with Precision
        </h1>
        <p className="max-w-3xl text-lg leading-relaxed text-slate-400">
          CareerCompass matches you to 100 corporate and modern engineering roles, benchmarks what
          each one pays in India, and plans the skills you are missing — then puts real openings
          beside that plan and tracks every application you send.
        </p>
        <div className="mt-7 flex flex-wrap items-center gap-3">
          <Link to={startHref} className="btn btn-primary">
            {startLabel}
          </Link>
          <Link
            to="/jobs"
            className="btn border border-white/20 bg-white/5 text-white hover:bg-white/10"
          >
            Search live jobs
          </Link>
        </div>
        <p className="mt-6 border-t border-white/10 pt-4 text-sm text-slate-400">
          100 curated roles across 8 categories · India CTC bands with their sources linked · live
          postings from Himalayas and Arbeitnow · applications tracked from saved to offer
        </p>
      </section>

      <section>
        <h2 className="section-title">🧭 How it works</h2>
        <p className="caption mt-1">
          Four steps from “I don’t know what to do next” to an application you are tracking.
        </p>
        <ol className="mt-6 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {steps.map((step, index) => (
            <li key={step.title} className="relative">
              <span className="grid h-9 w-9 place-items-center rounded-full border border-brand-200 bg-white text-sm font-bold text-brand-700 shadow-sm">
                {index + 1}
              </span>
              <h3 className="mt-3 text-base font-bold text-slate-900">{step.title}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-slate-500">{step.body}</p>
              {index < steps.length - 1 && (
                <span
                  aria-hidden="true"
                  className="absolute left-11 right-[-1.5rem] top-4 hidden h-px bg-gradient-to-r from-brand-200 to-brand-100 lg:block"
                />
              )}
            </li>
          ))}
        </ol>
      </section>

      <section className="mt-9">
        <h2 className="section-title">🧩 What you get</h2>
        <p className="caption mt-1">
          Pick a feature to see what it does, what it looks like, and where to find it.
        </p>
        <div className="mt-5">
          <FeatureExplorer profileReady={hasProfile} />
        </div>
      </section>

      <section className="mt-9">
        <SectionCard className="flex flex-col gap-4 border-brand-200 bg-brand-50 p-6 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-lg font-bold text-slate-900">
              Start with your interests, not the job market
            </h2>
            <p className="mt-1 text-sm text-slate-600">
              The questionnaire takes about two minutes and needs no account — sign in only when you
              want your roadmaps and applications kept.
            </p>
          </div>
          <div className="flex shrink-0 flex-wrap items-center gap-3">
            <Link to={startHref} className="btn btn-primary">
              {startLabel}
            </Link>
            <Link to="/roles" className="btn btn-secondary">
              Browse the 100 roles
            </Link>
          </div>
        </SectionCard>
      </section>
    </div>
  );
}
