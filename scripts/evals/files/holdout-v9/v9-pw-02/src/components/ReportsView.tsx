import { useState } from 'react';

type Report = { id: string; title: string };

export function ReportsView({ reports, loading }: { reports: Report[]; loading: boolean }) {
  const [offerOpen, setOfferOpen] = useState(true);
  if (loading) {
    return <div data-testid="reports-skeleton" aria-busy="true" />;
  }
  return (
    <main>
      {offerOpen && (
        <aside data-testid="upgrade-offer" className="offer-strip">
          <button type="button" onClick={() => setOfferOpen(false)}>Dismiss upgrade offer</button>
        </aside>
      )}
      {reports.map((report) => (
        <article key={report.id} data-testid="report-row">{report.title}</article>
      ))}
    </main>
  );
}
