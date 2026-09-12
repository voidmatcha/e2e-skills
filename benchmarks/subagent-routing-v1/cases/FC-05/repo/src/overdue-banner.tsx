type PatronSummary = { name: string; overdueBalanceCents: number };

export function OverdueBanner({ patron }: { patron: PatronSummary }) {
  if (patron.overdueBalanceCents <= 0) {
    return null;
  }
  return <aside data-testid="overdue-banner">Payment is required before another checkout.</aside>;
}
