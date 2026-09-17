interface Props {
  active: "chat" | "feed" | "profile" | "upgrade";
  onChange: (tab: "chat" | "feed" | "profile" | "upgrade") => void;
  onLogout: () => void;
  displayName: string;
}

export function NavBar({ active, onChange, onLogout, displayName }: Props) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        flexWrap: "wrap",
        gap: "var(--space-2)",
        padding: "var(--space-3) var(--space-4) 0",
      }}
    >
      <div className="tab-nav" style={{ border: "none", padding: 0 }}>
        <button className={active === "chat" ? "active" : ""} onClick={() => onChange("chat")}>
          Ask
        </button>
        <button className={active === "feed" ? "active" : ""} onClick={() => onChange("feed")}>
          Feed
        </button>
        <button className={active === "profile" ? "active" : ""} onClick={() => onChange("profile")}>
          Profile
        </button>
        <button className={active === "upgrade" ? "active" : ""} onClick={() => onChange("upgrade")}>
          Upgrade
        </button>
      </div>
      <button className="primary-button" onClick={onLogout} title={displayName} style={{ flexShrink: 0 }}>
        Sign out
      </button>
    </div>
  );
}