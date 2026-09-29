export async function saveProfile(form: HTMLFormElement, status: HTMLElement) {
  status.textContent = 'Saved';
  const body = new FormData(form);
  await fetch('/api/profile', { method: 'PATCH', body });
}
