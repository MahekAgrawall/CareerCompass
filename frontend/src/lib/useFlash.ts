import { useCallback, useEffect, useRef, useState } from "react";

/** Shows a transient message that auto-dismisses (used for "compare is full" notices). */
export function useFlash(duration = 3500) {
  const [message, setMessage] = useState<string | null>(null);
  const timer = useRef<number | undefined>(undefined);

  const flash = useCallback(
    (msg: string) => {
      setMessage(msg);
      if (timer.current) window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => setMessage(null), duration);
    },
    [duration],
  );

  useEffect(
    () => () => {
      if (timer.current) window.clearTimeout(timer.current);
    },
    [],
  );

  return { message, flash, clear: () => setMessage(null) };
}
