import { useEffect, useState } from "react";
import { ApiError, botApi, type ConversationOut } from "../api/client";
import { useIsMobile } from "../hooks/useIsMobile";

interface Props {
  activeConversationId: string | null;
  onSelect: (conversationId: string) => void;
  onCreateNew: () => void;
  refreshKey: number;
  getTitle: (id: string) => string;
  removeTitle: (id: string) => void;
  collapsed: boolean;
  onToggleCollapsed: (collapsed: boolean) => void;
}

const SIDEBAR_WIDTH = 260;
const COLLAPSED_WIDTH = 44;

function TrashIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
      <path d="M10 11v6" />
      <path d="M14 11v6" />
      <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
    </svg>
  );
}

export function SessionSidebar({
  activeConversationId,
  onSelect,
  onCreateNew,
  refreshKey,
  getTitle,
  removeTitle,
  collapsed,
  onToggleCollapsed,
}: Props) {
  const [conversations, setConversations] = useState<ConversationOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  const isMobile = useIsMobile();

  async function load() {
    try {
      const list = await botApi.listConversations();
      setConversations(list);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't load your sessions.");
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey]);

  async function handleDelete(id: string, e: React.MouseEvent) {
    e.stopPropagation();
    try {
      await botApi.deleteConversation(id);
      setConversations((prev) => prev.filter((c) => c.id !== id));
      removeTitle(id);
      if (id === activeConversationId) onCreateNew();
    } catch (e2) {
      setError(e2 instanceof ApiError ? e2.message : "Couldn't delete that session.");
    }
  }

  function handleSelect(id: string) {
    onSelect(id);
    if (isMobile) onToggleCollapsed(true); // tapping a session closes the drawer on mobile
  }

  const width = collapsed ? COLLAPSED_WIDTH : SIDEBAR_WIDTH;

  return (
    <>
      {isMobile && !collapsed && (
        <div
          onClick={() => onToggleCollapsed(true)}
          aria-label="Close sessions sidebar"
          style={{ position: "fixed", inset: 0, background: "rgba(32, 28, 22, 0.4)", zIndex: 9 }}
        />
      )}
      <div
        style={{
          position: "fixed",
          top: 0,
          left: 0,
          bottom: 0,
          width,
          flexShrink: 0,
          display: "flex",
          flexDirection: "column",
          borderRight: "1px solid var(--steam-line)",
          background: "var(--paper)",
          zIndex: 10,
          overflow: "hidden",
        }}
      >
        {collapsed ? (
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", paddingTop: "var(--space-3)" }}>
            <button className="icon-button" onClick={() => onToggleCollapsed(false)} aria-label="Open sessions sidebar" title="Open sidebar">
              »
            </button>
          </div>
        ) : (
          <>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "var(--space-3)" }}>
              <div className="wordmark" style={{ fontSize: "1.05rem" }}>
                <span className="wordmark-mark">Dastar</span>khwan
              </div>
              <button className="icon-button" onClick={() => onToggleCollapsed(true)} aria-label="Close sessions sidebar" title="Close sidebar">
                «
              </button>
            </div>

            <div style={{ padding: "0 var(--space-3) var(--space-3)" }}>
              <button className="primary-button" onClick={onCreateNew} style={{ width: "100%" }}>
                + New
              </button>
            </div>

            {error && <div className="error-text" style={{ padding: "0 var(--space-3)" }}>{error}</div>}

            <div style={{ flex: 1, overflowY: "auto", padding: "0 var(--space-2) var(--space-3)", display: "flex", flexDirection: "column", gap: "var(--space-1)" }}>
              {conversations.map((c) => (
                <div
                  key={c.id}
                  onClick={() => handleSelect(c.id)}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    gap: "var(--space-2)",
                    padding: "var(--space-2)",
                    borderRadius: "var(--radius-card)",
                    cursor: "pointer",
                    background: c.id === activeConversationId ? "var(--steam)" : "transparent",
                  }}
                >
                  <div style={{ overflow: "hidden" }}>
                    <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: "0.9rem" }}>
                      {getTitle(c.id)}
                      {c.is_locked && " · closed"}
                    </div>
                    <div style={{ fontSize: "0.75rem", color: "var(--ink-faint)" }}>
                      {new Date(c.created_at).toLocaleString()}
                    </div>
                  </div>
                  <button
                    className="icon-button"
                    onClick={(e) => handleDelete(c.id, e)}
                    aria-label="Delete session"
                    title="Delete session"
                    style={{ color: "var(--ink-faint)" }}
                  >
                    <TrashIcon />
                  </button>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </>
  );
}

export { SIDEBAR_WIDTH, COLLAPSED_WIDTH };