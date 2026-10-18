import { useMutation, useQueryClient } from "@tanstack/react-query";

import * as endpoints from "@/api/endpoints";
import type { JobPosting } from "@/api/types";

/**
 * The classifier's verdict for one posting, and how to ask for it.
 *
 * The reading is *stored server-side per listing* (see
 * `backend/services/classification.py`), so the card only ever offers this for a
 * listing nobody has read — `posting.classification` is `null`, which is the offer
 * to classify, distinct from an Unclassified verdict that is already an answer. Once
 * a verdict exists, a later search decorates the posting with it and no call is
 * needed, so this is a one-shot control rather than a toggle.
 *
 * The mutation's own result is returned as soon as it lands, so the badge appears
 * without waiting for anything else. `["jobs"]` is then invalidated: the search's
 * `classified` count moved, and a page filtered by category should be able to admit
 * a listing the fresh reading has just placed there. The refetch is a search, not
 * another classification — the AI token is spent once, on the click.
 */
export function useClassifyJob(posting: JobPosting) {
  const queryClient = useQueryClient();

  const classify = useMutation({
    mutationFn: () => endpoints.classifyJob(posting.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["jobs"] }),
  });

  return { classify, verdict: classify.data ?? posting.classification };
}
