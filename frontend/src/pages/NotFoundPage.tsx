import { Link } from "react-router-dom";

import EmptyState from "@/components/EmptyState";
import { useDocumentTitle } from "@/lib/hooks";

export default function NotFoundPage() {
  useDocumentTitle("Page not found");
  return (
    <EmptyState
      icon="🧭"
      title="Page not found"
      description="That route doesn't exist. Let's get you back on course."
      action={
        <div className="flex flex-wrap justify-center gap-3">
          <Link to="/" className="btn btn-primary">
            Back to Home
          </Link>
          <Link to="/roles" className="btn btn-secondary">
            Browse Roles
          </Link>
        </div>
      }
    />
  );
}
