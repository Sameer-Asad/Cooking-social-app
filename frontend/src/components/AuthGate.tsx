import { useState, type FormEvent } from "react";

interface Props {
  onLogin: (email: string, password: string) => Promise<void>;
  onSignup: (email: string, password: string, username?: string) => Promise<void>;
  error: string | null;
}

const AUTH_SHELL_WIDTH = 435;

export function AuthGate({ onLogin, onSignup, error }: Props) {
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [username, setUsername] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      if (mode === "login") {
        await onLogin(email, password);
      } else if (username.trim()) {
        await onSignup(email, password, username.trim());
      } else {
        await onSignup(email, password);
      }
    } catch {
      // error surfaced via the `error` prop from useAuth
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="auth-shell" style={{ maxWidth: AUTH_SHELL_WIDTH }}>
      <h1>
        <span className="wordmark-mark">Dastar</span>khwan
      </h1>
      <p style={{ color: "var(--ink-soft)", margin: 0 }}>
        {mode === "login"
          ? "Sign in to ask, cook, and share."
          : "Create an account to get started."}
      </p>

      <div
        role="tablist"
        style={{
          display: "flex",
          border: "1px solid var(--steam-line)",
          borderRadius: "var(--radius-card)",
          overflow: "hidden",
          width: "100%",
        }}
      >
        <button
          type="button"
          role="tab"
          aria-selected={mode === "login"}
          onClick={() => setMode("login")}
          style={{
            flex: 1,
            padding: "var(--space-3)",
            background: mode === "login" ? "var(--ink)" : "var(--steam)",
            color: mode === "login" ? "var(--paper)" : "var(--ink-soft)",
            border: "none",
            fontWeight: 500,
            fontSize: 14,
            cursor: "pointer",
          }}
        >
          Login
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mode === "signup"}
          onClick={() => setMode("signup")}
          style={{
            flex: 1,
            padding: "var(--space-3)",
            background: mode === "signup" ? "var(--ink)" : "var(--steam)",
            color: mode === "signup" ? "var(--paper)" : "var(--ink-soft)",
            border: "none",
            fontWeight: 500,
            fontSize: 14,
            cursor: "pointer",
          }}
        >
          Sign up
        </button>
      </div>

      <form onSubmit={handleSubmit}>
        <input
          type="email"
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          autoComplete="email"
        />
        {mode === "signup" && (
          <input
            type="text"
            placeholder="Username (optional — you can set this later too)"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            minLength={3}
            maxLength={50}
            autoComplete="username"
          />
        )}
        <input
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          minLength={8}
          autoComplete={mode === "login" ? "current-password" : "new-password"}
        />
        {error && <div className="error-text">{error}</div>}
        <button className="primary-button" type="submit" disabled={submitting}>
          {submitting ? "Please wait…" : mode === "login" ? "Sign in" : "Sign up"}
        </button>
      </form>
    </div>
  );
}