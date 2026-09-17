import { useState } from "react";
import { AuthGate } from "./components/AuthGate";
import { NavBar } from "./components/NavBar";
import { COLLAPSED_WIDTH, SIDEBAR_WIDTH } from "./components/SessionSidebar";
import { useAuth } from "./hooks/useAuth";
import { useIsMobile } from "./hooks/useIsMobile";
import { BotChat } from "./pages/BotChat";
import { Feed } from "./pages/Feed";
import { Profile } from "./pages/Profile";
import { Upgrade } from "./pages/Upgrade";

type Tab = "chat" | "feed" | "profile" | "upgrade";

export default function App() {
  const { user, loading, error, login, signup, logout, setUsername } = useAuth();
  const [tab, setTab] = useState<Tab>("chat");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() =>
    typeof window !== "undefined" ? window.matchMedia("(max-width: 768px)").matches : false
  );
  const isMobile = useIsMobile();

  if (loading) return <div className="empty-state">Loading…</div>;

  if (!user) {
    return (
      <div className="app-shell">
        <AuthGate onLogin={login} onSignup={signup} error={error} />
      </div>
    );
  }

  const shift = !isMobile && tab === "chat" ? (sidebarCollapsed ? COLLAPSED_WIDTH : SIDEBAR_WIDTH) : 0;

  return (
    <div
      className="app-shell"
      style={{ display: "flex", flexDirection: "column", height: "100vh", width: "100vw", overflow: "hidden", maxWidth: "none" }}
    >
      <div style={{ marginLeft: shift, transition: "margin-left 0.15s ease", borderBottom: "1px solid var(--steam-line)" }}>
        <NavBar active={tab} onChange={setTab} onLogout={logout} displayName={user.display_name} />
      </div>
      <div style={{ flex: 1, minHeight: 0, marginLeft: shift, transition: "margin-left 0.15s ease" }}>
        {tab === "chat" && (
          <BotChat sidebarCollapsed={sidebarCollapsed} onSidebarCollapsedChange={setSidebarCollapsed} />
        )}
        {tab === "feed" && (
          <div style={{ height: "100%", overflowY: "auto" }}>
            <Feed />
          </div>
        )}
        {tab === "profile" && (
          <div style={{ height: "100%", overflowY: "auto" }}>
            <Profile user={user} onSetUsername={setUsername} />
          </div>
        )}
        {tab === "upgrade" && (
          <div style={{ height: "100%", overflowY: "auto" }}>
            <Upgrade />
          </div>
        )}
      </div>
    </div>
  );
}