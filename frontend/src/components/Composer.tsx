import { useRef, useState } from "react";
import { ApiError, botApi, ragApi, type BotStreamMeta, type BotStreamDone } from "../api/client";

interface Props {
  conversationId: string;
  disabled: boolean;
  onUserMessage: (text: string) => void;
  onMeta: (meta: BotStreamMeta) => void;
  onStatus: (tool: string) => void;
  onToken: (text: string) => void;
  onDone: (done: BotStreamDone) => void;
  onStreamError: (message: string) => void;
}

function MicIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="9" y="2" width="6" height="12" rx="3" />
      <path d="M5 10a7 7 0 0 0 14 0" />
      <line x1="12" y1="19" x2="12" y2="22" />
    </svg>
  );
}

function StopIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
      <rect x="5" y="5" width="14" height="14" rx="2" />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  );
}

function DocumentIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
    </svg>
  );
}

export function Composer({
  conversationId,
  disabled,
  onUserMessage,
  onMeta,
  onStatus,
  onToken,
  onDone,
  onStreamError,
}: Props) {
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [reviewNotice, setReviewNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attachedDocName, setAttachedDocName] = useState<string | null>(null);
  const [removingDoc, setRemovingDoc] = useState(false);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function handleMeta(meta: BotStreamMeta, opts: { alreadyAnnounced: boolean }) {
    if (meta.needs_review) {
      setText(meta.question_text);
      setReviewNotice(
        `This ${meta.detected_language === "ur" ? "Urdu" : "Hindi"} transcript may contain recognition errors — please review and edit before sending.`
      );
      return;
    }
    setReviewNotice(null);
    // For a typed question we already showed the bubble optimistically
    // before the request went out; for a voice question, this "meta"
    // frame is the first moment we actually know the transcribed text,
    // so the parent creates the bubble here instead.
    if (!opts.alreadyAnnounced) onUserMessage(meta.question_text);
    onMeta(meta);
  }

  async function handleSendText() {
    if (!text.trim() || sending) return;
    const sentText = text;
    setSending(true);
    setError(null);
    setText("");
    onUserMessage(sentText);
    try {
      await botApi.askQuestionStream(
        conversationId,
        { text: sentText },
        {
          onMeta: (meta) => handleMeta(meta, { alreadyAnnounced: true }),
          onStatus: (s) => onStatus(s.tool),
          onToken: (t) => onToken(t),
          onDone: (d) => onDone(d),
          onError: (msg) => {
            setError(msg);
            onStreamError(msg);
          },
        }
      );
    } catch (e) {
      const message = e instanceof ApiError ? e.message : "Couldn't send that — try again.";
      setError(message);
      onStreamError(message);
    } finally {
      setSending(false);
    }
  }

  async function handleFilesPicked(e: React.ChangeEvent<HTMLInputElement>) {
    const picked = Array.from(e.target.files ?? []);
    e.target.value = "";
    if (!picked.length) return;

    // Sec 4.5: only one document is indexed per user at a time —
    // uploading a new one silently supersedes whatever was indexed
    // before, so the badge only ever needs to reflect the latest file.
    const file = picked[0];
    setSending(true);
    setError(null);
    try {
      await ragApi.uploadDocument(conversationId, file);
      setAttachedDocName(file.name);
    } catch (e2) {
      setError(e2 instanceof ApiError ? e2.message : "Couldn't process that document.");
    } finally {
      setSending(false);
    }
  }

  async function handleRemoveDocument() {
    setRemovingDoc(true);
    setError(null);
    try {
      await ragApi.disableDocument(conversationId);
      setAttachedDocName(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't remove that document.");
    } finally {
      setRemovingDoc(false);
    }
  }

  async function startRecording() {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        setSending(true);
        setError(null);
        try {
          await botApi.askQuestionStream(
            conversationId,
            { audio: blob },
            {
              onMeta: (meta) => handleMeta(meta, { alreadyAnnounced: false }),
              onStatus: (s) => onStatus(s.tool),
              onToken: (t) => onToken(t),
              onDone: (d) => onDone(d),
              onError: (msg) => {
                setError(msg);
                onStreamError(msg);
              },
            }
          );
        } catch (e) {
          const message = e instanceof ApiError ? e.message : "Couldn't process that recording.";
          setError(message);
          onStreamError(message);
        } finally {
          setSending(false);
        }
      };
      mediaRecorderRef.current = recorder;
      recorder.start();
      setIsRecording(true);
    } catch {
      setError("Microphone access was denied or unavailable.");
    }
  }

  function stopRecording() {
    mediaRecorderRef.current?.stop();
    setIsRecording(false);
  }

  return (
    <div className="composer" style={{ width: "100%", boxSizing: "border-box" }}>
      {attachedDocName && (
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            padding: "4px 10px",
            borderRadius: "var(--radius-card)",
            background: "var(--steam)",
            border: "1px solid var(--steam-line)",
            fontSize: "0.8rem",
            marginBottom: "var(--space-2)",
            maxWidth: "100%",
          }}
        >
          <DocumentIcon />
          <span
            style={{
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              maxWidth: 220,
            }}
            title={attachedDocName}
          >
            {attachedDocName}
          </span>
          <span style={{ color: "var(--ink-faint)" }}>· this conversation is using this document</span>
          <button
            type="button"
            onClick={handleRemoveDocument}
            disabled={removingDoc}
            aria-label={`Remove ${attachedDocName}`}
            title="Remove document"
            style={{ background: "none", border: "none", cursor: "pointer", color: "var(--ink-faint)", padding: 0 }}
          >
            ×
          </button>
        </div>
      )}

      {reviewNotice && <div className="edit-review-banner">{reviewNotice}</div>}
      {error && <div className="error-text">{error}</div>}

      <div
        className="composer-row"
        style={{ display: "flex", alignItems: "flex-end", gap: "var(--space-2)", width: "100%", boxSizing: "border-box" }}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.docx,.txt,.md"
          style={{ display: "none" }}
          onChange={handleFilesPicked}
        />
        <button
          type="button"
          className="icon-button"
          onClick={() => fileInputRef.current?.click()}
          disabled={disabled || sending}
          aria-label="Attach a document"
          title="Attach a document"
        >
          <PlusIcon />
        </button>
        <button
          type="button"
          className={`icon-button${isRecording ? " recording" : ""}`}
          onClick={isRecording ? stopRecording : startRecording}
          disabled={disabled || sending}
          aria-label={isRecording ? "Stop recording" : "Record a voice question"}
          title={isRecording ? "Stop recording" : "Record a voice question"}
        >
          {isRecording ? <StopIcon /> : <MicIcon />}
        </button>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Ask about a recipe, in any language…"
          disabled={disabled || sending || isRecording}
          style={{ flex: 1, minWidth: 0 }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSendText();
            }
          }}
        />
        <button
          type="button"
          className="send-button"
          onClick={handleSendText}
          disabled={disabled || sending || isRecording || !text.trim()}
          aria-label="Send"
        >
          →
        </button>
      </div>
    </div>
  );
}