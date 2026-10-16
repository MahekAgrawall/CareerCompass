import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import Alert from "@/components/Alert";
import EmptyState from "@/components/EmptyState";
import { QueryState } from "@/components/QueryState";
import * as endpoints from "@/api/endpoints";
import { ApiError, isAbortError } from "@/api/client";
import type { ChatMessage } from "@/api/types";
import { useDocumentTitle } from "@/lib/hooks";
import { useProfile } from "@/state/ProfileContext";
import { useRoadmapCache } from "@/state/RoadmapContext";

function suggestions(roleTitle: string): string[] {
  return [
    `How should I split my 1.5 hours/day between DSA and ${roleTitle} projects?`,
    "What specific interview questions will Indian tech recruiters ask me?",
    "Which of the 3 recommended projects should I push to GitHub first?",
    "How do I explain my lack of prior work experience during technical rounds?",
  ];
}

export default function ChatPage() {
  const { roleId = "" } = useParams();
  const { profile } = useProfile();
  const { getRoadmap } = useRoadmapCache();

  const roleQuery = useQuery({
    queryKey: ["role", roleId],
    queryFn: () => endpoints.getRole(roleId),
    enabled: Boolean(roleId),
  });

  const role = roleQuery.data;
  const roadmap = roleId ? getRoadmap(roleId) : null;

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useDocumentTitle(role ? `Copilot · ${role.title}` : "Roadmap Copilot");

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streaming]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const send = async (text: string) => {
    const trimmed = text.trim();
    if (!role || !roadmap || !trimmed || streaming) return;

    const history = messages;
    setError(null);
    setInput("");
    setStreaming(true);
    setMessages([...history, { role: "user", content: trimmed }, { role: "model", content: "" }]);

    const controller = new AbortController();
    abortRef.current = controller;
    const timeout = window.setTimeout(
      () => controller.abort(new DOMException("Request timed out", "TimeoutError")),
      120_000,
    );

    try {
      await endpoints.streamChat(
        { roleId: role.id, roadmap, message: trimmed, history, profile: profile ?? {} },
        (chunk) => {
          setMessages((prev) => {
            const copy = [...prev];
            const last = copy[copy.length - 1];
            copy[copy.length - 1] = { role: "model", content: last.content + chunk };
            return copy;
          });
        },
        controller.signal,
      );
    } catch (err) {
      // A navigation/unmount abort is expected — leave the partial reply in place.
      if (err instanceof DOMException && err.name === "AbortError") return;
      setError(
        isAbortError(err)
          ? "The AI took too long to respond. Please try again."
          : err instanceof ApiError
            ? err.message
            : "Could not reach the AI right now.",
      );
      setMessages((prev) => {
        const copy = [...prev];
        const last = copy[copy.length - 1];
        if (last?.role === "model" && last.content === "") copy.pop();
        return copy;
      });
    } finally {
      window.clearTimeout(timeout);
      setStreaming(false);
      abortRef.current = null;
    }
  };

  return (
    <QueryState isLoading={roleQuery.isLoading} error={roleQuery.error} loadingLabel="Loading copilot…">
      {role && !roadmap && (
        <EmptyState
          icon="🗺️"
          title="Generate a roadmap first"
          description="The copilot is pre-loaded with your target role and generated roadmap. Create one to start chatting."
          action={
            <Link to={`/roadmap/${role.id}`} className="btn btn-primary">
              Generate AI Skill Roadmap
            </Link>
          }
        />
      )}

      {role && roadmap && (
        <div className="flex min-h-[70vh] flex-col">
          <h1 className="section-title">💬 Roadmap Copilot: {role.title}</h1>
          <p className="caption mt-1">
            AI career mentor pre-loaded with your background, target role, and generated roadmap.
          </p>
          <hr className="my-5 border-slate-200" />

          <div className="flex-1 space-y-4">
            {messages.length === 0 && (
              <div>
                <p className="mb-3 text-sm font-semibold text-slate-700">
                  💡 High-impact questions to ask your copilot:
                </p>
                <div className="grid gap-2 sm:grid-cols-2">
                  {suggestions(role.title).map((text) => (
                    <button
                      key={text}
                      type="button"
                      className="card card-hover px-4 py-3 text-left text-sm text-slate-700"
                      onClick={() => void send(text)}
                    >
                      {text}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((message, index) => (
              <div
                key={index}
                className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm ${
                    message.role === "user"
                      ? "bg-brand-600 text-white"
                      : "border border-slate-200 bg-white text-slate-700"
                  }`}
                >
                  {message.role === "model" && (
                    <span className="mr-1.5" aria-hidden="true">
                      🧭
                    </span>
                  )}
                  {message.content || (
                    <span className="inline-flex gap-1 text-slate-400">
                      <span className="animate-pulse">●</span>
                      <span className="animate-pulse [animation-delay:150ms]">●</span>
                      <span className="animate-pulse [animation-delay:300ms]">●</span>
                    </span>
                  )}
                </div>
              </div>
            ))}

            {error && <Alert tone="error">{error}</Alert>}
            <div ref={bottomRef} />
          </div>

          <form
            className="sticky bottom-0 mt-5 flex gap-2 border-t border-slate-200 bg-slate-50 pt-4"
            onSubmit={(event) => {
              event.preventDefault();
              void send(input);
            }}
          >
            <input
              className="input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={`Ask any question about your ${role.title} roadmap…`}
              disabled={streaming}
            />
            <button type="submit" className="btn btn-primary" disabled={streaming || !input.trim()}>
              {streaming ? "…" : "Send"}
            </button>
          </form>

          <hr className="my-5 border-slate-200" />
          <div className="flex flex-wrap gap-3">
            <Link to={`/roadmap/${role.id}`} className="btn btn-secondary">
              ← Back to Roadmap
            </Link>
            <button
              type="button"
              className="btn btn-danger ml-auto"
              onClick={() => setMessages([])}
              disabled={messages.length === 0 || streaming}
            >
              🗑️ Clear Conversation
            </button>
          </div>
        </div>
      )}
    </QueryState>
  );
}
