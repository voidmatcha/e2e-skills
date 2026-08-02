export async function createContact(name: string) {
  return fetch('/api/contacts', {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
}
