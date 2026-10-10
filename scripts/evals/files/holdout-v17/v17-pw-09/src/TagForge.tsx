import React from 'react';
export function TagForge() {
  const [queued, setQueued] = React.useState(false);
  return <><button onClick={() => { setQueued(true); void fetch('/shared-api/tags', { method: 'POST' }); }}>Forge tag</button>{queued && <span>Tag queued</span>}</>;
}
