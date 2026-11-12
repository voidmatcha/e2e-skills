import type { Event } from './seed';

export function renderSummary(events: Event[]): string {
  const taken = events.reduce((sum, e) => sum + e.attendees.length, 0);
  const seats = events.reduce((sum, e) => sum + e.capacity, 0);
  const full = events.filter((e) => e.attendees.length >= e.capacity).length;
  return `${events.length} events · ${taken} of ${seats} seats taken · ${full} full`;
}
