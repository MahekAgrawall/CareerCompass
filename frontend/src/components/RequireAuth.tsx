import { Navigate, useLocation } from "react-router-dom";
import type { ReactNode } from "react";

import Spinner from "./Spinner";
import { useAuth } from "@/state/AuthContext";

/** Guards a route behind authentication, remembering where the user was headed. */
export default function RequireAuth({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const location = useLocation();

  if (status === "loading") return <Spinner label="Checking your session…" />;
  if (status === "anonymous") {
    return <Navigate to="/auth" replace state={{ from: location.pathname }} />;
  }

  return <>{children}</>;
}
