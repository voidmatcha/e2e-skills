export function SeedDrawer({ packets }) {
  return <div>{packets.filter(p => p.viable).map(p => <span data-cy='packet' key={p.id}>{p.id}</span>)}</div>;
}
