import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ChatMessage } from "./ChatMessage";
import type { MessageOut } from "../api/client";

function makeMessage(overrides: Partial<MessageOut> = {}): MessageOut {
  return {
    id: "msg-1",
    role: "assistant",
    content: "Preheat the oven to 180C.",
    detected_language: "en",
    audio_url: "/media/audio/msg-1.mp3",
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("ChatMessage", () => {
  it("renders a user message as a plain bubble, with no recipe card or badge", () => {
    render(<ChatMessage message={makeMessage({ role: "user", content: "How do I make dal?" })} />);
    expect(screen.getByText("How do I make dal?")).toBeInTheDocument();
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
    expect(document.querySelector(".recipe-card")).not.toBeInTheDocument();
    expect(document.querySelector(".user-bubble")).toBeInTheDocument();
  });

  it("renders an assistant message as a recipe card with a language badge", () => {
    render(<ChatMessage message={makeMessage()} />);
    expect(screen.getByText("Preheat the oven to 180C.")).toBeInTheDocument();
    expect(screen.getByText(/English/)).toBeInTheDocument();
    expect(document.querySelector(".recipe-card")).toBeInTheDocument();
  });

  it("flags an unverified (non-en/ur/hi) language in the badge", () => {
    render(<ChatMessage message={makeMessage({ detected_language: "fr" })} />);
    expect(screen.getByText(/French/)).toBeInTheDocument();
    expect(screen.getByText(/unverified/)).toBeInTheDocument();
  });

  it("does not flag a validated language as unverified", () => {
    render(<ChatMessage message={makeMessage({ detected_language: "ur" })} />);
    expect(screen.queryByText(/unverified/)).not.toBeInTheDocument();
  });

  it("shows the confidence percentage and applies low-confidence styling below the threshold", () => {
    render(<ChatMessage message={makeMessage()} languageConfidence={0.42} />);
    expect(screen.getByText(/42%/)).toBeInTheDocument();
    const badge = document.querySelector(".recipe-card-badge");
    expect(badge).toHaveClass("low-confidence");
  });

  it("does not apply low-confidence styling at or above the threshold", () => {
    render(<ChatMessage message={makeMessage()} languageConfidence={0.8} />);
    const badge = document.querySelector(".recipe-card-badge");
    expect(badge).not.toHaveClass("low-confidence");
  });

  it("renders an audio player when audio_url is present", () => {
    render(<ChatMessage message={makeMessage({ audio_url: "/media/audio/x.mp3" })} />);
    const audio = document.querySelector("audio");
    expect(audio).toBeInTheDocument();
    expect(audio).toHaveAttribute("src", "/media/audio/x.mp3");
    expect(screen.queryByText(/Audio isn't available/)).not.toBeInTheDocument();
  });

  it("renders the degraded-audio notice, not a broken player, when audio_url is null (Sec 9)", () => {
    render(<ChatMessage message={makeMessage({ audio_url: null })} />);
    expect(document.querySelector("audio")).not.toBeInTheDocument();
    expect(screen.getByText(/Audio isn't available for this reply right now/)).toBeInTheDocument();
  });
});
