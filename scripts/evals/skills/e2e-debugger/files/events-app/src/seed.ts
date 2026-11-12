export type Event = { id: number; title: string; capacity: number; attendees: string[] };

export const seedEvents: Event[] = [
  { id: 1, title: 'Book Club', capacity: 3, attendees: ['Ann', 'Ben', 'Cy'] },
  { id: 2, title: 'Board Games Night', capacity: 10, attendees: ['Dee', 'Eli'] },
  { id: 3, title: 'Community Garden Cleanup', capacity: 25, attendees: [] },
];
