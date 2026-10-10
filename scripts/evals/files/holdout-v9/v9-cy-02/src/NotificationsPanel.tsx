import { useState } from 'react';

type Note = { id: string; text: string };

export function NotificationsPanel({ notes, loading }: { notes: Note[]; loading: boolean }) {
  const [tipOpen, setTipOpen] = useState(true);
  if (loading) {
    return <div data-cy="notifications-loading" role="progressbar" />;
  }
  return (
    <section>
      {tipOpen && (
        <p data-cy="shortcuts-tip">
          Press ? for shortcuts
          <button data-cy="shortcuts-tip-close" onClick={() => setTipOpen(false)}>Close</button>
        </p>
      )}
      {notes.map((note) => <p key={note.id}>{note.text}</p>)}
    </section>
  );
}
