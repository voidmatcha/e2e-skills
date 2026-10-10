const ICON_SIZE = 16;

export function StatusIcon({ state }: { state: 'ok' | 'warning' | 'error' }) {
  return (
    <svg data-testid="status-icon" width={ICON_SIZE} height={ICON_SIZE} viewBox="0 0 16 16" aria-label={state}>
      <use href={`#icon-${state}`} />
    </svg>
  );
}
