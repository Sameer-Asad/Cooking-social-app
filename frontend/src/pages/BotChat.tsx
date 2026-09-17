import { useEffect, useRef, useState } from "react";
import { ApiError, botApi, type BotStreamDone, type BotStreamMeta, type MessageOut } from "../api/client";
import { ChatMessage, StreamingExchange } from "../components/ChatMessage";
import { Composer } from "../components/Composer";
import { SessionSidebar } from "../components/SessionSidebar";
import { useConversationTitles } from "../hooks/useConversationTitles";

interface Props {
  sidebarCollapsed: boolean;
  onSidebarCollapsedChange: (collapsed: boolean) => void;
}

interface StreamingState {
  question: string;
  answerText: string;
  status: string | null;
  detectedLanguage: string;
  languageConfidence: number;
  audioUrl: string | null;
  finished: boolean;
}

export function BotChat({ sidebarCollapsed, onSidebarCollapsedChange }: Props) {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<MessageOut[]>([]);
  const [locked, setLocked] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionListKey, setSessionListKey] = useState(0);
  const [initializing, setInitializing] = useState(true);
  const [streaming, setStreaming] = useState<StreamingState | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const conversationIdRef = useRef<string | null>(null);
  const didInitRef = useRef(false);
  const creatingRef = useRef(false); // guards "+ New" against double-clicks/double-invokes
  const { getTitle, setTitleFromFirstMessage, removeTitle } = useConversationTitles();

  useEffect(() => {
    conversationIdRef.current = conversationId;
  }, [conversationId]);

  // On open: pick up the most recent existing conversation. A new
  // conversation is only ever created by startNewConversation, below —
  // never automatically on mount.
  useEffect(() => {
    if (didInitRef.current) return;
    didInitRef.current = true;

    botApi
      .listConversations()
      .then((list) => {
        const mostRecent = list.find((c) => !c.is_locked) ?? list[0];
        if (mostRecent) setConversationId(mostRecent.id);
        setInitializing(false);
      })
      .catch((e) => {
        setError(e instanceof ApiError ? e.message : "Couldn't load your sessions.");
        setInitializing(false);
      });
  }, []);

  useEffect(() => {
    function handlePageHide() {
      const id = conversationIdRef.current;
      if (id) botApi.endSession(id);
    }
    window.addEventListener("pagehide", handlePageHide);
    return () => window.removeEventListener("pagehide", handlePageHide);
  }, []);

  async function refreshMessages() {
    if (!conversationId) return;
    try {
      const msgs = await botApi.listMessages(conversationId);
      setMessages(msgs);
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) setLocked(true);
    }
    setSessionListKey((k) => k + 1);
  }

  useEffect(() => {
    if (conversationId) refreshMessages();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId]);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, streaming]);

  async function startNewConversation() {
    if (creatingRef.current) return;
    creatingRef.current = true;
    try {
      setLocked(false);
      setMessages([]);
      setError(null);
      setStreaming(null);
      const c = await botApi.createConversation();
      setConversationId(c.id);
      setSessionListKey((k) => k + 1);
    } finally {
      creatingRef.current = false;
    }
  }

  async function selectConversation(id: string) {
    setLocked(false);
    setError(null);
    setStreaming(null);
    setConversationId(id);
  }

  // ── Streaming callbacks passed down to Composer ──────────────────────
  // Order of events for a typed question: onUserMessage fires immediately
  // (we already know the text), then onMeta patches in the detected
  // language once it arrives. For a voice question we don't know the
  // transcript yet when recording stops, so onUserMessage is skipped and
  // onMeta itself creates the streaming bubble using question_text.

  function handleUserMessage(text: string) {
    if (conversationId) setTitleFromFirstMessage(conversationId, text);
    setError(null);
    setStreaming({
      question: text,
      answerText: "",
      status: null,
      detectedLanguage: "en",
      languageConfidence: 1,
      audioUrl: null,
      finished: false,
    });
  }

  function handleMeta(meta: BotStreamMeta) {
    setStreaming((prev) => {
      if (prev) {
        return { ...prev, detectedLanguage: meta.detected_language, languageConfidence: meta.language_confidence };
      }
      // Voice question — this meta frame is the first time we know the
      // transcribed text, so create the bubble here instead.
      if (conversationId) setTitleFromFirstMessage(conversationId, meta.question_text);
      return {
        question: meta.question_text,
        answerText: "",
        status: null,
        detectedLanguage: meta.detected_language,
        languageConfidence: meta.language_confidence,
        audioUrl: null,
        finished: false,
      };
    });
  }

  function handleStatus(tool: string) {
    setStreaming((prev) => (prev ? { ...prev, status: tool } : prev));
  }

  function handleToken(token: string) {
    setStreaming((prev) => (prev ? { ...prev, answerText: prev.answerText + token, status: null } : prev));
  }

  async function handleDone(done: BotStreamDone) {
    setStreaming((prev) => (prev ? { ...prev, audioUrl: done.audio_url, finished: true } : prev));
    await refreshMessages();
    setStreaming(null);
  }

  function handleStreamError(message: string) {
    setError(message);
    setStreaming(null);
  }

  return (
    <div style={{ height: "100%", position: "relative" }}>
      <SessionSidebar
        activeConversationId={conversationId}
        onSelect={selectConversation}
        onCreateNew={startNewConversation}
        refreshKey={sessionListKey}
        getTitle={getTitle}
        removeTitle={removeTitle}
        collapsed={sidebarCollapsed}
        onToggleCollapsed={onSidebarCollapsedChange}
      />
      <div className="view" style={{ maxWidth: 900, margin: "0 auto", height: "100%", boxSizing: "border-box" }}>
        {error && <div className="error-text">{error}</div>}
        <div className="message-list" ref={listRef}>
          {!initializing && !conversationId && !error && (
            <div className="empty-state">Click "+ New" to start a conversation.</div>
          )}
          {conversationId && messages.length === 0 && !streaming && !error && (
            <div className="empty-state">
              Ask about a dish — by typing or by voice, in whichever language you like.
            </div>
          )}
          {messages.map((m) => (
            <ChatMessage key={m.id} message={m} />
          ))}
          {streaming && (
            <StreamingExchange
              question={streaming.question}
              answerText={streaming.answerText}
              status={streaming.status}
              audioUrl={streaming.audioUrl}
              finished={streaming.finished}
              detectedLanguage={streaming.detectedLanguage}
              languageConfidence={streaming.languageConfidence}
            />
          )}
        </div>
        {locked ? (
          <div className="composer">
            <div className="edit-review-banner">This conversation reached its message limit.</div>
            <button className="primary-button" onClick={startNewConversation}>
              Start a new conversation
            </button>
          </div>
        ) : (
          conversationId && (
            <Composer
              key={conversationId}
              conversationId={conversationId}
              disabled={!conversationId}
              onUserMessage={handleUserMessage}
              onMeta={handleMeta}
              onStatus={handleStatus}
              onToken={handleToken}
              onDone={handleDone}
              onStreamError={handleStreamError}
            />
          )
        )}
      </div>
    </div>
  );
}