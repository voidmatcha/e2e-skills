import { useState } from 'react';

export function LikeButton() {
  const [pressed, setPressed] = useState(false);

  const saveLike = () => {
    setPressed(true);
    void fetch('/api/likes', { method: 'POST' });
  };

  return (
    <button
      aria-pressed={pressed}
      data-cy="like-toggle"
      onClick={saveLike}
      type="button"
    >
      Like
    </button>
  );
}
