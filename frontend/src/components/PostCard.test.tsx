import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PostCard } from "./PostCard";
import { ApiError, feedApi, type Post } from "../api/client";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    feedApi: { like: vi.fn(), unlike: vi.fn(), listComments: vi.fn(), comment: vi.fn(), list: vi.fn(), upload: vi.fn() },
  };
});

const mockedLike = vi.mocked(feedApi.like);
const mockedUnlike = vi.mocked(feedApi.unlike);
const mockedListComments = vi.mocked(feedApi.listComments);
const mockedComment = vi.mocked(feedApi.comment);

function makePost(overrides: Partial<Post> = {}): Post {
  return {
    id: "post-1",
    author_id: "user-1",
    media_type: "image",
    media_path: "images/biryani.jpg",
    description: "Homemade biryani",
    like_count: 3,
    comment_count: 1,
    created_at: "2026-01-01T00:00:00Z",
    liked_by_me: false,
    ...overrides,
  };
}

describe("PostCard", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    mockedLike.mockReset();
    mockedUnlike.mockReset();
    mockedListComments.mockReset();
    mockedComment.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders the heart already filled when the post was already liked (liked_by_me)", () => {
    render(<PostCard post={makePost({ liked_by_me: true, like_count: 6 })} />);
    const likeButton = screen.getByRole("button", { name: /^Unlike/ });
    expect(likeButton).toHaveClass("liked");
    expect(likeButton).toHaveAttribute("aria-pressed", "true");
  });

  it("renders the heart empty when the post was not already liked", () => {
    render(<PostCard post={makePost({ liked_by_me: false, like_count: 6 })} />);
    const likeButton = screen.getByRole("button", { name: /^Like/ });
    expect(likeButton).not.toHaveClass("liked");
    expect(likeButton).toHaveAttribute("aria-pressed", "false");
  });

  it("flips the heart and count instantly, before the debounce window (and any network call) fires", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedLike.mockResolvedValue({ post_id: "post-1", like_count: 7 });
    render(<PostCard post={makePost({ like_count: 6, liked_by_me: false })} />);

    const likeButton = screen.getByRole("button", { name: /^Like/ });
    await user.click(likeButton);

    // Instant — no request yet, debounce window hasn't elapsed.
    expect(likeButton).toHaveClass("liked");
    expect(likeButton).toHaveTextContent("7");
    expect(mockedLike).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(350);
    expect(mockedLike).toHaveBeenCalledTimes(1);
    expect(mockedLike).toHaveBeenCalledWith("post-1");
  });

  it("coalesces rapid like/unlike/like clicks into a single request reflecting the final choice", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedLike.mockResolvedValue({ post_id: "post-1", like_count: 7 });
    render(<PostCard post={makePost({ like_count: 6, liked_by_me: false })} />);

    const likeButton = () => screen.getByRole("button", { name: /^(Like|Unlike)/ });
    await user.click(likeButton()); // like
    await user.click(likeButton()); // unlike
    await user.click(likeButton()); // like  <- final state

    // Each click updated the UI instantly along the way.
    expect(likeButton()).toHaveClass("liked");
    expect(likeButton()).toHaveTextContent("7");
    expect(mockedLike).not.toHaveBeenCalled();
    expect(mockedUnlike).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(350);
    // Only ONE request went out, and it matches the final decision (like).
    expect(mockedLike).toHaveBeenCalledTimes(1);
    expect(mockedUnlike).not.toHaveBeenCalled();
  });

  it("resets the debounce timer on each click, so it only fires 350ms after the LAST click", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedLike.mockResolvedValue({ post_id: "post-1", like_count: 7 });
    render(<PostCard post={makePost({ like_count: 6, liked_by_me: false })} />);

    const likeButton = screen.getByRole("button", { name: /^Like/ });
    await user.click(likeButton);
    await vi.advanceTimersByTimeAsync(300); // less than the debounce window
    expect(mockedLike).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(300); // now 600ms since the click, but only 300ms since... no further click happened
    expect(mockedLike).toHaveBeenCalledTimes(1);
  });

  it("rolls back the optimistic increment and shows an error on a failed like", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedLike.mockRejectedValue(new ApiError(500, "Server error"));
    render(<PostCard post={makePost({ like_count: 6, liked_by_me: false })} />);

    const likeButton = screen.getByRole("button", { name: /^Like/ });
    await user.click(likeButton);
    await vi.advanceTimersByTimeAsync(350);

    await waitFor(() => expect(screen.getByText("Server error")).toBeInTheDocument());
    expect(likeButton).toHaveTextContent("6");
    expect(likeButton).not.toHaveClass("liked");
  });

  it("unlikes an already-liked post: heart empties, count decrements, DELETE is called after the debounce", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedUnlike.mockResolvedValue({ post_id: "post-1", like_count: 5 });
    render(<PostCard post={makePost({ like_count: 6, liked_by_me: true })} />);

    const likeButton = screen.getByRole("button", { name: /^Unlike/ });
    await user.click(likeButton);

    expect(likeButton).not.toHaveClass("liked");
    expect(likeButton).toHaveTextContent("5");
    expect(mockedUnlike).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(350);
    expect(mockedUnlike).toHaveBeenCalledWith("post-1");
    expect(mockedLike).not.toHaveBeenCalled();
  });

  it("rolls back the optimistic decrement and shows an error on a failed unlike", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedUnlike.mockRejectedValue(new ApiError(500, "Server error"));
    render(<PostCard post={makePost({ like_count: 6, liked_by_me: true })} />);

    const likeButton = screen.getByRole("button", { name: /^Unlike/ });
    await user.click(likeButton);
    await vi.advanceTimersByTimeAsync(350);

    await waitFor(() => expect(screen.getByText("Server error")).toBeInTheDocument());
    expect(likeButton).toHaveTextContent("6");
    expect(likeButton).toHaveClass("liked");
  });

  it("lazily loads comments only when the comment button is first clicked", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
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
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedListComments.mockResolvedValue([]);
    render(<PostCard post={makePost()} />);
    await user.click(screen.getByRole("button", { name: /comments/i }));
    expect(await screen.findByText("No comments yet.")).toBeInTheDocument();
  });

  it("adds a new comment, appends it locally, and increments the visible count", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
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
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedListComments.mockResolvedValue([]);
    render(<PostCard post={makePost()} />);
    await user.click(screen.getByRole("button", { name: /comments/i }));
    await screen.findByText("No comments yet.");

    await user.type(screen.getByPlaceholderText("Add a comment…"), "   ");
    await user.click(screen.getByRole("button", { name: "Post" }));
    expect(mockedComment).not.toHaveBeenCalled();
  });
});