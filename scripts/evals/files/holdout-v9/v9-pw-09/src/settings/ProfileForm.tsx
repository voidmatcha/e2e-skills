import { useState } from 'react';

export function ProfileForm({ initialName }: { initialName: string }) {
  const [name, setName] = useState(initialName);
  const [draft, setDraft] = useState(initialName);
  const [compact, setCompact] = useState(false);

  function save() {
    setName(draft);
    void fetch('/api/profile', { method: 'PUT', body: JSON.stringify({ displayName: draft }) });
  }

  return (
    <form onSubmit={(event) => { event.preventDefault(); save(); }}>
      <h1 data-testid="profile-heading">{name}</h1>
      <label>
        Display name
        <input value={draft} onChange={(event) => setDraft(event.target.value)} />
      </label>
      <button type="submit">Save profile</button>
      <button type="button" aria-pressed={compact} onClick={() => setCompact(!compact)}>
        Compact layout
      </button>
    </form>
  );
}
