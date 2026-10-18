import Badge from "./Badge";
import type { JobPosting } from "@/api/types";
import {
  confidenceNote,
  experienceNote,
  explanationNote,
  isPlaced,
  reasonNote,
  relatedNote,
  skillSummary,
  verdictLabel,
} from "@/lib/classification";
import { truncate } from "@/lib/format";
import { useClassifyJob } from "@/state/useClassifyJob";

/**
 * What the classifier made of one posting, or the control to ask it.
 *
 * A posting is one of three things here, and the card says which:
 *
 * * **not read** (`classification` is `null`) — a button. Reading one advert with
 *   the AI is exactly one model call and the answer is stored per listing, so this
 *   is offered only where nobody has looked, and asking twice is free;
 * * **placed** — the declared role family, its category, and the advert's demanded
 *   versus welcomed skills, which the classifier keeps apart on purpose;
 * * **unplaced** — the word *Unclassified* with the pipeline's reason and, when it
 *   declined, the model's own sentence naming the job it really was.
 *
 * The verdict is a reading of the advert, not of the title, which is why it sits
 * below the excerpt rather than beside the posting's own badges: the excerpt is what
 * the advert said, and this is what was made of it.
 */
export default function JobClassification({ posting }: { posting: JobPosting }) {
  const { classify, verdict } = useClassifyJob(posting);

  if (!verdict) {
    return (
      <div className="mt-3">
        <button
          type="button"
          className="btn btn-ghost w-full border border-dashed border-slate-300 text-xs"
          disabled={classify.isPending}
          onClick={() => classify.mutate()}
          title="Read this advert with the AI and file what the job actually is"
        >
          {classify.isPending ? "🤖 Reading the advert…" : "🤖 Classify this role"}
        </button>
        {classify.isError && (
          <p className="mt-1 text-xs text-rose-600">
            Could not classify this listing: {classify.error.message}
          </p>
        )}
      </div>
    );
  }

  if (!isPlaced(verdict)) {
    return (
      <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50 p-2.5">
        <Badge variant="muted">❓ {verdictLabel(verdict)}</Badge>
        {reasonNote(verdict) && (
          <p className="text-xs leading-relaxed text-slate-600">{reasonNote(verdict)}.</p>
        )}
        {explanationNote(verdict) && (
          <p className="mt-1 text-xs leading-relaxed text-slate-500">
            {truncate(explanationNote(verdict), 160)}
          </p>
        )}
      </div>
    );
  }

  const { required, preferred } = skillSummary(verdict);
  const experience = experienceNote(verdict);
  const related = relatedNote(verdict);
  const confidence = confidenceNote(verdict);

  return (
    <div className="mt-3 rounded-lg border border-sky-200 bg-sky-50/60 p-2.5">
      <Badge variant="ai">🤖 {verdictLabel(verdict)}</Badge>
      <Badge variant="muted">{verdict.primary_category}</Badge>
      {confidence && (
        <span className="align-middle text-[11px] font-normal text-slate-500">{confidence}</span>
      )}

      {explanationNote(verdict) && (
        <p className="mt-1 text-xs leading-relaxed text-slate-600">
          {truncate(explanationNote(verdict), 160)}
        </p>
      )}

      {required.length > 0 && (
        <p className="mt-1 text-xs leading-relaxed text-slate-600">
          <span className="font-semibold text-slate-700">Required:</span> {required.join(", ")}
        </p>
      )}
      {preferred.length > 0 && (
        <p className="mt-0.5 text-xs leading-relaxed text-slate-500">
          <span className="font-semibold text-slate-600">Preferred:</span> {preferred.join(", ")}
        </p>
      )}
      {experience && (
        <p className="mt-0.5 text-xs leading-relaxed text-slate-600">
          <span className="font-semibold text-slate-700">Experience:</span> {experience}
        </p>
      )}
      {related && (
        <p className="mt-0.5 text-xs leading-relaxed text-slate-500">
          <span className="font-semibold text-slate-600">Also titled:</span> {related}
        </p>
      )}
    </div>
  );
}
