import React from 'react';
export function StarPin() {
  const [pinned, setPinned] = React.useState(false);
  return <button aria-pressed={pinned} onClick={() => {
    setPinned(true);
    void fetch('/api/pins', { method: 'POST' });
  }}>Pin star</button>;
}
