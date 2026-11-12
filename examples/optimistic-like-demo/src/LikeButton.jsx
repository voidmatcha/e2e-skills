import { useEffect, useState } from "react";
import { getLike, postLike } from "./api.js";

const USER = "mina.trails";
const BASE_LIKES = 128;

// Original line icons for the action row (not copied from any product).
const HeartIcon = () => (
  <svg className="icon heart" viewBox="0 0 24 24" aria-hidden="true">
    <path d="M12 20.6 10.6 19.3C5.6 14.8 2.5 12 2.5 8.4 2.5 5.6 4.7 3.5 7.4 3.5c1.8 0 3.5 0.9 4.6 2.3 1.1-1.4 2.8-2.3 4.6-2.3 2.7 0 4.9 2.1 4.9 4.9 0 3.6-3.1 6.4-8.1 10.9L12 20.6Z" />
  </svg>
);
const CommentIcon = () => (
  <svg className="icon" viewBox="0 0 24 24" aria-hidden="true">
    <path d="M12 3.2c-5 0-9 3.5-9 7.9 0 2.2 1 4.2 2.7 5.6L4.6 21l4.3-1.6c1 0.3 2 0.4 3.1 0.4 5 0 9-3.5 9-7.9S17 3.2 12 3.2Z" />
  </svg>
);
const ShareIcon = () => (
  <svg className="icon" viewBox="0 0 24 24" aria-hidden="true">
    <path d="M21 3 3 10.2l7.4 2.6L13 21 21 3Z" />
    <path d="M10.4 12.8 21 3" />
  </svg>
);
const SaveIcon = () => (
  <svg className="icon" viewBox="0 0 24 24" aria-hidden="true">
    <path d="M5.5 3h13v18l-6.5-4.6L5.5 21V3Z" />
  </svg>
);

export function LikeButton() {
  const [liked, setLiked] = useState(false);
  const [ready, setReady] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getLike().then((value) => {
      setLiked(value);
      setReady(true);
    });
  }, []);

  async function likeArticle() {
    const previousLiked = liked;
    setLiked(true);
    setSaving(true);
    setError("");
    try {
      await postLike();
    } catch {
      setLiked(previousLiked);
      setError("Couldn't save. Try again.");
    } finally {
      setSaving(false);
    }
  }

  const likes = BASE_LIKES + (liked ? 1 : 0);
  return (
    <article className="post">
      <header className="post-head">
        <span className="avatar" aria-hidden="true">M</span>
        <span className="username">{USER}</span>
        <span className="more" aria-hidden="true">···</span>
      </header>

      <div className="photo" role="img" aria-label="Sunrise over a mountain ridge">
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
          <circle cx="68" cy="34" r="13" fill="#FFE08A" />
          <path d="M0 78 L22 48 L36 64 L52 40 L70 62 L84 52 L100 70 L100 100 L0 100 Z" fill="#3D3A6B" />
          <path d="M0 88 L18 70 L34 82 L50 66 L66 84 L82 72 L100 86 L100 100 L0 100 Z" fill="#26243F" />
        </svg>
      </div>

      <div className="actions">
        <button type="button" className="like" aria-label="Like article" aria-pressed={liked} disabled={!ready || saving} onClick={likeArticle}>
          <HeartIcon />
        </button>
        <span className="action" aria-hidden="true"><CommentIcon /></span>
        <span className="action" aria-hidden="true"><ShareIcon /></span>
        <span className="action save" aria-hidden="true"><SaveIcon /></span>
      </div>

      <p className="likes">{likes} likes</p>
      <p className="caption"><span className="username">{USER}</span> first light on the ridge.</p>
      <p className="time">2 hours ago</p>
      <p role="status">{saving ? "Saving..." : liked ? "Liked!" : "Not liked yet."}</p>
      {error && <p className="error" role="alert">{error}</p>}
    </article>
  );
}
