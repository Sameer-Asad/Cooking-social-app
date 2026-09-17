import { useEffect, useState } from "react";
import { ApiError, feedApi, mediaUrl, type Profile as ProfileData, type User } from "../api/client";

interface Props {
  user: User;
  onSetUsername: (username: string) => Promise<void>;
}

export function Profile({ user, onSetUsername }: Props) {
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [usernameInput, setUsernameInput] = useState("");
  const [savingUsername, setSavingUsername] = useState(false);
  const [usernameError, setUsernameError] = useState<string | null>(null);

  async function loadProfile() {
    setLoading(true);
    try {
      const data = await feedApi.myProfile();
      setProfile(data);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't load your profile.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadProfile();
  }, []);

  async function handleSaveUsername() {
    if (!usernameInput.trim()) return;
    setSavingUsername(true);
    setUsernameError(null);
    try {
      await onSetUsername(usernameInput.trim());
      setUsernameInput("");
      await loadProfile();
    } catch (e) {
      setUsernameError(e instanceof ApiError ? e.message : "Couldn't save that username.");
    } finally {
      setSavingUsername(false);
    }
  }

  if (loading) return <div className="empty-state">Loading…</div>;
  if (error) return <div className="error-text">{error}</div>;
  if (!profile) return null;

  return (
    <div className="view">
      <div className="feed-toolbar">
        <h2>{user.display_name}</h2>
      </div>

      <div className="auth-shell" style={{ margin: 0 }}>
        <div>
          <strong>Email:</strong> {profile.email}
        </div>
        <div>
          <strong>Username:</strong> {profile.username ?? "not set"}
        </div>
        <div>
          <strong>Plan:</strong> {profile.is_paid_tier ? "Paid" : "Free"}
        </div>

        {!user.username && (
          <div style={{ marginTop: "var(--space-3)" }}>
            <p style={{ color: "var(--ink-soft)", margin: "0 0 var(--space-2)" }}>
              You don't have a username yet — set one so others see it on your likes and comments.
            </p>
            <input
              type="text"
              placeholder="Choose a username"
              value={usernameInput}
              onChange={(e) => setUsernameInput(e.target.value)}
              minLength={3}
              maxLength={50}
            />
            {usernameError && <div className="error-text">{usernameError}</div>}
            <button
              className="primary-button"
              onClick={handleSaveUsername}
              disabled={savingUsername || !usernameInput.trim()}
              style={{ marginTop: "var(--space-2)" }}
            >
              {savingUsername ? "Saving…" : "Save username"}
            </button>
          </div>
        )}
      </div>

      <h3 style={{ marginTop: "var(--space-4)" }}>Your posts</h3>
      {profile.posts.length === 0 ? (
        <div className="empty-state">You haven't shared anything yet.</div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "var(--space-2)" }}>
          {profile.posts.map((p) => (
            <div
              key={p.id}
              style={{
                aspectRatio: "1 / 1",
                border: "1px solid var(--steam-line)",
                borderRadius: "var(--radius-card)",
                overflow: "hidden",
                background: "var(--ink)",
              }}
            >
              {p.media_type === "video" ? (
                <video
                  src={mediaUrl(p.media_path)}
                  muted
                  style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
                />
              ) : (
                <img
                  src={mediaUrl(p.media_path)}
                  alt={p.description}
                  style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
                />
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}