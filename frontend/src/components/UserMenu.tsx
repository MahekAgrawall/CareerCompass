import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { useAuth } from "@/state/AuthContext";

/**
 * The account corner of the header.
 *
 * It used to be a name plus a second full-size button, so the right-hand side of
 * the bar had two focal points and competed with the navigation for width. The
 * products people call well built keep that corner to one quiet control: an
 * avatar that opens the account's own pages and the way out.
 *
 * This is a disclosure, not a menu widget: `aria-expanded` on the trigger, a
 * plain panel of links right after it in the tab order, Escape or a click
 * outside closes it. No half-implemented arrow-key model.
 */
export default function UserMenu() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const closeOnOutsideClick = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  if (!user) return null;

  const firstName = user.name.trim().split(/\s+/)[0] || "Account";
  const initial = firstName.charAt(0).toUpperCase();

  const signOut = () => {
    setOpen(false);
    logout();
    navigate("/");
  };

  return (
    <div ref={root} className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-controls="account-panel"
        className="flex items-center gap-2 rounded-full border border-slate-200 bg-white py-1 pl-1 pr-2.5 text-sm font-semibold text-slate-700 transition hover:border-slate-300 hover:bg-slate-50"
      >
        <span
          className="grid h-7 w-7 place-items-center rounded-full bg-brand-600 text-xs font-bold text-white"
          aria-hidden="true"
        >
          {initial}
        </span>
        <span className="hidden max-w-[9rem] truncate sm:inline">{firstName}</span>
        <svg
          width="10"
          height="6"
          viewBox="0 0 10 6"
          fill="none"
          aria-hidden="true"
          className={`text-slate-400 transition-transform ${open ? "rotate-180" : ""}`}
        >
          <path
            d="M1 1l4 4 4-4"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        <span className="sr-only">account menu</span>
      </button>

      {open && (
        <div
          id="account-panel"
          className="absolute right-0 z-40 mt-2 w-60 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-lg"
        >
          <div className="border-b border-slate-100 px-3 py-2.5">
            <p className="truncate text-sm font-semibold text-slate-900">{user.name}</p>
            <p className="truncate text-xs text-slate-500">{user.email}</p>
          </div>
          <div className="p-1">
            <Link
              to="/profile"
              onClick={() => setOpen(false)}
              className="block rounded-lg px-2.5 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-100 hover:text-slate-900"
            >
              My profile
            </Link>
            <Link
              to="/applications"
              onClick={() => setOpen(false)}
              className="block rounded-lg px-2.5 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-100 hover:text-slate-900"
            >
              My applications
            </Link>
            <button
              type="button"
              onClick={signOut}
              className="block w-full rounded-lg px-2.5 py-2 text-left text-sm font-medium text-slate-700 transition hover:bg-slate-100 hover:text-slate-900"
            >
              Sign out
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
