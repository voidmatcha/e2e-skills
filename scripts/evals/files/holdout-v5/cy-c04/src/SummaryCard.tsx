type Summary = {
  status: string;
  total: number;
};

export function SummaryCard({ summary }: { summary: Summary }) {
  if (summary.status !== 'published') return null;
  return <article data-cy="summary-card">{summary.total}</article>;
}
