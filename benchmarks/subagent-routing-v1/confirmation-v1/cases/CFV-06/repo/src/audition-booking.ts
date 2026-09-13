// confirmation-case: CFV-06/src/audition-booking.ts
export async function reserveAuditionSlot(slotId: string) {
  return fetch(`/api/auditions/${slotId}/reservations`, { method: 'POST' });
}
