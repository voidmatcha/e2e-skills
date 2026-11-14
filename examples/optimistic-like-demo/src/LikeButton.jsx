import { useEffect, useState } from "react";
import { getLike, postLike } from "./api.js";

const USER = "mina.trails";
const PLACE = "Dolomites";
const CAPTION = "First light on the ridge.";
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
    <div className="feed">
      <article className="reel">
        {/* Original vertical illustration, so the demo ships no third-party media. */}
        <div className="reel-media" role="img" aria-label="Sunrise over a mountain ridge">
          <svg viewBox="0 0 90 160" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
            <defs>
              <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0" stopColor="#2E2A5C" />
                <stop offset="0.55" stopColor="#C8628A" />
                <stop offset="1" stopColor="#F6B27A" />
              </linearGradient>
            </defs>
            <rect width="90" height="160" fill="url(#sky)" />
            <circle cx="28" cy="58" r="11" fill="#FFE08A" />
            <path d="M0 104 L16 82 L28 94 L44 70 L60 92 L74 80 L90 96 L90 160 L0 160 Z" fill="#4A3F78" />
            <path d="M0 122 L14 106 L30 118 L46 100 L62 120 L78 108 L90 118 L90 160 L0 160 Z" fill="#2F2A55" />
            <path d="M0 140 L20 128 L38 138 L56 126 L74 140 L90 132 L90 160 L0 160 Z" fill="#1E1B3A" />
          </svg>
        </div>
        <div className="reel-shade" aria-hidden="true" />

        <div className="rail">
          <div className="rail-item">
            <button type="button" className="like" aria-label="Like article" aria-pressed={liked} disabled={!ready || saving} onClick={likeArticle}>
              <HeartIcon />
            </button>
            <p className="likes">{likes} likes</p>
          </div>
          <div className="rail-item" aria-hidden="true"><span className="action"><CommentIcon /></span><span className="rail-label">Comment</span></div>
          <div className="rail-item" aria-hidden="true"><span className="action"><ShareIcon /></span><span className="rail-label">Share</span></div>
          <div className="rail-item" aria-hidden="true"><span className="action"><SaveIcon /></span></div>
        </div>

        <div className="meta">
          <div className="author">
            <span className="avatar" aria-hidden="true">M</span>
            <span className="username">{USER}</span>
            <span className="place">· {PLACE}</span>
          </div>
          <p className="caption">{CAPTION}</p>
        </div>
      </article>

      <p role="status">{saving ? "Saving..." : liked ? "Liked!" : "Not liked yet."}</p>
      {error && <p className="error" role="alert">{error}</p>}
    </div>
  );
}
