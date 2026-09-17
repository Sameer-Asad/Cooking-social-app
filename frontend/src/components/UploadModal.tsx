import { useState, type ChangeEvent } from "react";
import { ApiError, feedApi, type MediaType, type Post } from "../api/client";

interface Props {
  onClose: () => void;
  onUploaded: (post: Post) => void;
}

export function UploadModal({ onClose, onUploaded }: Props) {
  const [description, setDescription] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [mediaType, setMediaType] = useState<MediaType | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function handleFileChange(e: ChangeEvent<HTMLInputElement>) {
    const picked = e.target.files?.[0] ?? null;
    if (!picked) {
      setFile(null);
      setMediaType(null);
      return;
    }
    // AC-5 / edge case: only one media type per post — this input only
    // ever lets you pick one file at a time, but we still detect its
    // type explicitly for the request payload (image vs video field).
    const type: MediaType = picked.type.startsWith("video/") ? "video" : "image";
    setFile(picked);
    setMediaType(type);
  }

  async function handleSubmit() {
    if (!file || !mediaType || !description.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const post = await feedApi.upload(description, { file, type: mediaType });
      onUploaded(post);
      onClose();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't upload that post.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(32, 28, 22, 0.5)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "var(--space-4)",
      }}
      onClick={onClose}
    >
      <div
        className="auth-shell"
        style={{ margin: 0, background: "var(--paper)", width: "100%", maxWidth: 420 }}
        onClick={(e) => e.stopPropagation()}
      >
        <h2>Share a dish</h2>
        <input type="file" accept="image/*,video/*" onChange={handleFileChange} />
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="How did you make it?"
          rows={4}
          style={{
            border: "1px solid var(--steam-line)",
            borderRadius: "var(--radius-card)",
            padding: "var(--space-3)",
            background: "var(--steam)",
            color: "var(--ink)",
            resize: "vertical",
          }}
        />
        {error && <div className="error-text">{error}</div>}
        <div style={{ display: "flex", gap: "var(--space-2)" }}>
          <button className="primary-button" onClick={handleSubmit} disabled={submitting}>
            {submitting ? "Uploading…" : "Post"}
          </button>
          <button className="auth-toggle" onClick={onClose}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
