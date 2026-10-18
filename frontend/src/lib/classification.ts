/**
 * How a listing's classification is worded on a job card.
 *
 * The verdict is the classifier's reading of the *advert*, not of the title it was
 * posted under (see `backend/services/classification.py`), so these helpers present
 * it as a reading: the declared role family when it placed the advert, and the
 * reason when it did not.
 *
 * Two absences are kept apart throughout, because they mean different things and
 * the card shows different controls for them:
 *
 * * **`null`** on the posting is *nobody has read this yet* — an offer to classify;
 * * an **Unclassified** verdict is an *answer* — the advert did not say enough, or
 *   no declared family fits it — and it has a reason worth showing.
 */
import type { ListingClassification } from "@/api/types";

/** The role the taxonomy uses for a verdict that placed nothing. */
export const UNCLASSIFIED = "Unclassified";

/** True when the verdict named a family; false for an Unclassified answer. */
export function isPlaced(verdict: ListingClassification): boolean {
  return verdict.canonical_role !== UNCLASSIFIED;
}

/** The role family to show — the declared one, or the word for a verdict with none. */
export function verdictLabel(verdict: ListingClassification): string {
  return isPlaced(verdict) ? verdict.canonical_role : "Unclassified";
}

/**
 * How sure the model was, or "" when there is no role for the number to describe.
 *
 * Only shown for a placed verdict: an Unclassified answer can carry a *high*
 * confidence too (the advert was unmistakably a sales job), and "95% sure" beside
 * the word Unclassified reads as a contradiction rather than the reading it is.
 */
export function confidenceNote(verdict: ListingClassification): string {
  if (!isPlaced(verdict)) return "";
  return `${Math.round(verdict.classification_confidence * 100)}% confident`;
}

/**
 * Why the advert was not placed, or "" when it was.
 *
 * The stored `unclassified_reason` is the sentence the pipeline wrote for a reader
 * ("the advert does not fit any declared role family"); the model's own
 * `short_match_explanation` says *which* job it looked like when it declined, so
 * both are shown when both exist.
 */
export function reasonNote(verdict: ListingClassification): string {
  return isPlaced(verdict) ? "" : verdict.unclassified_reason;
}

/**
 * The model's own sentence about the advert, or "" when there is none.
 *
 * For a placed verdict this is why it is that role; for a declined one it names the
 * job the advert really was. It is empty when the advert was too thin to send to a
 * model at all, or when the reading was thrown away as too unsure.
 */
export function explanationNote(verdict: ListingClassification): string {
  return verdict.short_match_explanation.trim();
}

/** How many skills of each kind a card shows before the line would swamp it. */
const REQUIRED_LIMIT = 6;
const PREFERRED_LIMIT = 5;

/**
 * The advert's demanded and merely-welcomed skills, as two short lists.
 *
 * The two are kept apart on purpose — the classifier was told to distinguish what
 * the advert *requires* from what it welcomes, and collapsing them into one list
 * would present a nice-to-have as a condition. Each is capped so a long advert does
 * not turn a card into a wall: the card is a summary, and the advert itself is one
 * click away.
 */
export function skillSummary(verdict: ListingClassification): {
  required: string[];
  preferred: string[];
} {
  return {
    required: verdict.required_skills.slice(0, REQUIRED_LIMIT),
    preferred: verdict.preferred_skills.slice(0, PREFERRED_LIMIT),
  };
}

/**
 * The advert's own experience wording, or "" when it stated none.
 *
 * `as_written` is used rather than the parsed `years`, because an advert that said
 * "3+ years" or gave a range has no single number, and inventing one for it would
 * be a precision the advert never offered (see `MinimumExperienceAnswer`).
 */
export function experienceNote(verdict: ListingClassification): string {
  return verdict.minimum_experience.as_written.trim();
}

/**
 * Other titles the advert might be searched under, or "" when there are none.
 *
 * Related, not synonyms: the classifier was told to keep roles distinct, so these
 * are the nearest *other* families a candidate narrowing a search would recognise.
 */
export function relatedNote(verdict: ListingClassification): string {
  return verdict.related_role_titles.slice(0, 4).join(", ");
}
