import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import CopilotPanel from "@/components/CopilotPanel";
import EmptyState from "@/components/EmptyState";
import { QueryState } from "@/components/QueryState";
import * as endpoints from "@/api/endpoints";
import { useDocumentTitle } from "@/lib/hooks";
import { useRoadmapCache } from "@/state/RoadmapContext";

/**
 * Standalone copilot route. The copilot now lives on the roadmap page itself
 * (`/roadmap/:roleId`); this page is kept so existing `/chat/:roleId` links and
 * bookmarks still work, and renders the same panel.
 */
export default function ChatPage() {
  const { roleId = "" } = useParams();
  const { getRoadmap } = useRoadmapCache();

  const roleQuery = useQuery({
    queryKey: ["role", roleId],
    queryFn: () => endpoints.getRole(roleId),
    enabled: Boolean(roleId),
  });

  const role = roleQuery.data;
  const roadmap = roleId ? getRoadmap(roleId) : null;

  useDocumentTitle(role ? `Copilot · ${role.title}` : "Roadmap Copilot");

  return (
    <QueryState isLoading={roleQuery.isLoading} error={roleQuery.error} loadingLabel="Loading copilot…">
      {role && !roadmap && (
        <EmptyState
          icon="🗺️"
          title="Generate a roadmap first"
          description="The copilot is pre-loaded with your target role and generated roadmap. Create one to start chatting."
          action={
            <Link to={`/roadmap/${role.id}`} className="btn btn-primary">
              Generate AI Skill Roadmap
            </Link>
          }
        />
      )}

      {role && roadmap && (
        <div>
          <CopilotPanel role={role} roadmap={roadmap} />
          <hr className="my-5 border-slate-200" />
          <Link to={`/roadmap/${role.id}`} className="btn btn-secondary">
            ← Back to Roadmap
          </Link>
        </div>
      )}
    </QueryState>
  );
}
