type Order = { status: string; carrier: string; window: string };

export function OrderPage({ order }: { order: Order }) {
  return (
    <section>
      <p data-testid="order-status">{order.status}</p>
      <p data-testid="order-carrier">{order.carrier}</p>
      <p data-testid="delivery-window">{order.window}</p>
    </section>
  );
}
