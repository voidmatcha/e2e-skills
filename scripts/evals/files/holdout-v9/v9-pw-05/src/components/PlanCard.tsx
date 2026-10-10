export function PlanCard({ name, price }: { name: string; price: string }) {
  return (
    <article data-testid="plan-card" style={{ width: 320, height: 180 }}>
      <h2>{name}</h2>
      <p>{price}</p>
    </article>
  );
}
