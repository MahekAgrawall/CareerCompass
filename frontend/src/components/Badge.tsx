import type { ReactNode } from "react";

type Variant = "demand" | "comp" | "future" | "match" | "niche" | "muted" | "ai";

export default function Badge({
  variant = "muted",
  children,
}: {
  variant?: Variant;
  children: ReactNode;
}) {
  return <span className={`badge badge-${variant}`}>{children}</span>;
}
