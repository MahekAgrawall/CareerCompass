import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";

import type { Roadmap } from "@/api/types";

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
 */
export function RoadmapProvider({ children }: { children: ReactNode }) {
  const [cache, setCache] = useState<RoadmapCache>(() => readStored());

  useEffect(() => {
    try {
      sessionStorage.setItem(ROADMAPS_KEY, JSON.stringify(cache));
    } catch {
      // Ignore quota errors — the cache is a convenience, not a source of truth.
    }
  }, [cache]);

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
