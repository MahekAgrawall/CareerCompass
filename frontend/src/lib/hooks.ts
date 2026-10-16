import { useEffect } from "react";

const APP_NAME = "CareerCompass";

/** Keeps `document.title` in sync with the active page. */
export function useDocumentTitle(title?: string) {
  useEffect(() => {
    document.title = title ? `${title} · ${APP_NAME}` : `${APP_NAME} 🧭 — AI Career Engine`;
  }, [title]);
}
