import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import * as endpoints from "@/api/endpoints";
import type { JobPosting } from "@/api/types";
import { APPLICATIONS_KEY, applicationInput } from "@/lib/applications";
import { useAuth } from "@/state/AuthContext";

/**
 * Whether *this* posting is already filed, and how to file it.
 *
 * Every card on the Jobs page asks that question, but they share one query key,
 * so React Query issues a single request for the whole page and a single refetch
 * after a save — not one per card.
 *
 * Guests get no request at all: `enabled` is false until there is a token, and
 * the card offers a way to sign in instead of a button that would 401.
 */
export function useSavedJob(posting: JobPosting) {
  const { status } = useAuth();
  const queryClient = useQueryClient();
  const signedIn = status === "authenticated";

  const applications = useQuery({
    queryKey: APPLICATIONS_KEY,
    queryFn: endpoints.listApplications,
    enabled: signedIn,
    // Switching the arrangement filter between "Remote only" and "Any" remounts
    // the cards; the tracker does not need re-reading for that.
    staleTime: 60_000,
  });

  const saved = applications.data?.results.find((row) => row.posting_id === posting.id);

  const save = useMutation({
    mutationFn: () => endpoints.saveApplication(applicationInput(posting)),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: APPLICATIONS_KEY }),
  });

  return { signedIn, saved, save };
}
