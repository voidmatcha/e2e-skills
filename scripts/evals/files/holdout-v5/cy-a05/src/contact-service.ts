let contactSequence = 0;

export function nextContactName() {
  contactSequence += 1;
  return `contact-${contactSequence}-${Date.now()}`;
}

export async function createContact(name: string) {
  return fetch('/api/contacts', {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
}
