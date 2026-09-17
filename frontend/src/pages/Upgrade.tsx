import { useState } from "react";
import { ApiError, billingApi } from "../api/client";

export function Upgrade() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleUpgrade() {
    setLoading(true);
    setError(null);
    try {
      const { checkout_url } = await billingApi.createCheckout();
      window.location.href = checkout_url;
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e.message
          : "Couldn't start checkout — try again in a moment."
      );
      setLoading(false);
    }
  }

  return (
    <div className="view" style={{ alignItems: "center", justifyContent: "center", textAlign: "center" }}>
      <div style={{ maxWidth: 480, margin: "0 auto" }}>
        <h2>Upgrade to Pro</h2>
        <p style={{ color: "var(--ink-soft)" }}>
          More questions per day, more conversations, more room to cook — for PKR 5,000/year.
        </p>
        {error && <div className="error-text">{error}</div>}
        <button
          className="primary-button"
          onClick={handleUpgrade}
          disabled={loading}
          style={{ marginTop: "var(--space-4)" }}
        >
          {loading ? "Redirecting…" : "Upgrade — PKR 5,000/year"}
        </button>
      </div>
    </div>
  );
}