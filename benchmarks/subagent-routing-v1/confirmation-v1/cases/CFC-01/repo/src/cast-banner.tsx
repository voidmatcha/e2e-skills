// confirmation-case: CFC-01/src/cast-banner.tsx
export function CastBanner({ understudy }: { understudy: boolean }) {
  if (!understudy) return null;
  return <aside data-testid="understudy-banner">Understudy tonight</aside>;
}
