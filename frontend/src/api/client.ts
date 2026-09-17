// All calls go through /api/* which vite.config.ts proxies to the
// backend (stripping the /api prefix) — see that file's comment.
// Auth is httpOnly-cookie based (Sec 6), so every call must send
// credentials, not an Authorization header.

const BASE = "/api";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

// If multiple requests hit a 401 at roughly the same time (e.g. several
// components fetch on mount), only one should trigger /auth/refresh —
// the rest wait on that same in-flight promise instead of each firing
// their own refresh call and racing to rotate the refresh token.
let refreshPromise: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
  if (!refreshPromise) {
    refreshPromise = fetch(`${BASE}/auth/refresh`, {
      method: "POST",
      credentials: "include",
    })
      .then((res) => res.ok)
      .catch(() => false)
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

async function rawRequest(path: string, init?: RequestInit): Promise<Response> {
  return fetch(`${BASE}${path}`, {
    ...init,
    credentials: "include",
    headers:
      init?.body instanceof FormData
        ? init.headers
        : { "Content-Type": "application/json", ...init?.headers },
  });
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res = await rawRequest(path, init);

  const isAuthEndpoint = path.startsWith("/auth/");

  if (res.status === 401 && !isAuthEndpoint) {
    const refreshed = await tryRefresh();
    if (refreshed) {
      res = await rawRequest(path, init);
    }
  }

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // response wasn't JSON — keep statusText
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ── SSE streaming helper ───────────────────────────────────────────────
// EventSource only supports GET, and this endpoint needs POST + FormData
// (text or an audio blob), so we parse the text/event-stream body by
// hand from a normal fetch() instead. Frames are separated by a blank
// line per the SSE spec; each frame we care about has an `event:` line
// and a `data:` line containing one JSON object.

export interface BotStreamMeta {
  conversation_id: string;
  detected_language: string;
  language_confidence: number;
  needs_review: boolean;
  question_text: string;
}

export interface BotStreamDone {
  message_id: string | null;
  audio_url: string | null;
  audio_degraded: boolean;
}

export interface BotStreamHandlers {
  onMeta?: (meta: BotStreamMeta) => void;
  onStatus?: (status: { tool: string }) => void;
  onToken?: (text: string) => void;
  onDone?: (done: BotStreamDone) => void;
  onError?: (message: string) => void;
}

async function streamRequest(
  path: string,
  init: RequestInit,
  handlers: BotStreamHandlers
): Promise<void> {
  async function doFetch(): Promise<Response> {
    return fetch(`${BASE}${path}`, {
      ...init,
      credentials: "include",
      headers: init.body instanceof FormData ? init.headers : { "Content-Type": "application/json", ...init.headers },
    });
  }

  let res = await doFetch();

  // Same 401 -> refresh -> retry-once behavior as request() above. The
  // access token is short-lived, and unlike the GET calls (conversation
  // list, message history) this endpoint wasn't going through request()
  // at all, so it had no refresh logic and just failed forever once the
  // token expired mid-session.
  if (res.status === 401) {
    const refreshed = await tryRefresh();
    if (refreshed) {
      res = await doFetch();
    }
  }

  if (!res.ok || !res.body) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // response wasn't JSON — keep statusText
    }
    handlers.onError?.(detail);
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let sepIndex: number;
    while ((sepIndex = buffer.indexOf("\n\n")) !== -1) {
      const rawFrame = buffer.slice(0, sepIndex);
      buffer = buffer.slice(sepIndex + 2);

      let eventType = "message";
      let dataLine = "";
      for (const line of rawFrame.split("\n")) {
        if (line.startsWith("event:")) eventType = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLine = line.slice(5).trim();
      }
      if (!dataLine) continue;

      let data: any;
      try {
        data = JSON.parse(dataLine);
      } catch {
        continue;
      }

      switch (eventType) {
        case "meta":
          handlers.onMeta?.(data);
          break;
        case "status":
          handlers.onStatus?.(data);
          break;
        case "token":
          handlers.onToken?.(data.text);
          break;
        case "done":
          handlers.onDone?.(data);
          break;
        case "error":
          handlers.onError?.(data.message);
          break;
      }
    }
  }
}

// ── Auth (routes_auth.py) ────────────────────────────────────────────

export interface User {
  id: string;
  email: string;
  username: string | null;
  display_name: string;
  is_paid_tier?: boolean;
}

export const authApi = {
  signup: (email: string, password: string, username?: string) =>
    request<User>("/auth/signup", {
      method: "POST",
      body: JSON.stringify(username ? { email, password, username } : { email, password }),
    }),
  login: (email: string, password: string) =>
    request<User>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  logout: () => request<{ ok: boolean }>("/auth/logout", { method: "POST" }),
  me: () => request<User>("/auth/me"),
  setUsername: (username: string) =>
    request<User>("/auth/me/username", {
      method: "PATCH",
      body: JSON.stringify({ username }),
    }),
};

// ── Bot (routes_bot.py) ───────────────────────────────────────────────

export interface BotQuestionResponse {
  conversation_id: string;
  detected_language: string;
  language_confidence: number;
  text: string;
  audio_url: string | null;
  audio_degraded: boolean;
  needs_review: boolean;
}

export interface MessageOut {
  id: string;
  role: "user" | "assistant";
  content: string;
  detected_language: string | null;
  audio_url: string | null;
  created_at: string;
}

export interface ConversationOut {
  id: string;
  created_at: string;
  last_message_at: string;
  is_locked: boolean;
  rag_enabled: boolean;
}

export const botApi = {
  createConversation: () =>
    request<{ id: string }>("/bot/conversations", { method: "POST" }),

  listConversations: () => request<ConversationOut[]>("/bot/conversations"),

  deleteConversation: (conversationId: string) =>
    request<{ ok: boolean }>(`/bot/conversations/${conversationId}`, { method: "DELETE" }),

  listMessages: (conversationId: string) =>
    request<MessageOut[]>(`/bot/conversations/${conversationId}/messages`),

  // Streaming version — used by Composer. The backend now returns
  // text/event-stream for this endpoint (see routes_bot.py), so this is
  // the one to use for asking a question; see streamRequest above for
  // the event sequence (meta -> status*/token* -> done, or error).
  askQuestionStream: (
    conversationId: string,
    args: { text?: string; audio?: Blob; languageHint?: string },
    handlers: BotStreamHandlers
  ) => {
    const form = new FormData();
    if (args.text) form.append("text", args.text);
    if (args.languageHint) form.append("language_hint", args.languageHint);
    if (args.audio) form.append("audio", args.audio, "question.webm");
    return streamRequest(`/bot/conversations/${conversationId}/messages`, { method: "POST", body: form }, handlers);
  },

  // Sec 4.4 trigger #3: best-effort tab-close signal. sendBeacon cannot
  // go through the normal request()/fetch wrapper — it fires
  // fire-and-forget with no response to read, which is the whole point
  // (it must complete even as the page is unloading). Same-origin
  // sendBeacon calls include cookies automatically, so the httpOnly
  // access_token cookie still authenticates this call.
  endSession: (conversationId: string) => {
    navigator.sendBeacon(`${BASE}/bot/conversations/${conversationId}/end-session`);
  },
};

// ── Feed (routes_feed.py) ─────────────────────────────────────────────

export type MediaType = "video" | "image";

export interface Post {
  id: string;
  author_id: string;
  media_type: MediaType;
  media_path: string;
  description: string;
  like_count: number;
  comment_count: number;
  created_at: string;
  liked_by_me: boolean;
}

export interface Comment {
  id: string;
  post_id: string;
  user_id: string;
  body: string;
  created_at: string;
}

export interface Liker {
  user_id: string;
  username: string | null;
  display_name: string;
  created_at: string;
}

export interface Profile {
  id: string;
  email: string;
  username: string | null;
  display_name: string;
  is_paid_tier: boolean;
  created_at: string;
  posts: Post[];
}

export const feedApi = {
  list: (limit = 20, offset = 0) =>
    request<Post[]>(`/feed/posts?limit=${limit}&offset=${offset}`),

  // AC-5: exactly one of video/image, plus a text description.
  upload: (description: string, media: { file: File; type: MediaType }) => {
    const form = new FormData();
    form.append("description", description);
    form.append(media.type, media.file);
    return request<Post>("/feed/posts", { method: "POST", body: form });
  },

  like: (postId: string) =>
    request<{ post_id: string; like_count: number }>(
      `/feed/posts/${postId}/like`,
      { method: "POST" }
    ),

  unlike: (postId: string) =>
    request<{ post_id: string; like_count: number }>(
      `/feed/posts/${postId}/like`,
      { method: "DELETE" }
    ),

  listLikers: (postId: string) => request<Liker[]>(`/feed/posts/${postId}/likes`),

  listComments: (postId: string) =>
    request<Comment[]>(`/feed/posts/${postId}/comments`),

  comment: (postId: string, body: string) =>
    request<Comment>(`/feed/posts/${postId}/comments`, {
      method: "POST",
      body: JSON.stringify({ body }),
    }),

  myProfile: () => request<Profile>("/feed/profile"),
};

// Media URLs returned by the backend are root-relative (e.g.
// "/media/audio/xxx.mp3" or a post's media_path like "images/xxx.jpg"
// which needs the /media/ prefix) — normalize both cases here.
export function mediaUrl(path: string): string {
  if (path.startsWith("/media/")) return path;
  return `/media/${path.replace(/^\/+/, "")}`;
}

export interface DocumentUploadResponse {
  conversation_id: string;
  rag_enabled: boolean;
  chunks_indexed: number;
}

export const ragApi = {
  uploadDocument: (conversationId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<DocumentUploadResponse>(
      `/bot/conversations/${conversationId}/document`,
      { method: "POST", body: form }
    );
  },
  disableDocument: (conversationId: string) =>
    request<DocumentUploadResponse>(
      `/bot/conversations/${conversationId}/document`,
      { method: "DELETE" }
    ),
};

export const billingApi = {
  createCheckout: () =>
    request<{ checkout_url: string }>("/billing/checkout", { method: "POST" }),
};