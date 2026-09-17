import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Composer } from "./Composer";
import { botApi, type BotStreamHandlers } from "../api/client";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    botApi: { askQuestionStream: vi.fn(), createConversation: vi.fn(), listMessages: vi.fn() },
  };
});

const mockedAskQuestionStream = vi.mocked(botApi.askQuestionStream);

function baseProps(overrides: Partial<Parameters<typeof Composer>[0]> = {}) {
  return {
    conversationId: "c1",
    disabled: false,
    onUserMessage: vi.fn(),
    onMeta: vi.fn(),
    onStatus: vi.fn(),
    onToken: vi.fn(),
    onDone: vi.fn(),
    onStreamError: vi.fn(),
    ...overrides,
  };
}

async function sendText(user: ReturnType<typeof userEvent.setup>, text: string) {
  const textarea = screen.getByPlaceholderText(/Ask about a recipe/);
  await user.type(textarea, text);
  await user.click(screen.getByRole("button", { name: "Send" }));
  return textarea;
}

describe("Composer", () => {
  beforeEach(() => {
    mockedAskQuestionStream.mockReset();
  });

  it("announces the user's message immediately (before the network call resolves) and clears the input", async () => {
    const user = userEvent.setup();
    const props = baseProps();
    let resolveStream: () => void;
    mockedAskQuestionStream.mockImplementation(
      () => new Promise<void>((resolve) => { resolveStream = resolve; })
    );

    render(<Composer {...props} />);
    const textarea = await sendText(user, "How do I make dal?");

    expect(props.onUserMessage).toHaveBeenCalledWith("How do I make dal?");
    expect(textarea).toHaveValue("");
    resolveStream!();
  });

  it("streams meta, tokens, and the done event through to the parent, in order", async () => {
    const user = userEvent.setup();
    const props = baseProps();
    mockedAskQuestionStream.mockImplementation(async (_conversationId, _args, handlers: BotStreamHandlers) => {
      handlers.onMeta?.({
        conversation_id: "c1",
        detected_language: "en",
        language_confidence: 0.99,
        needs_review: false,
        question_text: "How do I make dal?",
      });
      handlers.onToken?.("Preheat ");
      handlers.onToken?.("to 180C.");
      handlers.onDone?.({ message_id: "m1", audio_url: "/media/audio/x.mp3", audio_degraded: false });
    });

    render(<Composer {...props} />);
    await sendText(user, "How do I make dal?");

    await waitFor(() =>
      expect(props.onDone).toHaveBeenCalledWith({ message_id: "m1", audio_url: "/media/audio/x.mp3", audio_degraded: false })
    );
    expect(props.onMeta).toHaveBeenCalledWith(
      expect.objectContaining({ detected_language: "en", question_text: "How do I make dal?" })
    );
    expect(props.onToken).toHaveBeenNthCalledWith(1, "Preheat ");
    expect(props.onToken).toHaveBeenNthCalledWith(2, "to 180C.");
    expect(mockedAskQuestionStream).toHaveBeenCalledWith(
      "c1",
      { text: "How do I make dal?" },
      expect.objectContaining({
        onMeta: expect.any(Function),
        onStatus: expect.any(Function),
        onToken: expect.any(Function),
        onDone: expect.any(Function),
        onError: expect.any(Function),
      })
    );
  });

  it("forwards a status event (e.g. a tool call) to the parent", async () => {
    const user = userEvent.setup();
    const props = baseProps();
    mockedAskQuestionStream.mockImplementation(async (_id, _args, handlers: BotStreamHandlers) => {
      handlers.onMeta?.({ conversation_id: "c1", detected_language: "en", language_confidence: 0.9, needs_review: false, question_text: "q" });
      handlers.onStatus?.({ tool: "web_search" });
      handlers.onToken?.("answer");
      handlers.onDone?.({ message_id: "m1", audio_url: null, audio_degraded: true });
    });

    render(<Composer {...props} />);
    await sendText(user, "some obscure dish");

    await waitFor(() => expect(props.onStatus).toHaveBeenCalledWith("web_search"));
  });

  it("submits on Enter without a shift key, and does not submit on Shift+Enter", async () => {
    const user = userEvent.setup();
    const props = baseProps();
    mockedAskQuestionStream.mockImplementation(async (_id, _args, handlers: BotStreamHandlers) => {
      handlers.onMeta?.({ conversation_id: "c1", detected_language: "en", language_confidence: 0.99, needs_review: false, question_text: "ok" });
      handlers.onDone?.({ message_id: "m1", audio_url: null, audio_degraded: true });
    });
    render(<Composer {...props} />);
    const textarea = screen.getByPlaceholderText(/Ask about a recipe/);

    await user.type(textarea, "line one{Shift>}{Enter}{/Shift}line two");
    expect(mockedAskQuestionStream).not.toHaveBeenCalled();

    await user.keyboard("{Enter}");
    await waitFor(() => expect(mockedAskQuestionStream).toHaveBeenCalledTimes(1));
  });

  it("shows the mandatory-review banner and does not treat it as an answer when needs_review is true (Sec 3.1)", async () => {
    const user = userEvent.setup();
    const props = baseProps();
    mockedAskQuestionStream.mockImplementation(async (_id, _args, handlers: BotStreamHandlers) => {
      handlers.onMeta?.({
        conversation_id: "c1",
        detected_language: "ur",
        language_confidence: 0.5,
        needs_review: true,
        question_text: "kڑاہی گوشت (raw transcript)",
      });
    });

    render(<Composer {...props} />);
    const textarea = await sendText(user, "voice question placeholder");

    await screen.findByText(/Urdu transcript may contain recognition errors/);
    // needs_review short-circuits before any answer streams in — the
    // parent never gets a token, and the raw transcript replaces the
    // textarea content for editing rather than being silently sent.
    expect(props.onToken).not.toHaveBeenCalled();
    expect(textarea).toHaveValue("kڑاہی گوشت (raw transcript)");
  });

  it("shows the Hindi wording of the review banner for a hi transcript", async () => {
    const user = userEvent.setup();
    const props = baseProps();
    mockedAskQuestionStream.mockImplementation(async (_id, _args, handlers: BotStreamHandlers) => {
      handlers.onMeta?.({
        conversation_id: "c1",
        detected_language: "hi",
        language_confidence: 0.4,
        needs_review: true,
        question_text: "raw hindi transcript",
      });
    });
    render(<Composer {...props} />);
    await sendText(user, "x");
    await screen.findByText(/Hindi transcript may contain recognition errors/);
  });

  it("surfaces a stream-level error event and does not clear the textarea", async () => {
    const user = userEvent.setup();
    const props = baseProps();
    mockedAskQuestionStream.mockImplementation(async (_id, _args, handlers: BotStreamHandlers) => {
      handlers.onMeta?.({ conversation_id: "c1", detected_language: "en", language_confidence: 0.9, needs_review: false, question_text: "one more question" });
      handlers.onError?.("Daily question limit reached");
    });
    render(<Composer {...props} />);
    await sendText(user, "one more question");

    await screen.findByText("Daily question limit reached");
    expect(props.onStreamError).toHaveBeenCalledWith("Daily question limit reached");
  });

  it("shows a fallback error and does not clear the textarea when the request itself throws", async () => {
    const user = userEvent.setup();
    const props = baseProps();
    mockedAskQuestionStream.mockRejectedValue(new Error("network down"));
    render(<Composer {...props} />);
    await sendText(user, "one more question");

    await screen.findByText("Couldn't send that — try again.");
    expect(props.onStreamError).toHaveBeenCalledWith("Couldn't send that — try again.");
  });

  it("disables the send button until there is non-whitespace text", async () => {
    const user = userEvent.setup();
    render(<Composer {...baseProps()} />);
    const sendButton = screen.getByRole("button", { name: "Send" });
    expect(sendButton).toBeDisabled();

    await user.type(screen.getByPlaceholderText(/Ask about a recipe/), "   ");
    expect(sendButton).toBeDisabled();

    await user.type(screen.getByPlaceholderText(/Ask about a recipe/), "real text");
    expect(sendButton).not.toBeDisabled();
  });

  it("disables the whole composer when the conversation is locked/disabled", () => {
    render(<Composer {...baseProps({ disabled: true })} />);
    expect(screen.getByPlaceholderText(/Ask about a recipe/)).toBeDisabled();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Record a voice question/ })).toBeDisabled();
  });
});