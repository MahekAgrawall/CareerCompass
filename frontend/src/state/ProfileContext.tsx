import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

import * as endpoints from "@/api/endpoints";
import type { Profile } from "@/api/types";
import { useAuth } from "./AuthContext";

const PROFILE_KEY = "cc.profile";

function readStoredProfile(): Profile | null {
  try {
    const raw = sessionStorage.getItem(PROFILE_KEY);
    return raw ? (JSON.parse(raw) as Profile) : null;
  } catch {
    return null;
  }
}

function normalize(partial: Partial<Profile>): Profile {
  return {
    name: partial.name ?? "",
    grad_year: partial.grad_year ?? "",
    experience: partial.experience ?? "",
    location: partial.location ?? "",
    current_skills: Array.isArray(partial.current_skills) ? partial.current_skills : [],
    interests: Array.isArray(partial.interests) ? partial.interests : [],
  };
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
 * sessionStorage so matching/roadmaps work without an account, and it is
 * mirrored to the backend whenever the user is authenticated.
 */
export function ProfileProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [profile, setProfileState] = useState<Profile | null>(() => readStoredProfile());
  const loadedForUser = useRef<number | null>(null);

  // Pull the server-side profile once per signed-in user.
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
        const data = await endpoints.getProfile();
        if (cancelled) return;
        if (data && Object.keys(data).length > 0) {
          const next = normalize(data);
          setProfileState(next);
          sessionStorage.setItem(PROFILE_KEY, JSON.stringify(next));
        }
      } catch {
        // Offline backend — keep the locally cached profile.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [user]);

  const saveProfile = useCallback(
    async (next: Profile) => {
      setProfileState(next);
      sessionStorage.setItem(PROFILE_KEY, JSON.stringify(next));
      if (user) {
        try {
          await endpoints.saveProfile(next);
        } catch {
          // Non-fatal: the profile stays cached locally.
        }
      }
    },
    [user],
  );

  const clearProfile = useCallback(() => {
    sessionStorage.removeItem(PROFILE_KEY);
    setProfileState(null);
  }, []);

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
