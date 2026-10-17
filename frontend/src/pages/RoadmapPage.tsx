import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import Alert from "@/components/Alert";
import CopilotPanel from "@/components/CopilotPanel";
import SectionCard from "@/components/SectionCard";
import Spinner from "@/components/Spinner";
import { QueryState } from "@/components/QueryState";
import * as endpoints from "@/api/endpoints";
import { ApiError, isAbortError, withTimeout } from "@/api/client";
import type { Roadmap, RoadmapPhaseItem, Role } from "@/api/types";
import { downloadTextFile, roadmapToMarkdown } from "@/lib/format";
import { useDocumentTitle } from "@/lib/hooks";
import { useProfile } from "@/state/ProfileContext";
import { useRoadmapCache } from "@/state/RoadmapContext";

const DIFFICULTY_ICON: Record<string, string> = {
  Beginner: "🟢",
  Intermediate: "🟡",
  Advanced: "🔴",
};

function PhaseList({
  title,
  caption,
  items,
  defaultOpen = false,
  withTime = true,
}: {
  title: string;
  caption?: string;
  items: RoadmapPhaseItem[];
  defaultOpen?: boolean;
  withTime?: boolean;
}) {
  if (!items?.length) return null;
  return (
    <section className="mt-6">
      <h2 className="text-lg font-bold text-slate-900">{title}</h2>
      {caption && <p className="caption mt-0.5">{caption}</p>}
      <div className="mt-3 space-y-2">
        {items.map((item, index) => (
          <details
            key={`${item.skill}-${index}`}
            open={defaultOpen}
            className="group rounded-xl border border-slate-200 bg-white p-4 shadow-sm open:shadow-md"
          >
            <summary className="cursor-pointer list-none font-semibold text-slate-800 marker:hidden">
              ✅ {item.skill}
              {withTime && item.time_estimate && (
                <span className="ml-2 text-sm font-normal italic text-slate-500">
                  Estimated: {item.time_estimate}
                </span>
              )}
              <span className="float-right text-slate-400 transition group-open:rotate-180">▾</span>
            </summary>
            <div className="mt-3 space-y-1.5 text-sm text-slate-600">
              <p>
                <strong className="text-slate-700">Why this matters:</strong> {item.why}
              </p>
              <p>
                <strong className="text-slate-700">📚 Curated free resource:</strong>{" "}
                <code className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-brand-700">{item.resource}</code>
              </p>
            </div>
          </details>
        ))}
      </div>
    </section>
  );
}

export default function RoadmapPage() {
  const { roleId = "" } = useParams();
  const { profile } = useProfile();
  const { getRoadmap, setRoadmap, clearRoadmap } = useRoadmapCache();

  const roleQuery = useQuery({
    queryKey: ["role", roleId],
    queryFn: () => endpoints.getRole(roleId),
    enabled: Boolean(roleId),
  });

  const cached = roleId ? getRoadmap(roleId) : null;
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notConfigured, setNotConfigured] = useState(false);
  const startedRef = useRef<string | null>(null);

  useDocumentTitle(roleQuery.data ? `${roleQuery.data.title} roadmap` : "Roadmap");

  const generate = useCallback(
    async (role: Role) => {
      setGenerating(true);
      setError(null);
      setNotConfigured(false);
      const { signal, cancel } = withTimeout(90_000);
      try {
        const roadmap = await endpoints.generateRoadmap(role.id, profile ?? {}, signal);
        setRoadmap(role.id, roadmap);
      } catch (err) {
        if (err instanceof ApiError && err.status === 503) {
          setNotConfigured(true);
          setError(err.message);
        } else if (isAbortError(err)) {
          setError("The AI took too long to respond. Please try again.");
        } else {
          setError(err instanceof Error ? err.message : "Could not generate your roadmap right now.");
        }
      } finally {
        cancel();
        setGenerating(false);
      }
    },
    [profile, setRoadmap],
  );

  // Auto-generate once per role when nothing is cached for this session.
  useEffect(() => {
    const role = roleQuery.data;
    if (!role || cached) return;
    if (startedRef.current === role.id) return;
    startedRef.current = role.id;
    void generate(role);
  }, [roleQuery.data, cached, generate]);

  const handleRegenerate = (role: Role) => {
    clearRoadmap(role.id);
    void generate(role);
  };

  const role = roleQuery.data;
  const roadmap: Roadmap | null = cached;

  return (
    <QueryState isLoading={roleQuery.isLoading} error={roleQuery.error} loadingLabel="Loading role…">
      {role && (
        <div>
          <h1 className="section-title">🗺️ Step 4 — Personalized Skill Roadmap</h1>
          <p className="mt-1 text-sm text-slate-600">
            <strong>Target Role:</strong> {role.icon} {role.title}
            <span className="mx-2 text-slate-300">|</span>
            <strong>Candidate:</strong> {profile?.name || "You"}
          </p>
          <hr className="my-5 border-slate-200" />

          {notConfigured && (
            <div className="space-y-3">
              <Alert tone="warning" title="AI is not configured">
                {error}
              </Alert>
              <Alert tone="info" title="Enable the AI roadmap">
                Set <code className="rounded bg-white/60 px-1">GEMINI_API_KEY</code> in{" "}
                <code className="rounded bg-white/60 px-1">backend/.env</code> (a free key from
                aistudio.google.com) and restart the backend.
              </Alert>
            </div>
          )}

          {!roadmap && generating && (
            <Spinner label="Synthesizing your roadmap & portfolio milestones with Gemini…" />
          )}

          {!roadmap && !generating && !notConfigured && error && (
            <div className="space-y-3">
              <Alert tone="error" title="Could not generate your roadmap">
                {error}
              </Alert>
              <button type="button" className="btn btn-primary" onClick={() => handleRegenerate(role)}>
                🔄 Try Again
              </button>
            </div>
          )}

          {roadmap && (
            <div>
              {roadmap.summary && (
                <Alert tone="info" title="Advisory Assessment">
                  {roadmap.summary}
                </Alert>
              )}

              <div className="mt-4 flex justify-end">
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() =>
                    downloadTextFile(
                      `careercompass_${role.id}_roadmap.md`,
                      roadmapToMarkdown(profile ?? {}, role, roadmap),
                    )
                  }
                >
                  ⬇️ Download roadmap (.md)
                </button>
              </div>

              <PhaseList
                title="🔥 Phase 1 — Immediate Focus (Hireability Acceleration)"
                caption="Highest-leverage foundational gaps to become interview-ready as quickly as possible."
                items={roadmap.immediate_focus}
                defaultOpen
              />
              <PhaseList
                title="📈 Phase 2 — Competitive Edge (Deepening Specialization)"
                caption="Capabilities that elevate your profile above average entry-level candidates."
                items={roadmap.next_level}
              />
              <PhaseList
                title="💡 Phase 3 — High-Growth Specialization"
                items={roadmap.good_to_explore}
                withTime={false}
              />

              {roadmap.projects?.length > 0 && (
                <section className="mt-6">
                  <h2 className="text-lg font-bold text-slate-900">🛠️ Portfolio Projects to Build</h2>
                  <p className="caption mt-0.5">
                    Hands-on repositories that validate your competence to hiring managers.
                  </p>
                  <div className="mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                    {roadmap.projects.map((project, index) => (
                      <SectionCard key={`${project.title}-${index}`} className="p-5" hover>
                        <p className="font-bold text-slate-900">
                          Project {index + 1}: {project.title}{" "}
                          <span aria-hidden="true">{DIFFICULTY_ICON[project.difficulty] ?? "⚪"}</span>{" "}
                          <span className="text-sm font-normal italic text-slate-500">
                            ({project.difficulty})
                          </span>
                        </p>
                        <p className="mt-2 text-sm leading-relaxed text-slate-600">{project.description}</p>
                        {project.skills_demonstrated?.length > 0 && (
                          <div className="mt-3 flex flex-wrap gap-1.5">
                            {project.skills_demonstrated.map((skill) => (
                              <code key={skill} className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600">
                                {skill}
                              </code>
                            ))}
                          </div>
                        )}
                      </SectionCard>
                    ))}
                  </div>
                </section>
              )}

              {roadmap.motivational_message && (
                <blockquote className="mt-6 border-l-4 border-brand-400 bg-brand-50 px-5 py-4 text-sm italic text-brand-900">
                  {roadmap.motivational_message}
                </blockquote>
              )}

              <hr className="my-6 border-slate-200" />

              <div className="grid gap-4 sm:grid-cols-2">
                <SectionCard className="flex flex-col p-5" hover>
                  <h3 className="text-lg font-bold text-slate-900">📅 Ready to Study? Plan Your Hours</h3>
                  <p className="mt-2 text-sm text-slate-500">
                    Configure your weekday and weekend availability to track every topic and subtopic with
                    completion markers.
                  </p>
                  <Link to={`/tracker/${role.id}`} className="btn btn-primary mt-4 w-full">
                    Open Custom Study Tracker →
                  </Link>
                </SectionCard>

                <SectionCard className="flex flex-col p-5" hover>
                  <h3 className="text-lg font-bold text-slate-900">💬 Have Questions on the Roadmap?</h3>
                  <p className="mt-2 text-sm text-slate-500">
                    Your Roadmap Copilot is on this page: break down daily tasks, ask interview tips, or get
                    project guidance without leaving the roadmap.
                  </p>
                  <a href="#copilot" className="btn btn-secondary mt-4 w-full">
                    Jump to the Copilot ↓
                  </a>
                </SectionCard>
              </div>

              <hr className="my-6 border-slate-200" />

              <section id="copilot" className="scroll-mt-24">
                <CopilotPanel role={role} roadmap={roadmap} />
              </section>

              <hr className="my-6 border-slate-200" />
              <div className="flex flex-wrap gap-3">
                <Link to={`/roles/${role.id}`} className="btn btn-secondary">
                  ← Back to Role Detail
                </Link>
                <button type="button" className="btn btn-secondary ml-auto" onClick={() => handleRegenerate(role)}>
                  🔄 Regenerate Roadmap
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </QueryState>
  );
}
