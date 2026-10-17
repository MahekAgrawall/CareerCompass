import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

import * as endpoints from "@/api/endpoints";
import type { Roadmap } from "@/api/types";
import { useAuth } from "./AuthContext";

const ROADMAPS_KEY = "cc.roadmaps";

type RoadmapCache = Record<string, Roadmap>;

function readStored(): RoadmapCache {
  try {
    const raw = sessionStorage.getItem(ROADMAPS_KEY);
    const parsed = raw ? (JSON.parse(raw) as RoadmapCache) : {};
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

interface RoadmapContextValue {
  getRoadmap: (roleId: string) => Roadmap | null;
  setRoadmap: (roleId: string, roadmap: Roadmap) => void;
  clearRoadmap: (roleId: string) => void;
}

const RoadmapContext = createContext<RoadmapContextValue | null>(null);

/**
 * Caches generated roadmaps per role for the browser session so the Roadmap,
 * Tracker and Copilot views don't re-trigger expensive AI generations.
 *
 * A signed-in candidate also has plans saved server-side, so the cache is seeded
 * from `GET /roadmaps` on sign-in: revisiting a role they already generated shows
 * the plan immediately instead of paying for a second generation. A plan generated
 * in this session always wins over the saved one — it is by definition newer.
 */
export function RoadmapProvider({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const [cache, setCache] = useState<RoadmapCache>(() => readStored());
  const hydrated = useRef(false);

  useEffect(() => {
    try {
      sessionStorage.setItem(ROADMAPS_KEY, JSON.stringify(cache));
    } catch {
      // Ignore quota errors — the cache is a convenience, not a source of truth.
    }
  }, [cache]);

  // Adopt the saved library once per session, when a token resolves.
  //
  // No cancellation here on purpose: StrictMode mounts effects twice in
  // development, so the cleanup would abort the one request this guard allows and
  // the cache would never be seeded. The provider lives for the whole app, and a
  // functional update is safe to apply whenever the response lands.
  useEffect(() => {
    if (status !== "authenticated" || hydrated.current) return;
    hydrated.current = true;

    (async () => {
      try {
        const saved = await endpoints.listSavedRoadmaps();
        setCache((current) => {
          const next = { ...current };
          let added = false;
          // Newest first from the API, so the first plan seen for a role wins.
          for (const item of saved) {
            if (!next[item.role_id]) {
              next[item.role_id] = item.roadmap;
              added = true;
            }
          }
          return added ? next : current;
        });
      } catch {
        // Offline or an expired session — the in-session cache still works.
      }
    })();
  }, [status]);

  const getRoadmap = useCallback((roleId: string) => cache[roleId] ?? null, [cache]);

  const setRoadmap = useCallback((roleId: string, roadmap: Roadmap) => {
    setCache((current) => ({ ...current, [roleId]: roadmap }));
  }, []);

  const clearRoadmap = useCallback((roleId: string) => {
    setCache((current) => {
      const next = { ...current };
      delete next[roleId];
      return next;
    });
  }, []);

  return (
    <RoadmapContext.Provider value={{ getRoadmap, setRoadmap, clearRoadmap }}>
      {children}
    </RoadmapContext.Provider>
  );
}

export function useRoadmapCache(): RoadmapContextValue {
  const ctx = useContext(RoadmapContext);
  if (!ctx) throw new Error("useRoadmapCache must be used within a RoadmapProvider");
  return ctx;
}
