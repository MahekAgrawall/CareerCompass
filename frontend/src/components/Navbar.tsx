import { NavLink } from "react-router-dom";

import BrandLogo from "./BrandLogo";
import UserMenu from "./UserMenu";
import { useAuth } from "@/state/AuthContext";
import { useCompare } from "@/state/CompareContext";

const linkBase = "rounded-lg px-1.5 py-2 text-[13px] font-semibold transition whitespace-nowrap";
const linkIdle = "text-slate-600 hover:bg-slate-100 hover:text-slate-900";
const linkActive = "bg-brand-50 text-brand-700";

function navClass({ isActive }: { isActive: boolean }) {
  return `${linkBase} ${isActive ? linkActive : linkIdle}`;
}

/**
 * Three zones, in the order people expect: brand, navigation, account.
 *
 * The row is budgeted to fit one line, and the links are set tight to keep it
 * there: nine of them measure ~620px at 13px with 6px of side padding, so brand
 * (~236px) + links + account (~112px) + the two 12px gaps come to ~993px — that
 * fits the 1120px the `max-w-6xl` container allows from a 1184px window up, and
 * fits from a 1040px window up. From `lg` the links sit inline and centred;
 * below `lg` the middle zone would be too narrow for them, so the links take a row of
 * their own instead of being squeezed against the brand. `md:flex-wrap` is the
 * safety net: a future label that does not fit wraps rather than disappearing,
 * and `overflow-x-auto` stays on phones, where a one-line scroll strip is the
 * right answer.
 *
 * A centred row that overflows is clipped at *both* ends and its first link
 * cannot be scrolled back into view, which is why a narrow slot can never be
 * the plan for these links.
 */
export default function Navbar() {
  const { user, status } = useAuth();
  const { count } = useCompare();

  return (
    <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/85 backdrop-blur">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3">
        <NavLink to="/" className="shrink-0" aria-label="CareerCompass home">
          <BrandLogo />
        </NavLink>

        <nav className="order-3 flex w-full items-center gap-0.5 overflow-x-auto md:flex-wrap md:justify-center md:overflow-x-visible lg:order-2 lg:w-auto lg:flex-1">
          <NavLink to="/" end className={navClass}>
            Home
          </NavLink>
          <NavLink to="/profile" className={navClass}>
            My Profile
          </NavLink>
          <NavLink to="/matches" className={navClass}>
            My Matches
          </NavLink>
          <NavLink to="/roles" className={navClass}>
            All Roles
          </NavLink>
          <NavLink to="/jobs" className={navClass}>
            Jobs
          </NavLink>
          <NavLink to="/roadmaps" className={navClass}>
            Roadmaps
          </NavLink>
          <NavLink to="/tracker" className={navClass}>
            Tracker
          </NavLink>
          <NavLink to="/applications" className={navClass}>
            Applications
          </NavLink>
          <NavLink to="/compare" className={navClass}>
            Compare{count > 0 ? ` (${count})` : ""}
          </NavLink>
        </nav>

        <div className="order-2 ml-auto flex items-center gap-2 xl:order-3">
          {status === "loading" ? (
            <span className="h-9 w-28 animate-pulse rounded-full bg-slate-200" aria-hidden="true" />
          ) : user ? (
            <UserMenu />
          ) : (
            <NavLink to="/auth" className="btn btn-primary">
              🔑 Sign In
            </NavLink>
          )}
        </div>
      </div>
    </header>
  );
}
