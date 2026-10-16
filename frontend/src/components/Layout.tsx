import type { ReactNode } from "react";

import Navbar from "./Navbar";
import ScrollToTop from "./ScrollToTop";

export default function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col bg-slate-50">
      <ScrollToTop />
      <Navbar />
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-7">
        <div className="animate-fade-in">{children}</div>
      </main>
      <footer className="border-t border-slate-200 bg-white py-6">
        <div className="mx-auto max-w-6xl px-4 text-center text-xs text-slate-400">
          CareerCompass — built with FastAPI + React. Salary benchmarks aggregated from AmbitionBox,
          Glassdoor and LinkedIn India tech data.
        </div>
      </footer>
    </div>
  );
}
