import { Link } from "react-router-dom";

import SectionCard from "@/components/SectionCard";
import { useDocumentTitle } from "@/lib/hooks";
import { useProfile } from "@/state/ProfileContext";

/** The loop the product implements, in the order a candidate meets it. */
const steps = [
  {
    title: "Answer the questionnaire",
    body: "A short set of questions on your interests, existing skills, experience and where you want to work. Two minutes, and it works without an account.",
  },
  {
    title: "See where you actually fit",
    body: "Your matches, each one showing the arithmetic behind the score, what the role pays in India, and how competitive it is right now.",
  },
  {
    title: "Leave with a plan",
    body: "Generate a roadmap for the role you pick, study it on a pace you choose, and work through its live openings as you apply.",
  },
];

/** What the product does. One concrete line each — no adjectives doing the work. */
const features = [
  {
    icon: "🎯",
    title: "Interest-first matching",
    body: "Roles are ranked 65% on the interests you claim and 35% on the skills you have, and every card prints both scores.",
  },
  {
    icon: "🧠",
    title: "Semantic recall",
    body: "A vector index shortlists roles that match the meaning of your profile and goal, then the same transparent scorer ranks them.",
  },
  {
    icon: "💼",
    title: "Live job search",
    body: "Real postings harvested from Himalayas and Arbeitnow, filtered in the store by role, location, experience and work arrangement.",
  },
  {
    icon: "💰",
    title: "India salary bands",
    body: "Fresher, mid and senior CTC envelopes for every role, with the public sources behind them linked on the role page.",
  },
  {
    icon: "🗺️",
    title: "AI skill roadmaps",
    body: "Gemini writes a three-phase plan — Immediate, Level Up, Explore — with one free resource per skill and three projects to build.",
  },
  {
    icon: "📅",
    title: "Study tracker",
    body: "Pick a weekday or weekend pace and every subtopic gets its hours, a checklist and a projected finish date.",
  },
  {
    icon: "📋",
    title: "Application tracking",
    body: "Save any posting and move it through Saved, Applied, Interview and Offer, with your own notes on each row.",
  },
  {
    icon: "⚖️",
    title: "Compare and export",
    body: "Weigh up to three roles side by side, and download any roadmap as a Markdown file you keep.",
  },
  {
    icon: "💬",
    title: "Roadmap copilot",
    body: "A streaming Gemini chat that already knows your profile, your target role and the plan it is sitting next to.",
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
          CareerCompass ranks 100 corporate and modern engineering roles against the interests and
          skills you actually have, benchmarks what each one pays in India, and turns the role you
          pick into a week-by-week plan — with live openings and an AI mentor beside it.
        </p>
        <div className="mt-7 flex flex-wrap items-center gap-3">
          <Link to={startHref} className="btn btn-primary">
            {startLabel}
          </Link>
          <Link
            to="/roles"
            className="btn border border-white/20 bg-white/5 text-white hover:bg-white/10"
          >
            Browse the 100 roles
          </Link>
        </div>
        <p className="mt-6 border-t border-white/10 pt-4 text-sm text-slate-400">
          100 curated roles across 8 categories · CTC bands with the sources behind them linked ·
          postings harvested from Himalayas and Arbeitnow
        </p>
      </section>

      <section>
        <h2 className="section-title">🧭 How it works</h2>
        <p className="caption mt-1">
          Three steps from “I don’t know what to do next” to a plan you can start this week.
        </p>
        <div className="mt-5 grid gap-4 md:grid-cols-3">
          {steps.map((step, index) => (
            <SectionCard key={step.title} className="p-5" hover>
              <span
                className="inline-grid h-7 w-7 place-items-center rounded-full bg-brand-50 text-sm font-bold text-brand-700"
                aria-hidden="true"
              >
                {index + 1}
              </span>
              <h3 className="mt-3 text-base font-bold text-slate-900">{step.title}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-slate-500">{step.body}</p>
            </SectionCard>
          ))}
        </div>
      </section>

      <section className="mt-9">
        <h2 className="section-title">🧩 What you get</h2>
        <p className="caption mt-1">
          Every part of the loop, from the first questionnaire to the applications you send.
        </p>
        <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {features.map((feature) => (
            <SectionCard key={feature.title} className="p-5" hover>
              <div className="flex items-center gap-2.5">
                <span
                  className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-slate-100 text-lg"
                  aria-hidden="true"
                >
                  {feature.icon}
                </span>
                <h3 className="text-sm font-bold text-slate-900">{feature.title}</h3>
              </div>
              <p className="mt-2.5 text-sm leading-relaxed text-slate-500">{feature.body}</p>
            </SectionCard>
          ))}
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
            <Link to="/jobs" className="btn btn-secondary">
              Search live jobs
            </Link>
          </div>
        </SectionCard>
      </section>
    </div>
  );
}
