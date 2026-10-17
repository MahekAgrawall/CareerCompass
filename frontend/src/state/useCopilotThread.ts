import { useCallback, useEffect, useState } from "react";
import type { SetStateAction } from "react";

import type { ChatMessage } from "@/api/types";

/**
 * The copilot thread, persisted per role for the browser session.
 *
 * The panel used to keep its messages in component state, so moving between the
 * roadmap page and `/chat/:roleId` — or simply stepping back to a role and
 * returning — silently threw the conversation away. The thread now lives beside
 * the roadmap cache in `sessionStorage`, so the same tab picks the conversation
 * back up. Closing the tab clears it, exactly like the roadmap cache and the
 * sign-in token.
 */
const CHATS_KEY = "cc.chats";

/** Enough to scroll back through, without growing the tab's quota forever. */
const MAX_MESSAGES = 40;

type ChatCache = Record<string, ChatMessage[]>;

function isMessage(value: unknown): value is ChatMessage {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<ChatMessage>;
  return (
    (candidate.role === "user" || candidate.role === "model") &&
    typeof candidate.content === "string"
  );
}

function readAll(): ChatCache {
  try {
    const raw = sessionStorage.getItem(CHATS_KEY);
    const parsed = raw ? (JSON.parse(raw) as ChatCache) : {};
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function readThread(roleId: string): ChatMessage[] {
  const stored = readAll()[roleId];
  return Array.isArray(stored) ? stored.filter(isMessage) : [];
}

function writeThread(roleId: string, messages: ChatMessage[]): void {
  try {
    const all = readAll();
    if (messages.length) all[roleId] = messages.slice(-MAX_MESSAGES);
    else delete all[roleId];
    sessionStorage.setItem(CHATS_KEY, JSON.stringify(all));
  } catch {
    // Quota, or a locked-down browser: a thread is a convenience, not a source of truth.
  }
}

/** The thread and the role it belongs to, so the two can never drift apart. */
interface Thread {
  roleId: string;
  messages: ChatMessage[];
}

/**
 * `paused` is set while a reply is streaming: writing on every chunk would hit
 * `sessionStorage` dozens of times per answer, and a half-typed reply is not worth
 * persisting anyway. The finished turn is written when streaming stops.
 */
export function useCopilotThread(roleId: string, { paused = false }: { paused?: boolean } = {}) {
  const [thread, setThread] = useState<Thread>(() => ({ roleId, messages: readThread(roleId) }));

  // Role and messages travel together in one state object, so an in-place
  // navigation to another role cannot write one role's thread under the other's key.
  useEffect(() => {
    if (thread.roleId === roleId) return;
    setThread({ roleId, messages: readThread(roleId) });
  }, [roleId, thread.roleId]);

  useEffect(() => {
    if (paused || thread.roleId !== roleId) return;
    writeThread(thread.roleId, thread.messages);
  }, [thread, roleId, paused]);

  const setMessages = useCallback((update: SetStateAction<ChatMessage[]>) => {
    setThread((current) => ({
      roleId: current.roleId,
      messages: typeof update === "function" ? update(current.messages) : update,
    }));
  }, []);

  const clear = useCallback(() => setMessages([]), [setMessages]);

  // While the role is switching, the loaded thread still belongs to the old role:
  // expose nothing for that one frame rather than the wrong conversation.
  return { messages: thread.roleId === roleId ? thread.messages : [], setMessages, clear };
}
