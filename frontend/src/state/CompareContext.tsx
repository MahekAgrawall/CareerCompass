import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";

import type { Role } from "@/api/types";

const COMPARE_KEY = "cc.compare";
const MAX_COMPARE = 3;

function readStored(): Role[] {
  try {
    const raw = sessionStorage.getItem(COMPARE_KEY);
    const parsed = raw ? (JSON.parse(raw) as Role[]) : [];
    return Array.isArray(parsed) ? parsed.slice(0, MAX_COMPARE) : [];
  } catch {
    return [];
  }
}

interface CompareContextValue {
  roles: Role[];
  count: number;
  max: number;
  isSelected: (roleId: string) => boolean;
  /** Adds a role; returns false when the comparison is already full. */
  add: (role: Role) => boolean;
  remove: (roleId: string) => void;
  toggle: (role: Role) => void;
  clear: () => void;
}

const CompareContext = createContext<CompareContextValue | null>(null);

export function CompareProvider({ children }: { children: ReactNode }) {
  const [roles, setRoles] = useState<Role[]>(() => readStored());

  useEffect(() => {
    sessionStorage.setItem(COMPARE_KEY, JSON.stringify(roles));
  }, [roles]);

  const isSelected = useCallback(
    (roleId: string) => roles.some((r) => r.id === roleId),
    [roles],
  );

  const add = useCallback((role: Role) => {
    let added = false;
    setRoles((current) => {
      if (current.some((r) => r.id === role.id) || current.length >= MAX_COMPARE) return current;
      added = true;
      return [...current, role];
    });
    return added;
  }, []);

  const remove = useCallback((roleId: string) => {
    setRoles((current) => current.filter((r) => r.id !== roleId));
  }, []);

  const toggle = useCallback((role: Role) => {
    setRoles((current) =>
      current.some((r) => r.id === role.id)
        ? current.filter((r) => r.id !== role.id)
        : current.length >= MAX_COMPARE
          ? current
          : [...current, role],
    );
  }, []);

  const clear = useCallback(() => setRoles([]), []);

  return (
    <CompareContext.Provider
      value={{ roles, count: roles.length, max: MAX_COMPARE, isSelected, add, remove, toggle, clear }}
    >
      {children}
    </CompareContext.Provider>
  );
}

export function useCompare(): CompareContextValue {
  const ctx = useContext(CompareContext);
  if (!ctx) throw new Error("useCompare must be used within a CompareProvider");
  return ctx;
}
