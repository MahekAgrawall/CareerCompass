import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import EmptyState from "@/components/EmptyState";
import SectionCard from "@/components/SectionCard";
import { QueryState } from "@/components/QueryState";
import * as endpoints from "@/api/endpoints";
import type { SavedRoadmap } from "@/api/types";
import { formatDate } from "@/lib/format";
import { useDocumentTitle } from "@/lib/hooks";
import { useRoadmapCache } from "@/state/RoadmapContext";

export default function RoadmapsPage() {
  useDocumentTitle("My roadmaps");
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { setRoadmap } = useRoadmapCache();

  const roadmapsQuery = useQuery({ queryKey: ["roadmaps"], queryFn: endpoints.listSavedRoadmaps });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => endpoints.deleteSavedRoadmap(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["roadmaps"] }),
  });

  const openPlan = (roleId: string, roadmap: SavedRoadmap["roadmap"]) => {
    setRoadmap(roleId, roadmap);
    navigate(`/roadmap/${roleId}`);
  };

  return (
    <div>
      <h1 className="section-title">🗺️ My Saved Roadmaps</h1>
      <p className="caption mt-1">
        Every roadmap you generate is saved here so you can revisit a plan or pick up where you left off.
      </p>
      <hr className="my-5 border-slate-200" />

      <QueryState isLoading={roadmapsQuery.isLoading} error={roadmapsQuery.error} loadingLabel="Loading your roadmaps…">
        {(roadmapsQuery.data?.length ?? 0) === 0 ? (
          <EmptyState
            icon="🗺️"
            title="No roadmaps yet"
            description="Pick a role and generate your first personalized plan — it will show up here."
            action={
              <Link to="/roles" className="btn btn-primary">
                Browse Roles Directory
              </Link>
            }
          />
        ) : (
          <>
            <p className="mb-4 text-sm font-semibold text-slate-700">
              {roadmapsQuery.data!.length} saved roadmap(s) — most recent first.
            </p>
            <div className="space-y-4">
              {roadmapsQuery.data!.map((item) => {
                const priority = item.roadmap?.immediate_focus?.length ?? 0;
                const projects = item.roadmap?.projects?.length ?? 0;
                return (
                  <SectionCard key={item.id} className="p-5" hover>
                    <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                      <div className="min-w-0">
                        <h2 className="text-base font-bold text-slate-900">💼 {item.role_title}</h2>
                        <p className="caption mt-0.5">
                          Generated {formatDate(item.created_at)} • {priority} priority skills • {projects} projects
                        </p>
                        {item.roadmap?.summary && (
                          <p className="mt-2 text-sm leading-relaxed text-slate-600">{item.roadmap.summary}</p>
                        )}
                      </div>
                      <div className="flex shrink-0 gap-2">
                        <button
                          type="button"
                          className="btn btn-primary"
                          onClick={() => openPlan(item.role_id, item.roadmap)}
                        >
                          Open Plan
                        </button>
                        <button
                          type="button"
                          className="btn btn-danger"
                          disabled={deleteMutation.isPending}
                          onClick={() => deleteMutation.mutate(item.id)}
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                  </SectionCard>
                );
              })}
            </div>
          </>
        )}
      </QueryState>

      <hr className="my-6 border-slate-200" />
      <div className="flex flex-wrap gap-3">
        <Link to="/" className="btn btn-secondary">
          ← Back to Home
        </Link>
        <Link to="/roles" className="btn btn-secondary ml-auto">
          Explore More Roles →
        </Link>
      </div>
    </div>
  );
}
