import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import Alert from "@/components/Alert";
import MetricCard from "@/components/MetricCard";
import ProgressBar from "@/components/ProgressBar";
import SectionCard from "@/components/SectionCard";
import { QueryState } from "@/components/QueryState";
import * as endpoints from "@/api/endpoints";
import type { Topic } from "@/api/types";
import { formatDate, weeklyHours } from "@/lib/format";
import { useDocumentTitle } from "@/lib/hooks";

function pickOption(options: string[], saved: string[]): string {
  return saved.find((value) => options.includes(value)) ?? options[0];
}

export default function TrackerPage() {
  const { roleId } = useParams<{ roleId?: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [weekdayHours, setWeekdayHours] = useState(1.5);
  const [weekendHours, setWeekendHours] = useState(4);
  const [dim1, setDim1] = useState("");
  const [dim2, setDim2] = useState("");
  const [dim3, setDim3] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const initializedFor = useRef<string | null>(null);

  const rolesQuery = useQuery({ queryKey: ["roles"], queryFn: endpoints.listRoles });
  const roles = rolesQuery.data ?? [];
  const activeRoleId = roleId && roles.some((r) => r.id === roleId) ? roleId : roles[0]?.id ?? "";
  const activeRole = roles.find((r) => r.id === activeRoleId);

  useDocumentTitle("Study tracker");

  const stackQuery = useQuery({
    queryKey: ["stack", activeRoleId],
    queryFn: () => endpoints.getStackSchema(activeRoleId),
    enabled: Boolean(activeRoleId),
  });

  const trackerQuery = useQuery({
    queryKey: ["tracker", activeRoleId],
    queryFn: () => endpoints.getTracker(activeRoleId),
    enabled: Boolean(activeRoleId),
  });

  // Seed the schedule form once per role load.
  useEffect(() => {
    const state = trackerQuery.data;
    const schema = stackQuery.data;
    if (!state || !schema || !activeRoleId) return;
    if (initializedFor.current === activeRoleId) return;
    initializedFor.current = activeRoleId;

    setWeekdayHours(state.schedule.weekday_hours);
    setWeekendHours(state.schedule.weekend_hours);
    const saved = state.schedule.target_languages ?? [];
    setDim1(pickOption(schema.dim1.options, saved));
    setDim2(pickOption(schema.dim2.options, saved));
    setDim3(pickOption(schema.dim3.options, saved));
  }, [trackerQuery.data, stackQuery.data, activeRoleId]);

  const saveMutation = useMutation({
    mutationFn: () =>
      endpoints.saveSchedule({
        role_id: activeRoleId,
        weekday_hours: weekdayHours,
        weekend_hours: weekendHours,
        target_languages: [dim1, dim2, dim3],
      }),
    onSuccess: () => {
      setNotice("Syllabus tailored for the selected stack!");
      queryClient.invalidateQueries({ queryKey: ["tracker", activeRoleId] });
      window.setTimeout(() => setNotice(null), 3500);
    },
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, done }: { id: number; done: boolean }) => endpoints.toggleTopic(id, done),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["tracker", activeRoleId] }),
  });

  const schema = stackQuery.data;
  const state = trackerQuery.data;
  const weekly = weeklyHours(weekdayHours, weekendHours);

  const categories = new Map<string, Topic[]>();
  for (const topic of state?.topics ?? []) {
    const list = categories.get(topic.category) ?? [];
    list.push(topic);
    categories.set(topic.category, list);
  }

  return (
    <QueryState
      isLoading={rolesQuery.isLoading || (Boolean(activeRoleId) && (trackerQuery.isLoading || stackQuery.isLoading))}
      error={rolesQuery.error ?? trackerQuery.error ?? stackQuery.error}
      loadingLabel="Loading your study tracker…"
    >
      {roles.length === 0 ? (
        <Alert tone="warning">No roles available in the database.</Alert>
      ) : (
        <div>
          <h1 className="section-title">📅 Study Hours Planner & Topic Tracker</h1>
          <p className="caption mt-1">
            Customize your daily study throughput across weekdays and weekends, and check off syllabus topics as
            you master them.
          </p>
          <hr className="my-5 border-slate-200" />

          {notice && (
            <div className="mb-4">
              <Alert tone="success">{notice}</Alert>
            </div>
          )}

          <SectionCard className="p-5">
            <h2 className="text-lg font-bold text-slate-900">⚙️ 1. Study Commitment & Target Stack</h2>

            <div className="mt-4 grid gap-4 lg:grid-cols-3">
              <label className="block">
                <span className="label">Target Role for Study Tracker</span>
                <select
                  className="input"
                  value={activeRoleId}
                  onChange={(e) => navigate(`/tracker/${e.target.value}`)}
                >
                  {roles.map((role) => (
                    <option key={role.id} value={role.id}>
                      {role.icon} {role.title}
                    </option>
                  ))}
                </select>
              </label>

              <label className="block">
                <span className="label">Weekday Study (hrs/day)</span>
                <input
                  className="input"
                  type="number"
                  min={0.5}
                  max={12}
                  step={0.5}
                  value={weekdayHours}
                  onChange={(e) => setWeekdayHours(Number(e.target.value))}
                />
              </label>

              <label className="block">
                <span className="label">Weekend Study (hrs/day)</span>
                <input
                  className="input"
                  type="number"
                  min={0.5}
                  max={16}
                  step={0.5}
                  value={weekendHours}
                  onChange={(e) => setWeekendHours(Number(e.target.value))}
                />
              </label>
            </div>

            {schema && (
              <>
                <h3 className="mt-5 text-sm font-bold text-slate-800">
                  🎯 Configure your {activeRole?.title} specialization stack
                </h3>
                <div className="mt-3 grid gap-4 lg:grid-cols-3">
                  <label className="block">
                    <span className="label">{schema.dim1.label}</span>
                    <select className="input" value={dim1} onChange={(e) => setDim1(e.target.value)}>
                      {schema.dim1.options.map((option) => (
                        <option key={option} value={option}>
                          {option}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="block">
                    <span className="label">{schema.dim2.label}</span>
                    <select className="input" value={dim2} onChange={(e) => setDim2(e.target.value)}>
                      {schema.dim2.options.map((option) => (
                        <option key={option} value={option}>
                          {option}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="block">
                    <span className="label">{schema.dim3.label}</span>
                    <select className="input" value={dim3} onChange={(e) => setDim3(e.target.value)}>
                      {schema.dim3.options.map((option) => (
                        <option key={option} value={option}>
                          {option}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
              </>
            )}

            <p className="mt-4 text-sm text-slate-600">
              ⚡ <strong>Weekly Study Pace:</strong>{" "}
              <code className="rounded bg-slate-100 px-1.5 py-0.5 text-xs font-semibold text-brand-700">
                {weekly.toFixed(1)} hours/week
              </code>{" "}
              <span className="text-slate-500">
                (5 weekdays × {weekdayHours}h + 2 weekend days × {weekendHours}h)
              </span>
            </p>

            <button
              type="button"
              className="btn btn-primary mt-4"
              disabled={saveMutation.isPending || !schema}
              onClick={() => saveMutation.mutate()}
            >
              {saveMutation.isPending ? "Saving…" : "Save Schedule & Update Syllabus"}
            </button>
          </SectionCard>

          {state && (
            <>
              <SectionCard className="mt-5 p-5">
                <h2 className="text-lg font-bold text-slate-900">
                  📊 2. Progress Dashboard: {activeRole?.icon} {activeRole?.title}
                </h2>
                <div className="mt-3">
                  <ProgressBar value={state.metrics.percentage} />
                </div>
                <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  <MetricCard
                    label="Completion"
                    value={`${state.metrics.percentage}%`}
                    hint={`${state.metrics.completed_topics}/${state.metrics.total_topics} topics`}
                  />
                  <MetricCard label="Total Syllabus Time" value={`${Math.round(state.metrics.total_hours)} hrs`} />
                  <MetricCard label="Remaining Study" value={`${Math.round(state.metrics.remaining_hours)} hrs`} />
                  <MetricCard label="Projected Timeline" value={`${state.metrics.weeks_remaining} wks`} hint="At current weekly pace" />
                </div>
              </SectionCard>

              <section className="mt-6">
                <h2 className="text-lg font-bold text-slate-900">📝 3. Detailed Topic & Subtopic Syllabus</h2>
                <p className="caption mt-0.5">
                  Check off topics as you finish your study sessions. All progress is automatically stored.
                </p>

                <div className="mt-4 space-y-4">
                  {[...categories.entries()].map(([category, topics]) => {
                    const completed = topics.filter((t) => t.is_completed).length;
                    return (
                      <SectionCard key={category} className="p-5">
                        <h3 className="text-base font-bold text-slate-900">
                          📚 {category}{" "}
                          <span className="text-sm font-normal text-slate-500">
                            (Completed: {completed}/{topics.length})
                          </span>
                        </h3>

                        <div className="mt-3 divide-y divide-slate-100">
                          {topics.map((topic) => (
                            <div key={topic.id} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-start">
                              <div className="flex-1">
                                <label className="flex cursor-pointer items-start gap-2.5">
                                  <input
                                    type="checkbox"
                                    className="mt-1 h-4 w-4 shrink-0 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                                    checked={topic.is_completed}
                                    disabled={toggleMutation.isPending}
                                    onChange={(e) => toggleMutation.mutate({ id: topic.id, done: e.target.checked })}
                                  />
                                  <span className="font-semibold text-slate-800">
                                    {topic.topic_name}{" "}
                                    <span className="font-normal text-slate-500">
                                      ({Math.round(topic.estimated_hours)} hrs)
                                    </span>
                                  </span>
                                </label>
                                <div className="mt-1.5">
                                  {topic.subtopics.map((sub) => (
                                    <p key={sub} className="subtopic">
                                      {sub}
                                    </p>
                                  ))}
                                </div>
                              </div>
                              <div className="shrink-0 sm:w-32 sm:text-right">
                                {topic.is_completed ? (
                                  <>
                                    <span className="badge badge-future">✓ Completed</span>
                                    <p className="text-xs text-slate-400">Done: {formatDate(topic.completed_at)}</p>
                                  </>
                                ) : (
                                  <span className="badge badge-muted">In Progress</span>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      </SectionCard>
                    );
                  })}
                </div>
              </section>

              <hr className="my-6 border-slate-200" />
              <div className="flex flex-wrap gap-3">
                <Link to={`/roadmap/${activeRoleId}`} className="btn btn-secondary">
                  ← Back to Roadmap
                </Link>
                <Link to={`/chat/${activeRoleId}`} className="btn btn-primary ml-auto">
                  💬 Chat with Roadmap Copilot
                </Link>
              </div>
            </>
          )}
        </div>
      )}
    </QueryState>
  );
}
