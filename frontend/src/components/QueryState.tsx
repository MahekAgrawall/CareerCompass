import EmptyState from "./EmptyState";
import Spinner from "./Spinner";
import Alert from "./Alert";
import { ApiError } from "@/api/client";

/** Renders a spinner while loading and a friendly error otherwise. */
export function QueryState({
  isLoading,
  error,
  loadingLabel,
  children,
}: {
  isLoading: boolean;
  error: unknown;
  loadingLabel?: string;
  children: React.ReactNode;
}) {
  if (isLoading) return <Spinner label={loadingLabel} />;
  if (error) {
    const message =
      error instanceof ApiError ? error.message : "Something went wrong. Please try again.";
    return <Alert tone="error" title="Could not load this page">{message}</Alert>;
  }
  return <>{children}</>;
}

export { EmptyState, Spinner, Alert };
