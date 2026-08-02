export function reorder(items: string[], from: number, to: number) {
  const next = [...items];
  const [moved] = next.splice(from, 1);
  next.splice(to, 0, moved);
  document.querySelector('[data-cy=board]')!.textContent = next.join(',');
  void fetch('/api/board/order', {
    method: 'POST',
    body: JSON.stringify(next),
  });
}

export function Board({ items }: { items: string[] }) {
  return (
    <section data-cy="board">
      <button data-cy="card-a" draggable>
        {items[0]}
      </button>
      <button data-cy="card-b" onDrop={() => reorder(items, 0, 1)}>
        {items[1]}
      </button>
    </section>
  );
}
