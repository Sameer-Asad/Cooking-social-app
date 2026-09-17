import { useCallback, useEffect, useState } from "react";

const STORAGE_KEY = "dastarkhwan:conversationTitles";

function loadTitles(): Record<string, string> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function firstWords(text: string, count = 5): string {
  const words = text.trim().split(/\s+/).filter(Boolean);
  const slice = words.slice(0, count).join(" ");
  return words.length > count ? `${slice}…` : slice;
}

// Titles are client-only (the backend has no title field on a
// conversation), persisted to localStorage so a reload doesn't lose them.
export function useConversationTitles() {
  const [titles, setTitles] = useState<Record<string, string>>(() => loadTitles());

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(titles));
    } catch {
      // storage unavailable — titles just won't persist across reloads
    }
  }, [titles]);

  const getTitle = useCallback((id: string) => titles[id] ?? "Untitled", [titles]);

  // Only takes effect the first time — later messages in the same
  // session shouldn't keep renaming it.
  const setTitleFromFirstMessage = useCallback((id: string, text: string) => {
    setTitles((prev) => (prev[id] ? prev : { ...prev, [id]: firstWords(text) }));
  }, []);

  const removeTitle = useCallback((id: string) => {
    setTitles((prev) => {
      if (!(id in prev)) return prev;
      const next = { ...prev };
      delete next[id];
      return next;
    });
  }, []);

  return { getTitle, setTitleFromFirstMessage, removeTitle };
}