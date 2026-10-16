import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

import * as endpoints from "@/api/endpoints";
import type { Profile } from "@/api/types";
import { useAuth } from "./AuthContext";

const PROFILE_KEY = "cc.profile";

/** Cached answers plus the account they belong to (`null` = filled in as a guest). */
interface CachedProfile {
  ownerId: number | null;
  profile: Profile;
}

function normalize(partial: Partial<Profile>): Profile {
  return {
    name: partial.name ?? "",
    grad_year: partial.grad_year ?? "",
    experience: partial.experience ?? "",
    location: partial.location ?? "",
    work_mode: partial.work_mode ?? "",
    open_to_relocate: partial.open_to_relocate ?? "",
    career_goal: partial.career_goal ?? "",
    current_skills: Array.isArray(partial.current_skills) ? partial.current_skills : [],
    interests: Array.isArray(partial.interests) ? partial.interests : [],
  };
}

/** True when the candidate actually answered something worth keeping. */
function hasAnswers(profile: Profile): boolean {
  return Boolean(profile.name.trim() || profile.interests.length || profile.current_skills.length);
}

/** Reads the cache, tolerating the older bare-profile format (owner unknown). */
function readCache(): CachedProfile | null {
  try {
    const raw = sessionStorage.getItem(PROFILE_KEY);
    if (!raw) return null;

    const parsed = JSON.parse(raw) as Partial<CachedProfile> & Partial<Profile>;
    if (!parsed || typeof parsed !== "object") return null;

    if (parsed.profile && typeof parsed.profile === "object") {
      return {
        ownerId: typeof parsed.ownerId === "number" ? parsed.ownerId : null,
        profile: normalize(parsed.profile),
      };
    }
    // Legacy format: the stored value *was* the profile.
    if ("name" in parsed || "interests" in parsed) {
      return { ownerId: null, profile: normalize(parsed as Partial<Profile>) };
    }
    return null;
  } catch {
    return null;
  }
}

function writeCache(profile: Profile | null, ownerId: number | null): void {
  if (!profile) {
    sessionStorage.removeItem(PROFILE_KEY);
    return;
  }
  sessionStorage.setItem(PROFILE_KEY, JSON.stringify({ ownerId, profile }));
}

interface ProfileContextValue {
  profile: Profile | null;
  hasProfile: boolean;
  saveProfile: (profile: Profile) => Promise<void>;
  clearProfile: () => void;
}

const ProfileContext = createContext<ProfileContextValue | null>(null);

/**
 * The candidate profile is the app's "anonymous-first" state: it lives in
 * `sessionStorage` so matching and roadmaps work without an account, and it is
 * mirrored to the backend whenever the user is authenticated.
 *
 * Cached answers are stamped with the account they belong to. A questionnaire
 * answered as a guest is therefore carried over to whichever account signs in
 * next and saved there — while answers belonging to a *different* account are
 * hidden and never adopted.
 */
export function ProfileProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [entry, setEntry] = useState<CachedProfile | null>(() => readCache());
  const loadedForUser = useRef<number | null>(null);

  const adopt = useCallback((next: Profile | null, ownerId: number | null) => {
    writeCache(next, ownerId);
    setEntry(next ? { ownerId, profile: next } : null);
  }, []);

  // While nobody is signed in the cache drives the UI. Once somebody is, only
  // answers stamped with their own id are visible.
  const profile = entry && (!user || entry.ownerId === user.id) ? entry.profile : null;

  // Reconcile the cached answers with the account once per signed-in user.
  useEffect(() => {
    if (!user) {
      loadedForUser.current = null;
      return;
    }
    if (loadedForUser.current === user.id) return;
    loadedForUser.current = user.id;

    let cancelled = false;
    (async () => {
      try {
        const saved = await endpoints.getProfile();
        if (cancelled) return;

        if (saved && Object.keys(saved).length > 0) {
          // The account already has answers — they win over anything cached.
          adopt(normalize(saved), user.id);
          return;
        }

        // Fresh account: carry over a questionnaire answered as a guest, then
        // persist it so the answers outlive this browser tab.
        const cached = readCache();
        if (!cached || !hasAnswers(cached.profile)) return;

        if (cached.ownerId === null || cached.ownerId === user.id) {
          adopt(cached.profile, user.id);
          await endpoints.saveProfile(cached.profile);
        } else {
          adopt(null, null);
        }
      } catch {
        // Offline backend — keep whatever is cached.
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [user, adopt]);

  const saveProfile = useCallback(
    async (next: Profile) => {
      adopt(next, user?.id ?? null);
      if (user) {
        try {
          await endpoints.saveProfile(next);
        } catch {
          // Non-fatal: the answers stay cached locally.
        }
      }
    },
    [user, adopt],
  );

  const clearProfile = useCallback(() => adopt(null, null), [adopt]);

  return (
    <ProfileContext.Provider
      value={{ profile, hasProfile: Boolean(profile), saveProfile, clearProfile }}
    >
      {children}
    </ProfileContext.Provider>
  );
}

export function useProfile(): ProfileContextValue {
  const ctx = useContext(ProfileContext);
  if (!ctx) throw new Error("useProfile must be used within a ProfileProvider");
  return ctx;
}
