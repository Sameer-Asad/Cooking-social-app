import { useEffect, useRef, useState } from "react";
import { ApiError, feedApi, mediaUrl, type Comment, type Liker, type Post } from "../api/client";
import { useIsMobile } from "../hooks/useIsMobile";

interface Props {
  post: Post;
}

// How long to wait after the last click before actually syncing with the
// server. The heart/count flip on EVERY click with zero delay, no
// matter what — this only controls how many network requests get sent.
// Waiting a beat after the last click means a quick like/unlike/like
// sends one request (the final decision), not one per click racing
// each other and settling out of order.
const LIKE_SYNC_DEBOUNCE_MS = 350;

function HeartIcon({ filled }: { filled: boolean }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill={filled ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.6l-1-1a5.5 5.5 0 1 0-7.8 7.8l1 1L12 21l7.8-7.8 1-1a5.5 5.5 0 0 0 0-7.8z" />
    </svg>
  );
}

function CommentIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
    </svg>
  );
}

export function PostCard({ post }: Props) {
  const [likeCount, setLikeCount] = useState(post.like_count);
  // Starts from what the server told us (post.liked_by_me), not a
  // hardcoded false — otherwise the heart would look empty on every
  // reload even for posts the user already liked.
  const [liked, setLiked] = useState(post.liked_by_me);
  const [commentCount, setCommentCount] = useState(post.comment_count);
  const [comments, setComments] = useState<Comment[] | null>(null);
  const [commentsOpen, setCommentsOpen] = useState(false);
  const [newComment, setNewComment] = useState("");
  const [likers, setLikers] = useState<Liker[] | null>(null);
  const [likersOpen, setLikersOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isMobile = useIsMobile();

  const desiredLikedRef = useRef(post.liked_by_me);
  // Bumped only on a genuine user click — lets syncLikeState tell "the
  // user toggled again mid-flight" apart from "my own rollback moved
  // desiredLikedRef", which otherwise look identical and cause an
  // infinite resync loop on every failed request.
  const generationRef = useRef(0);
  const debounceTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const syncInFlightRef = useRef(false);

  useEffect(() => {
    return () => {
      if (debounceTimeoutRef.current) clearTimeout(debounceTimeoutRef.current);
    };
  }, []);

  async function syncLikeState() {
    const desired = desiredLikedRef.current;
    const startGeneration = generationRef.current;
    syncInFlightRef.current = true;
    try {
      const result = desired ? await feedApi.like(post.id) : await feedApi.unlike(post.id);
      setLikeCount(result.like_count);
      setLikers(null);
    } catch (e) {
      setLiked(!desired);
      setLikeCount((c) => c + (desired ? -1 : 1));
      desiredLikedRef.current = !desired; // rollback — does NOT bump generation
      setError(
        e instanceof ApiError
          ? e.message
          : desired
          ? "Couldn't like this post."
          : "Couldn't unlike this post."
      );
    } finally {
      syncInFlightRef.current = false;
      // Only resync if the user genuinely toggled again mid-flight —
      // not if this generation's own rollback moved desiredLikedRef.
      if (generationRef.current !== startGeneration) {
        syncLikeState();
      }
    }
  }

  function handleToggleLike() {
    const next = !liked;
    setLiked(next);
    setLikeCount((c) => c + (next ? 1 : -1));
    setError(null);
    generationRef.current += 1;
    desiredLikedRef.current = next;

    if (debounceTimeoutRef.current) clearTimeout(debounceTimeoutRef.current);
    debounceTimeoutRef.current = setTimeout(() => {
      if (!syncInFlightRef.current) syncLikeState();
    }, LIKE_SYNC_DEBOUNCE_MS);
  }

  async function toggleLikers() {
    const opening = !likersOpen;
    setLikersOpen(opening);
    if (opening && likers === null) {
      try {
        const list = await feedApi.listLikers(post.id);
        setLikers(list);
      } catch {
        setLikers([]);
      }
    }
  }

  async function toggleComments() {
    const opening = !commentsOpen;
    setCommentsOpen(opening);
    if (opening && comments === null) {
      try {
        const list = await feedApi.listComments(post.id);
        setComments(list);
      } catch {
        setComments([]);
      }
    }
  }

  async function handleAddComment() {
    if (!newComment.trim()) return;
    try {
      const comment = await feedApi.comment(post.id, newComment);
      setComments((prev) => (prev ? [...prev, comment] : [comment]));
      setCommentCount((c) => c + 1);
      setNewComment("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't post that comment.");
    }
  }

  const mediaStyle: React.CSSProperties = {
    display: "block",
    width: isMobile ? "100%" : "60%",
    margin: "0 auto",
  };

  return (
    <div className="post-card">
      {post.media_type === "video" ? (
        <video className="post-media" src={mediaUrl(post.media_path)} controls style={mediaStyle} />
      ) : (
        <img className="post-media" src={mediaUrl(post.media_path)} alt={post.description} style={mediaStyle} />
      )}
      <div className="post-body">
        <p className="post-description">{post.description}</p>
        {error && <div className="error-text">{error}</div>}
        <div className="post-actions">
          <button
            className={`action-button${liked ? " liked" : ""}`}
            onClick={handleToggleLike}
            aria-label={`${liked ? "Unlike" : "Like"} — ${likeCount} likes`}
            aria-pressed={liked}
            style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
          >
            <HeartIcon filled={liked} /> {likeCount}
          </button>
          <button className="action-button" onClick={toggleLikers}>
            who liked
          </button>
          <button
            className="action-button"
            onClick={toggleComments}
            aria-label={`Comments — ${commentCount}`}
            style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
          >
            <CommentIcon /> {commentCount}
          </button>
        </div>

        {likersOpen && (
          <div className="comment-list">
            {likers === null && <div>Loading…</div>}
            {likers?.length === 0 && <div style={{ color: "var(--ink-faint)" }}>No likes yet.</div>}
            {likers?.map((l) => (
              <div key={l.user_id} className="comment-row">
                {l.display_name}
              </div>
            ))}
          </div>
        )}

        {commentsOpen && (
          <>
            <div className="comment-list">
              {comments === null && <div>Loading comments…</div>}
              {comments?.length === 0 && <div style={{ color: "var(--ink-faint)" }}>No comments yet.</div>}
              {comments?.map((c) => (
                <div key={c.id} className="comment-row">
                  {c.body}
                </div>
              ))}
            </div>
            <div className="comment-form">
              <input
                value={newComment}
                onChange={(e) => setNewComment(e.target.value)}
                placeholder="Add a comment…"
                onKeyDown={(e) => e.key === "Enter" && handleAddComment()}
              />
              <button className="primary-button" onClick={handleAddComment}>
                Post
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}