import { useState } from 'react';

export function Board({ cardId }: { cardId: string }) {
  const [lane, setLane] = useState('backlog');
  const card = <article data-cy={`card-${cardId}`}>{lane}</article>;

  function moveToDone() {
    setLane('done');
    void fetch(`/api/cards/${cardId}`, {
      method: 'PATCH',
      body: JSON.stringify({ lane: 'done' }),
    });
  }

  return (
    <section>
      <div data-cy="lane-backlog">{lane === 'backlog' ? card : null}</div>
      <div data-cy="lane-done" onDrop={moveToDone}>
        {lane === 'done' ? card : null}
        Done
      </div>
    </section>
  );
}
