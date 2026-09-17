import { mediaUrl, type MessageOut } from "../api/client";
import { isValidatedLanguage, languageDisplayName } from "../api/languages";

interface Props {
  message: MessageOut;
  languageConfidence?: number; // only known for the message just received this session
}

export function ChatMessage({ message, languageConfidence }: Props) {
  if (message.role === "user") {
    return (
      <div className="message-row user">
        <div className="user-bubble">{message.content}</div>
      </div>
    );
  }

  const lang = message.detected_language;
  const lowConfidence =
    languageConfidence !== undefined && languageConfidence < 0.6;

  return (
    <div className="message-row assistant">
      <div className="recipe-card">
        {lang && (
          <span
            className={`recipe-card-badge${lowConfidence ? " low-confidence" : ""}`}
          >
            {languageDisplayName(lang)}
            {!isValidatedLanguage(lang) && " · unverified"}
            {languageConfidence !== undefined &&
              ` · ${Math.round(languageConfidence * 100)}%`}
          </span>
        )}
        <div className="recipe-card-text">{message.content}</div>
        {message.audio_url && (
          <audio controls src={mediaUrl(message.audio_url)} />
        )}
        {!message.audio_url && (
          <div className="recipe-card-degraded">
            Audio isn't available for this reply right now — text is still accurate.
          </div>
        )}
      </div>
    </div>
  );
}

interface StreamingExchangeProps {
  question: string;
  answerText: string;
  status: string | null;
  audioUrl: string | null;
  finished: boolean;
  detectedLanguage: string;
  languageConfidence: number;
}

// Renders the in-flight user question + assistant reply while a stream
// is still coming in: the question appears the moment it's known, the
// answer fills in token by token, and the audio player only appears
// once `finished` is true (the text-then-audio ordering the user asked
// for). Once the stream's "done" event lands, BotChat swaps this out
// for the real persisted <ChatMessage> pulled from the server.
export function StreamingExchange({
  question,
  answerText,
  status,
  audioUrl,
  finished,
  detectedLanguage,
  languageConfidence,
}: StreamingExchangeProps) {
  const lowConfidence = languageConfidence < 0.6;

  return (
    <>
      <div className="message-row user">
        <div className="user-bubble">{question}</div>
      </div>
      <div className="message-row assistant">
        <div className="recipe-card">
          <span className={`recipe-card-badge${lowConfidence ? " low-confidence" : ""}`}>
            {languageDisplayName(detectedLanguage)}
            {!isValidatedLanguage(detectedLanguage) && " · unverified"}
            {` · ${Math.round(languageConfidence * 100)}%`}
          </span>
          {answerText ? (
            <div className="recipe-card-text">
              {answerText}
              {!finished && <span className="stream-cursor">▍</span>}
            </div>
          ) : (
            <div className="recipe-card-text stream-loading">
              {status ? `Using ${status.replace(/_/g, " ")}…` : "Thinking…"}
            </div>
          )}
          {finished && audioUrl && <audio controls src={mediaUrl(audioUrl)} />}
          {finished && !audioUrl && (
            <div className="recipe-card-degraded">
              Audio isn't available for this reply right now — text is still accurate.
            </div>
          )}
        </div>
      </div>
    </>
  );
}