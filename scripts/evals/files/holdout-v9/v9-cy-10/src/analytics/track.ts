let queuedEvents = 0;

export function track(event: string): void {
  queuedEvents += 1;
  fetch('/api/analytics', { method: 'POST', body: JSON.stringify({ event, queuedEvents }) }).catch(() => {});
}
