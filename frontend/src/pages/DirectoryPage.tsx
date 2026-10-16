import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import Alert from "@/components/Alert";
import RoleCard from "@/components/RoleCard";
import SelectField from "@/components/SelectField";
import { QueryState } from "@/components/QueryState";
import * as endpoints from "@/api/endpoints";
import { useDocumentTitle } from "@/lib/hooks";
import { useFlash } from "@/lib/useFlash";

const NICHE_OPTIONS = ["All Roles", "Niche Specialists Only 🎯", "Mainstream Core Only 🏢"];

export default function DirectoryPage() {
  useDocumentTitle("Role directory");
  const { message, flash } = useFlash();
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("All Categories");
  const [niche, setNiche] = useState(NICHE_OPTIONS[0]);

  const rolesQuery = useQuery({ queryKey: ["roles"], queryFn: endpoints.listRoles });
  const categoriesQuery = useQuery({ queryKey: ["categories"], queryFn: endpoints.listCategories });

  const categoryOptions = useMemo(
    () => ["All Categories", ...(categoriesQuery.data ?? [])],
    [categoriesQuery.data],
  );

  const filtered = useMemo(() => {
    let roles = rolesQuery.data ?? [];
    const q = search.trim().toLowerCase();

    if (q) {
      roles = roles.filter((role) =>
        [role.title, role.description, ...role.skills.must_have, ...role.matching_skills, ...role.top_companies]
          .some((value) => String(value).toLowerCase().includes(q)),
      );
    }
    if (category !== "All Categories") {
      roles = roles.filter((role) => role.category === category);
    }
    if (niche === "Niche Specialists Only 🎯") {
      roles = roles.filter((role) => role.is_niche);
    } else if (niche === "Mainstream Core Only 🏢") {
      roles = roles.filter((role) => !role.is_niche);
    }
    return roles;
  }, [rolesQuery.data, search, category, niche]);

  return (
    <div>
      <h1 className="section-title">📚 Comprehensive Technology Roles Catalog</h1>
      <p className="caption mt-1">
        Browse all corporate, AI, and specialized technology roles with Indian compensation benchmarks.
      </p>
      <hr className="my-5 border-slate-200" />

      <div className="mb-5 grid gap-3 lg:grid-cols-[2fr_1.4fr_1.4fr]">
        <label className="block">
          <span className="label">Search by role title, skill, or keyword</span>
          <input
            className="input"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="e.g. Agent, Java, Cloud, Palantir, SQL…"
          />
        </label>
        <SelectField label="Category" value={category} options={categoryOptions} onChange={setCategory} />
        <SelectField label="Role Classification" value={niche} options={NICHE_OPTIONS} onChange={setNiche} />
      </div>

      {message && (
        <div className="mb-4">
          <Alert tone="warning">{message}</Alert>
        </div>
      )}

      <QueryState isLoading={rolesQuery.isLoading} error={rolesQuery.error} loadingLabel="Loading roles…">
        <p className="mb-4 text-sm font-semibold text-slate-700">Showing {filtered.length} roles</p>
        {filtered.length === 0 ? (
          <Alert tone="warning">No roles match your filters. Try clearing the search or category.</Alert>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {filtered.map((role) => (
              <RoleCard key={role.id} role={role} onCompareFull={() => flash("Comparison max is 3 roles.")} />
            ))}
          </div>
        )}
      </QueryState>
    </div>
  );
}
