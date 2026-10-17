import { useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { Link } from "react-router-dom";

/**
 * The feature index on the home page.
 *
 * Nine cards of equal weight was the monotone version: the same shape nine
 * times, nothing to do once you had read one, and no way into the product from
 * any of them. This is a list you move through instead — one feature on stage at
 * a time, the panel animating in as it changes, a schematic beside it showing
 * what that part of the app looks like, and a link into the page where the
 * feature actually lives.
 *
 * It is a real tablist: `role`/`aria-selected`/roving `tabIndex`, with arrow
 * keys (plus Home and End) moving both the selection and the focus. Both axes
 * are accepted because the list is a column on wide screens and a horizontal
 * scroll strip on phones.
 *
 * The schematics are decorative (`aria-hidden`) — shapes, and the product's own
 * vocabulary where a label is worth reading, but no invented figures: the 65/35
 * split, the roadmap phases, the application stages and the board name are all
 * things the app really says.
 */

type PreviewKind =
  | "scores"
  | "recall"
  | "postings"
  | "salary"
  | "phases"
  | "checklist"
  | "stages"
  | "compare"
  | "chat";

interface Feature {
  id: string;
  icon: string;
  title: string;
  /** What the feature is, in the product's own terms. */
  detail: string;
  /** Concrete specifics — the parts a reader would otherwise have to trust. */
  points: string[];
  /** Where the feature lives. */
  to: string;
  cta: string;
  preview: PreviewKind;
  /** Matching sends you to your results only once you have answered the form. */
  followsProfile?: boolean;
}

const FEATURES: Feature[] = [
  {
    id: "matching",
    icon: "🎯",
    title: "Interest-first matching",
    detail:
      "Every role is scored 65% on the interests you claim and 35% on the skills you already have, and a role with no interest overlap does not survive the cut.",
    points: [
      "Both component scores are printed on the card, with the chips that counted",
      "Your free-text goal and work hub feed the recall stage, never the arithmetic",
    ],
    to: "/profile",
    cta: "Build your profile",
    preview: "scores",
    followsProfile: true,
  },
  {
    id: "recall",
    icon: "🧠",
    title: "Semantic recall",
    detail:
      "A vector index recalls roles that match the meaning of your profile and your goal, so “I like untangling messy data” can surface a role your chips never named.",
    points: [
      "Recall can only add candidates — it never touches a score",
      "Runs on Gemini embeddings, or fully offline with the deterministic embedder",
    ],
    to: "/roles",
    cta: "Browse the catalog",
    preview: "recall",
  },
  {
    id: "jobs",
    icon: "💼",
    title: "Live job search",
    detail:
      "Search real openings harvested from the public Himalayas and Arbeitnow boards, filtered by role, location, experience and work arrangement — and every search tells you when the postings were harvested.",
    points: [
      "Filters run in the vector store, so the counts cover the whole collection",
      "Each card links straight out to the original listing, so you apply at the source",
      "Public boards mean remote and international postings sit beside Indian ones",
    ],
    to: "/jobs",
    cta: "Search live jobs",
    preview: "postings",
  },
  {
    id: "salary",
    icon: "💰",
    title: "India salary benchmarks",
    detail:
      "Every role carries fresher, mid and senior CTC envelopes for the Indian market — the low end a typical mid-market or services offer, the high end a strong product company or GCC.",
    points: [
      "Three bands per role, not one number pretending to be everyone's salary",
      "Every reference point is linked with its sample size on the role page",
    ],
    to: "/roles",
    cta: "See the bands",
    preview: "salary",
  },
  {
    id: "roadmap",
    icon: "🗺️",
    title: "AI skill roadmaps",
    detail:
      "Google Gemini writes a three-phase plan for the role you pick — Immediate, Level Up, Explore — with one free resource per skill and three portfolio projects with difficulty ratings.",
    points: [
      "Saved to your library with the model and prompt version that produced it",
      "Re-open a plan instead of spending another generation on it",
    ],
    to: "/roles",
    cta: "Pick a role to plan",
    preview: "phases",
  },
  {
    id: "tracker",
    icon: "📅",
    title: "Study tracker",
    detail:
      "Choose a weekday or weekend pace and the role's own tech stack; every subtopic gets hours, a checklist and a projected finish date, recomputed as you tick things off.",
    points: [
      "A stack per role, not one generic syllabus for all 100",
      "Progress, remaining hours and weeks-to-finish update live",
    ],
    to: "/tracker",
    cta: "Open the tracker",
    preview: "checklist",
  },
  {
    id: "applications",
    icon: "📋",
    title: "Application pipeline",
    detail:
      "Save any posting from the live search and move it through Saved → Applied → Interview → Offer, or Closed when it went nowhere, with a note and the date it moved.",
    points: [
      "A row is a snapshot, so it survives the board taking the listing down",
      "Saving the same posting twice never resets a stage you already reached",
    ],
    to: "/applications",
    cta: "Open my applications",
    preview: "stages",
  },
  {
    id: "compare",
    icon: "⚖️",
    title: "Compare and export",
    detail:
      "Put up to three roles side by side on demand, competition, AI-future relevance, compensation and must-have skills — and download any roadmap as a Markdown file you keep.",
    points: ["Three roles at a time, from any page", "Roadmaps export as portable Markdown"],
    to: "/compare",
    cta: "Compare roles",
    preview: "compare",
  },
  {
    id: "copilot",
    icon: "💬",
    title: "Roadmap copilot",
    detail:
      "A multi-turn Gemini chat sits beside the roadmap with your profile, target role and plan already in context, and the answers stream in as they are written.",
    points: ["Pre-loaded with your profile and your plan", "The thread is kept for the tab"],
    to: "/roadmaps",
    cta: "Open my roadmaps",
    preview: "chat",
  },
];

/** Decorative sketches of each feature — shapes and real labels, no invented figures. */
function Schematic({ kind }: { kind: PreviewKind }) {
  if (kind === "scores") {
    return (
      <div className="space-y-2.5 rounded-lg border border-slate-200 bg-white p-3">
        <div className="h-2.5 w-2/3 rounded bg-slate-200" />
        {[
          { label: "Interest fit", pct: 65 },
          { label: "Skill fit", pct: 35 },
        ].map((row) => (
          <div key={row.label}>
            <div className="flex justify-between text-[10px] font-semibold text-slate-500">
              <span>{row.label}</span>
              <span>{row.pct}%</span>
            </div>
            <div className="mt-1 h-1.5 rounded-full bg-slate-100">
              <div className="h-1.5 rounded-full bg-brand-500" style={{ width: `${row.pct}%` }} />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (kind === "recall") {
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-3">
        <div className="flex flex-wrap gap-1.5">
          <span className="h-4 w-14 rounded-full bg-slate-200" />
          <span className="h-4 w-20 rounded-full bg-slate-100" />
          <span className="h-4 w-12 rounded-full bg-slate-200" />
        </div>
        <p className="my-2 text-center text-xs text-slate-300" aria-hidden="true">
          ↓
        </p>
        <div className="flex items-center gap-2 rounded-lg border border-brand-200 bg-brand-50 px-2.5 py-2">
          <div className="h-2 flex-1 rounded bg-brand-200" />
          <span className="text-[10px] font-bold text-brand-700">by meaning</span>
        </div>
      </div>
    );
  }

  if (kind === "postings") {
    return (
      <div className="space-y-2 rounded-lg border border-slate-200 bg-white p-3">
        <div className="flex flex-wrap gap-1.5">
          <span className="h-4 w-16 rounded-full bg-brand-100" />
          <span className="h-4 w-12 rounded-full bg-slate-100" />
          <span className="h-4 w-14 rounded-full bg-slate-100" />
          <span className="h-4 w-11 rounded-full bg-slate-100" />
        </div>
        {[0, 1].map((row) => (
          <div key={row} className="flex items-center gap-2 rounded-lg border border-slate-100 p-2">
            <div className="flex-1 space-y-1.5">
              <div className="h-2 w-3/4 rounded bg-slate-200" />
              <div className="h-2 w-1/2 rounded bg-slate-100" />
            </div>
            <span className="shrink-0 text-[10px] font-bold text-brand-600">Apply on Himalayas ↗</span>
          </div>
        ))}
      </div>
    );
  }

  if (kind === "salary") {
    return (
      <div className="flex items-end justify-center gap-3 rounded-lg border border-slate-200 bg-white p-3 pt-6">
        {[
          { label: "Fresher", height: "h-8" },
          { label: "Mid", height: "h-14" },
          { label: "Senior", height: "h-20" },
        ].map((bar) => (
          <div key={bar.label} className="flex flex-col items-center gap-1.5">
            <div className={`w-9 rounded-t bg-gradient-to-t from-brand-500 to-brand-400 ${bar.height}`} />
            <span className="text-[10px] font-semibold text-slate-500">{bar.label}</span>
          </div>
        ))}
      </div>
    );
  }

  if (kind === "phases") {
    return (
      <div className="space-y-2 rounded-lg border border-slate-200 bg-white p-3">
        {["Immediate", "Level Up", "Explore"].map((phase, index) => (
          <div key={phase} className="flex items-center gap-2">
            <span className="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-brand-50 text-[9px] font-bold text-brand-700">
              {index + 1}
            </span>
            <span className="text-[11px] font-semibold text-slate-600">{phase}</span>
            <div className="ml-auto h-2 w-1/3 rounded bg-slate-200" />
          </div>
        ))}
      </div>
    );
  }

  if (kind === "checklist") {
    return (
      <div className="space-y-2 rounded-lg border border-slate-200 bg-white p-3">
        <div className="h-1.5 rounded-full bg-slate-100">
          <div className="h-1.5 w-2/5 rounded-full bg-brand-500" />
        </div>
        {[true, true, false].map((done, index) => (
          <div key={index} className="flex items-center gap-2">
            <span
              className={`grid h-4 w-4 shrink-0 place-items-center rounded border text-[9px] font-bold ${
                done ? "border-brand-500 bg-brand-500 text-white" : "border-slate-300 text-transparent"
              }`}
            >
              ✓
            </span>
            <div className={`h-2 rounded ${done ? "w-2/3 bg-slate-200" : "w-1/2 bg-slate-100"}`} />
          </div>
        ))}
      </div>
    );
  }

  if (kind === "stages") {
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-3">
        <div className="flex flex-wrap gap-1.5">
          {["Saved", "Applied", "Interview", "Offer"].map((stage, index) => (
            <span
              key={stage}
              className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                index === 2 ? "bg-brand-600 text-white" : "bg-slate-100 text-slate-500"
              }`}
            >
              {stage}
            </span>
          ))}
        </div>
        <div className="mt-3 space-y-1.5">
          <div className="h-2 w-3/4 rounded bg-slate-200" />
          <div className="h-2 w-1/3 rounded bg-slate-100" />
        </div>
      </div>
    );
  }

  if (kind === "compare") {
    const rows = [
      { label: "Demand", bars: ["w-3/4", "w-1/2", "w-2/3"] },
      { label: "CTC", bars: ["w-1/2", "w-3/4", "w-1/3"] },
      { label: "AI relevance", bars: ["w-2/3", "w-1/3", "w-3/4"] },
    ];
    return (
      <div className="space-y-2 rounded-lg border border-slate-200 bg-white p-3">
        {rows.map((row) => (
          <div key={row.label} className="flex items-center gap-2">
            <span className="w-16 shrink-0 text-[10px] font-semibold text-slate-500">{row.label}</span>
            <div className="grid flex-1 grid-cols-3 gap-1.5">
              {row.bars.map((width, index) => (
                <div key={index} className={`h-2 rounded bg-slate-200 ${width}`} />
              ))}
            </div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-2 rounded-lg border border-slate-200 bg-white p-3">
      <div className="flex justify-end">
        <div className="w-2/3 space-y-1 rounded-lg rounded-br-sm bg-brand-50 p-2">
          <div className="h-2 w-3/4 rounded bg-brand-200" />
          <div className="h-2 w-1/2 rounded bg-brand-200" />
        </div>
      </div>
      <div className="flex justify-start">
        <div className="w-4/5 space-y-1 rounded-lg rounded-bl-sm bg-slate-100 p-2">
          <div className="h-2 w-full rounded bg-slate-300" />
          <div className="h-2 w-5/6 rounded bg-slate-300" />
          <div className="flex items-center gap-1">
            <div className="h-2 w-1/3 rounded bg-slate-300" />
            <span className="inline-block h-3 w-1 animate-pulse rounded-sm bg-slate-400" />
          </div>
        </div>
      </div>
    </div>
  );
}

export default function FeatureExplorer({ profileReady }: { profileReady: boolean }) {
  const [activeId, setActiveId] = useState(FEATURES[0].id);
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);

  const activeIndex = Math.max(
    0,
    FEATURES.findIndex((feature) => feature.id === activeId),
  );
  const active = FEATURES[activeIndex];
  const target =
    active.followsProfile && profileReady
      ? { to: "/matches", cta: "See my matches" }
      : { to: active.to, cta: active.cta };

  const move = (index: number) => {
    const next = (index + FEATURES.length) % FEATURES.length;
    setActiveId(FEATURES[next].id);
    tabRefs.current[next]?.focus();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    const step =
      event.key === "ArrowDown" || event.key === "ArrowRight"
        ? 1
        : event.key === "ArrowUp" || event.key === "ArrowLeft"
          ? -1
          : 0;
    if (step !== 0) {
      event.preventDefault();
      move(activeIndex + step);
      return;
    }
    if (event.key === "Home") {
      event.preventDefault();
      move(0);
    }
    if (event.key === "End") {
      event.preventDefault();
      move(FEATURES.length - 1);
    }
  };

  return (
    <div className="grid gap-4 lg:grid-cols-[18rem_1fr]">
      <div
        role="tablist"
        aria-label="What you get"
        className="flex gap-2 overflow-x-auto pb-1 lg:flex-col lg:gap-1 lg:overflow-visible lg:pb-0"
      >
        {FEATURES.map((feature, index) => {
          const selected = feature.id === active.id;
          return (
            <button
              key={feature.id}
              ref={(element) => {
                tabRefs.current[index] = element;
              }}
              type="button"
              role="tab"
              id={`feature-tab-${feature.id}`}
              aria-selected={selected}
              aria-controls={`feature-panel-${feature.id}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => setActiveId(feature.id)}
              onKeyDown={onKeyDown}
              className={`flex shrink-0 items-center gap-2.5 rounded-lg border px-3 py-2.5 text-left text-sm font-semibold transition duration-200 lg:w-full ${
                selected
                  ? "border-brand-200 bg-brand-50 text-brand-700 shadow-sm"
                  : "border-transparent text-slate-600 hover:bg-slate-100 hover:text-slate-900"
              }`}
            >
              <span
                aria-hidden="true"
                className={`text-base transition-transform duration-200 ${selected ? "scale-125" : "scale-100"}`}
              >
                {feature.icon}
              </span>
              <span className="whitespace-nowrap lg:whitespace-normal">{feature.title}</span>
            </button>
          );
        })}
      </div>

      <div
        key={active.id}
        role="tabpanel"
        id={`feature-panel-${active.id}`}
        aria-labelledby={`feature-tab-${active.id}`}
        className="card animate-fade-in p-5 motion-reduce:animate-none sm:p-6"
      >
        <div className="grid gap-5 lg:grid-cols-[1fr_16rem] lg:items-start">
          <div>
            <div className="flex items-center gap-3">
              <span
                aria-hidden="true"
                className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-brand-50 text-xl"
              >
                {active.icon}
              </span>
              <h3 className="text-lg font-bold text-slate-900">{active.title}</h3>
            </div>
            <p className="mt-3 text-sm leading-relaxed text-slate-600">{active.detail}</p>
            <ul className="mt-3">
              {active.points.map((point) => (
                <li key={point} className="subtopic">
                  {point}
                </li>
              ))}
            </ul>
            <Link to={target.to} className="btn btn-primary mt-5">
              {target.cta}
            </Link>
          </div>

          <div aria-hidden="true">
            <Schematic kind={active.preview} />
          </div>
        </div>
      </div>
    </div>
  );
}
