import type { ReactNode } from "react";

type Tone = "info" | "success" | "warning" | "error";

const TONES: Record<Tone, string> = {
  info: "border-brand-200 bg-brand-50 text-brand-900",
  success: "border-green-200 bg-green-50 text-green-900",
  warning: "border-amber-200 bg-amber-50 text-amber-900",
  error: "border-red-200 bg-red-50 text-red-900",
};

const ICONS: Record<Tone, string> = {
  info: "💡",
  success: "✅",
  warning: "⚠️",
  error: "⛔",
};

export default function Alert({
  tone = "info",
  title,
  children,
  icon,
}: {
  tone?: Tone;
  title?: ReactNode;
  children?: ReactNode;
  icon?: string;
}) {
  return (
    <div className={`rounded-xl border px-4 py-3 text-sm ${TONES[tone]}`} role="status">
      <div className="flex gap-2.5">
        <span aria-hidden="true">{icon ?? ICONS[tone]}</span>
        <div className="min-w-0 flex-1">
          {title && <p className="font-semibold">{title}</p>}
          {children && <div className={title ? "mt-1" : undefined}>{children}</div>}
        </div>
      </div>
    </div>
  );
}
