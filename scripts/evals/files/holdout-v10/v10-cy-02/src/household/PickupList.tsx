type Pickup = { id: string; stream: 'glass' | 'paper' | 'organics'; date: string; skipped: boolean };

export function PickupList({ pickups }: { pickups: Pickup[] }) {
  const today = new Date().toISOString().slice(0, 10);
  const upcoming = pickups.filter((pickup) => pickup.date >= today && !pickup.skipped);
  if (upcoming.length === 0) {
    return <p data-cy="no-pickups">No pickups scheduled</p>;
  }
  return (
    <ul>
      {upcoming.map((pickup) => (
        <li key={pickup.id} data-cy="pickup-row">{pickup.stream} - {pickup.date}</li>
      ))}
    </ul>
  );
}
