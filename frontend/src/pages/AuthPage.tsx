import { useState } from "react";
import type { FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import Alert from "@/components/Alert";
import SectionCard from "@/components/SectionCard";
import { ApiError } from "@/api/client";
import { useDocumentTitle } from "@/lib/hooks";
import { useAuth } from "@/state/AuthContext";

type Mode = "login" | "signup";

export default function AuthPage() {
  useDocumentTitle("Sign in");
  const navigate = useNavigate();
  const location = useLocation();
  const { status, login, signup } = useAuth();

  const from = (location.state as { from?: string } | null)?.from ?? "/";

  const [mode, setMode] = useState<Mode>("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (status === "authenticated") return <Navigate to={from} replace />;

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      if (mode === "login") {
        await login(email.trim(), password);
        navigate(from, { replace: true });
      } else {
        await signup(name.trim(), email.trim(), password);
        navigate("/profile", { replace: true });
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  const switchMode = (next: Mode) => {
    setMode(next);
    setError(null);
  };

  return (
    <div className="mx-auto max-w-lg">
      <SectionCard className="p-6">
        <div className="mb-5 grid grid-cols-2 gap-1 rounded-lg bg-slate-100 p-1">
          <button
            type="button"
            onClick={() => switchMode("login")}
            className={`rounded-md px-3 py-2 text-sm font-semibold transition ${
              mode === "login" ? "bg-white text-brand-700 shadow-sm" : "text-slate-600 hover:text-slate-900"
            }`}
          >
            🔑 Sign In
          </button>
          <button
            type="button"
            onClick={() => switchMode("signup")}
            className={`rounded-md px-3 py-2 text-sm font-semibold transition ${
              mode === "signup" ? "bg-white text-brand-700 shadow-sm" : "text-slate-600 hover:text-slate-900"
            }`}
          >
            ✨ Create Account
          </button>
        </div>

        <h2 className="text-lg font-bold text-slate-900">
          {mode === "login" ? "Welcome Back" : "Create Your Account"}
        </h2>
        <p className="caption mt-1">
          {mode === "login"
            ? "Access your saved profile, custom roadmaps, and study schedules."
            : "Keep your career trajectories, roadmaps, and tracker checklists saved."}
        </p>

        <form className="mt-5 space-y-4" onSubmit={handleSubmit}>
          {mode === "signup" && (
            <label className="block">
              <span className="label">Full Name</span>
              <input
                className="input"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Mahek Agrawal"
                autoComplete="name"
                required
              />
            </label>
          )}

          <label className="block">
            <span className="label">Email</span>
            <input
              className="input"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="name@domain.com"
              autoComplete="email"
              required
            />
          </label>

          <label className="block">
            <span className="label">Password</span>
            <input
              className="input"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={mode === "signup" ? "At least 8 characters" : "••••••••"}
              autoComplete={mode === "signup" ? "new-password" : "current-password"}
              minLength={mode === "signup" ? 8 : undefined}
              required
            />
          </label>

          {error && <Alert tone="error">{error}</Alert>}

          <button type="submit" className="btn btn-primary w-full" disabled={submitting}>
            {submitting ? "Please wait…" : mode === "login" ? "Sign In" : "Register"}
          </button>
        </form>

        <p className="mt-4 text-center text-xs text-slate-400">
          Sessions are scoped to this browser tab and end when you close it.
        </p>
      </SectionCard>
    </div>
  );
}
