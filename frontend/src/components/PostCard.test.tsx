import { render, screen } from "@testing-library/react";
import { fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PostCard } from "./PostCard";
import { ApiError, feedApi, type Post } from "../api/client";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    feedApi: {
      like: vi.fn(),
      unlike: vi.fn(),
      listComments: vi.fn(),
      comment: vi.fn(),
      listLikers: vi.fn(),
      list: vi.fn(),
      upload: vi.fn(),
    },
  };
});

const mockedLike = vi.mocked(feedApi.like);
const mockedUnlike = vi.mocked(feedApi.unlike);
const mockedListComments = vi.mocked(feedApi.listComments);
const mockedComment = vi.mocked(feedApi.comment);

const DEBOUNCE_MS = 350;

function makePost(overrides: Partial<Post> = {}): Post {
  return {
    id: "post-1",
    author_id: "user-1",
    media_type: "image",
    media_path: "images/biryani.jpg",
    description: "Homemade biryani",
    like_count: 3,
    comment_count: 1,
    liked_by_me: false,
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("PostCard", () => {
  beforeEach(() => {
    mockedLike.mockReset();
    mockedUnlike.mockReset();
    mockedListComments.mockReset();
    mockedComment.mockReset();
    vi.useRealTimers();
  });

  // Runs AFTER setup.ts's global afterEach(cleanup()) has already unmounted
  // the component — so any pending debounce timeout gets cancelled by
  // PostCard's own cleanup effect while the SAME timer system that
  // scheduled it (fake, in most tests here) is still active. Switching
  // back to real timers mid-test (before unmount) was cancelling a fake
  // timer ID with the real clearTimeout, which is a silent no-op — the
  // orphaned fake timeout, and everything it closed over, never got
  // freed. vi.clearAllTimers() is a belt-and-suspenders sweep for
  // anything still pending regardless.
  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
  });

  it("renders the heart already filled when the post was already liked (liked_by_me)", () => {
    render(<PostCard post={makePost({ liked_by_me: true, like_count: 5 })} />);
    const likeButton = screen.getByRole("button", { name: /unlike/i });
    expect(likeButton).toHaveAttribute("aria-pressed", "true");
    expect(likeButton).toHaveTextContent("5");
  });

  it("renders the heart empty when the post was not already liked", () => {
    render(<PostCard post={makePost({ liked_by_me: false, like_count: 5 })} />);
    const likeButton = screen.getByRole("button", { name: /^like/i });
    expect(likeButton).toHaveAttribute("aria-pressed", "false");
  });

  it("flips the heart and count instantly, before the debounce window (and any network call) fires", () => {
    vi.useFakeTimers();
    render(<PostCard post={makePost({ liked_by_me: false, like_count: 3 })} />);

    const likeButton = screen.getByRole("button", { name: /^like/i });
    fireEvent.click(likeButton);

    // Instant, optimistic UI flip — no network call yet. Deliberately NOT
    // advancing the fake timer here; the pending debounce timeout is left
    // for the afterEach + unmount to clean up correctly.
    expect(likeButton).toHaveAttribute("aria-pressed", "true");
    expect(likeButton).toHaveTextContent("4");
    expect(mockedLike).not.toHaveBeenCalled();
    expect(mockedUnlike).not.toHaveBeenCalled();
  });

  it("coalesces rapid like/unlike/like clicks into a single request reflecting the final choice", async () => {
    vi.useFakeTimers();
    mockedLike.mockResolvedValue({ post_id: "post-1", like_count: 4 });
    render(<PostCard post={makePost({ liked_by_me: false, like_count: 3 })} />);

    const likeButton = screen.getByRole("button", { name: /^like/i });
    fireEvent.click(likeButton); // like
    fireEvent.click(likeButton); // unlike
    fireEvent.click(likeButton); // like again — final desired state is "liked"

    await vi.advanceTimersByTimeAsync(DEBOUNCE_MS + 10);

    expect(mockedLike).toHaveBeenCalledTimes(1);
    expect(mockedUnlike).not.toHaveBeenCalled();
  });

  it("resets the debounce timer on each click, so it only fires 350ms after the LAST click", async () => {
    vi.useFakeTimers();
    mockedLike.mockResolvedValue({ post_id: "post-1", like_count: 4 });
    render(<PostCard post={makePost({ liked_by_me: false, like_count: 3 })} />);

    const likeButton = screen.getByRole("button", { name: /^like/i });
    fireEvent.click(likeButton);

    // Advance most, but not all, of the debounce window, then click again.
    await vi.advanceTimersByTimeAsync(DEBOUNCE_MS - 50);
    expect(mockedLike).not.toHaveBeenCalled();

    fireEvent.click(likeButton); // unlike — resets the timer
    fireEvent.click(likeButton); // like again — resets again

    await vi.advanceTimersByTimeAsync(DEBOUNCE_MS - 50);
    expect(mockedLike).not.toHaveBeenCalled(); // still hasn't fired

    await vi.advanceTimersByTimeAsync(100);
    expect(mockedLike).toHaveBeenCalledTimes(1); // fires only after a full quiet window
  });

  it("rolls back the optimistic increment and shows an error on a failed like", async () => {
    vi.useFakeTimers();
    mockedLike.mockRejectedValue(new ApiError(500, "Server error"));
    render(<PostCard post={makePost({ liked_by_me: false, like_count: 6 })} />);

    const likeButton = screen.getByRole("button", { name: /^like/i });
    fireEvent.click(likeButton);
    await vi.advanceTimersByTimeAsync(DEBOUNCE_MS + 10);

    // Required here, not just decorative: findByText polls internally,
    // and needs the real setTimeout to actually advance on its own.
    // Timer already fired above, so nothing pending is left behind.
    vi.useRealTimers();
    await screen.findByText("Server error");
    expect(likeButton).toHaveTextContent("6");
    expect(likeButton).toHaveAttribute("aria-pressed", "false");
  });

  it("unlikes an already-liked post: heart empties, count decrements, DELETE is called after the debounce", async () => {
    vi.useFakeTimers();
    mockedUnlike.mockResolvedValue({ post_id: "post-1", like_count: 5 });
    render(<PostCard post={makePost({ liked_by_me: true, like_count: 6 })} />);

    const likeButton = screen.getByRole("button", { name: /unlike/i });
    fireEvent.click(likeButton);

    expect(likeButton).toHaveAttribute("aria-pressed", "false");
    expect(likeButton).toHaveTextContent("5");
    expect(mockedUnlike).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(DEBOUNCE_MS + 10);
    expect(mockedUnlike).toHaveBeenCalledTimes(1);
    expect(mockedUnlike).toHaveBeenCalledWith("post-1");
  });

  it("rolls back the optimistic decrement and shows an error on a failed unlike", async () => {
    vi.useFakeTimers();
    mockedUnlike.mockRejectedValue(new ApiError(500, "Server error"));
    render(<PostCard post={makePost({ liked_by_me: true, like_count: 6 })} />);

    const likeButton = screen.getByRole("button", { name: /unlike/i });
    fireEvent.click(likeButton);
    await vi.advanceTimersByTimeAsync(DEBOUNCE_MS + 10);

    // Same reasoning as the failed-like test above: required for
    // findByText's polling, safe because the timer already fired.
    vi.useRealTimers();
    await screen.findByText("Server error");
    expect(likeButton).toHaveTextContent("6");
    expect(likeButton).toHaveAttribute("aria-pressed", "true");
  });

  it("lazily loads comments only when the comment button is first clicked", async () => {
    const user = userEvent.setup();
    mockedListComments.mockResolvedValue([
      { id: "c1", post_id: "post-1", user_id: "u1", body: "Looks great!", created_at: "2026-01-01T00:00:00Z" },
    ]);
    render(<PostCard post={makePost()} />);

    expect(mockedListComments).not.toHaveBeenCalled();
    const commentButton = screen.getByRole("button", { name: /comments/i });
    await user.click(commentButton);
    expect(await screen.findByText("Looks great!")).toBeInTheDocument();
    expect(mockedListComments).toHaveBeenCalledTimes(1);

    await user.click(commentButton);
    await user.click(commentButton);
    expect(mockedListComments).toHaveBeenCalledTimes(1);
  });

  it("shows an empty state when a post has no comments", async () => {
    const user = userEvent.setup();
    mockedListComments.mockResolvedValue([]);
    render(<PostCard post={makePost()} />);
    await user.click(screen.getByRole("button", { name: /comments/i }));
    expect(await screen.findByText("No comments yet.")).toBeInTheDocument();
  });

  it("adds a new comment, appends it locally, and increments the visible count", async () => {
    const user = userEvent.setup();
    mockedListComments.mockResolvedValue([]);
    mockedComment.mockResolvedValue({
      id: "c2", post_id: "post-1", user_id: "u1", body: "So good!", created_at: "2026-01-01T00:00:00Z",
    });
    render(<PostCard post={makePost({ comment_count: 1 })} />);

    const commentButton = screen.getByRole("button", { name: /comments/i });
    await user.click(commentButton);
    await screen.findByText("No comments yet.");

    await user.type(screen.getByPlaceholderText("Add a comment…"), "So good!");
    await user.click(screen.getByRole("button", { name: "Post" }));

    expect(await screen.findByText("So good!")).toBeInTheDocument();
    expect(commentButton).toHaveTextContent("2");
    expect(mockedComment).toHaveBeenCalledWith("post-1", "So good!");
  });

  it("does not submit an empty or whitespace-only comment", async () => {
    const user = userEvent.setup();
    mockedListComments.mockResolvedValue([]);
    render(<PostCard post={makePost()} />);
    await user.click(screen.getByRole("button", { name: /comments/i }));
    await screen.findByText("No comments yet.");

    await user.type(screen.getByPlaceholderText("Add a comment…"), "   ");
    await user.click(screen.getByRole("button", { name: "Post" }));
    expect(mockedComment).not.toHaveBeenCalled();
  });
});