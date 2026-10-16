import type { Profile, Roadmap, Role, TrackerMetrics } from "@/api/types";

/** Renders a generated roadmap as a portable Markdown document (mirrors the legacy exporter). */
export function roadmapToMarkdown(
  profile: Partial<Profile>,
  role: Role,
  roadmap: Roadmap,
): string {
  const lines: string[] = [
    `# ${role.title} — Personalized Roadmap`,
    "",
    `**Candidate:** ${profile.name || "Candidate"}  `,
    `**Target role:** ${role.title} (${role.category})  `,
    "**Generated with CareerCompass**",
    "",
    "## Summary",
    "",
    roadmap.summary ?? "",
    "",
  ];

  const section = (
    title: string,
    items: Roadmap["immediate_focus"],
    withTime = true,
  ) => {
    if (!items?.length) return;
    lines.push(`## ${title}`, "");
    for (const item of items) {
      lines.push(`### ${item.skill}`);
      if (withTime && item.time_estimate) lines.push(`- **Estimated time:** ${item.time_estimate}`);
      if (item.why) lines.push(`- **Why it matters:** ${item.why}`);
      if (item.resource) lines.push(`- **Free resource:** ${item.resource}`);
      lines.push("");
    }
  };

  section("Phase 1 — Immediate Focus", roadmap.immediate_focus);
  section("Phase 2 — Competitive Edge", roadmap.next_level);
  section("Phase 3 — High-Growth Specialization", roadmap.good_to_explore, false);

  if (roadmap.projects?.length) {
    lines.push("## Portfolio Projects", "");
    roadmap.projects.forEach((project, index) => {
      lines.push(`### Project ${index + 1}: ${project.title}`);
      if (project.difficulty) lines.push(`- **Difficulty:** ${project.difficulty}`);
      if (project.description) lines.push(`- **Description:** ${project.description}`);
      if (project.skills_demonstrated?.length) {
        lines.push(`- **Skills demonstrated:** ${project.skills_demonstrated.join(", ")}`);
      }
      lines.push("");
    });
  }

  if (roadmap.motivational_message) {
    lines.push("---", "", `> ${roadmap.motivational_message}`, "");
  }

  return lines.join("\n");
}

/** Triggers a browser download of a text file. */
export function downloadTextFile(filename: string, content: string, mime = "text/markdown") {
  const blob = new Blob([content], { type: `${mime};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

/** Formats an ISO timestamp as a short YYYY-MM-DD date. */
export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  return value.slice(0, 10);
}

/** Ranks market-demand labels so they can be sorted high → low. */
export function demandRank(value: string | undefined): number {
  const v = value ?? "";
  if (v.startsWith("Hyper")) return 4;
  if (v.startsWith("Very High")) return 3;
  if (v.startsWith("High")) return 2;
  if (v.startsWith("Moderate")) return 1;
  return 2;
}

/** Shortens a string to `max` characters, appending an ellipsis when trimmed. */
export function truncate(text: string, max: number): string {
  if (text.length <= max) return text;
  return `${text.slice(0, max).trimEnd()}…`;
}

/** Computes the weekly study pace from weekday/weekend hours. */
export function weeklyHours(weekdayHours: number, weekendHours: number): number {
  return weekdayHours * 5 + weekendHours * 2;
}

/** Small helper to display metric numbers cleanly. */
export function formatHours(value: number): string {
  return `${Math.round(value)} hrs`;
}

export function metricsSummary(metrics: TrackerMetrics): string {
  return `${metrics.completed_topics}/${metrics.total_topics} topics`;
}
