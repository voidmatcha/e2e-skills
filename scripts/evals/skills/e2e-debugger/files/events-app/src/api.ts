import { seedEvents, type Event } from './seed';

const events: Event[] = structuredClone(seedEvents);

// Simulated server delay: every save takes 300-600 ms.
function wait(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 300 + Math.random() * 300));
}

export async function removeAttendee(eventId: number, name: string): Promise<Event[]> {
  await wait();
  const event = events.find((e) => e.id === eventId);
  if (event) event.attendees = event.attendees.filter((a) => a !== name);
  return events;
}
