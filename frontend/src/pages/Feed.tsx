import { useEffect, useState } from "react";
import { ApiError, feedApi, type Post } from "../api/client";
import { PostCard } from "../components/PostCard";
import { UploadModal } from "../components/UploadModal";

export function Feed() {
  const [posts, setPosts] = useState<Post[]>([]);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function loadPosts() {
    setLoading(true);
    try {
      const list = await feedApi.list();
      setPosts(list);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't load the feed.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadPosts();
  }, []);

  return (
    <div className="view">
      <div className="feed-toolbar">
        <h2>The feed</h2>
        <button className="primary-button" onClick={() => setUploadOpen(true)}>
          Share a dish
        </button>
      </div>
      {error && <div className="error-text">{error}</div>}
      {loading && <div className="empty-state">Loading…</div>}
      {!loading && posts.length === 0 && !error && (
        <div className="empty-state">Nothing posted yet — be the first to share a dish.</div>
      )}
      <div className="post-list">
        {posts.map((p) => (
          <PostCard key={p.id} post={p} />
        ))}
      </div>
      {uploadOpen && (
        <UploadModal
          onClose={() => setUploadOpen(false)}
          onUploaded={(post) => setPosts((prev) => [post, ...prev])}
        />
      )}
    </div>
  );
}