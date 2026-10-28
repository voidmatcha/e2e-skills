export async function saveProfile(form: HTMLFormElement, status: HTMLElement) {
  status.textContent = 'Saved';
  const body = new FormData(form);
  await fetch('/api/profile', { method: 'PATCH', body });
}

async function loadProfileFromServer() {
  const response = await fetch('/api/profile');
  if (!response.ok) throw new Error(`Profile load failed: ${response.status}`);
  const { displayName } = await response.json();
  const input = document.querySelector<HTMLInputElement>('input[name="displayName"]');
  if (!input) throw new Error('Display name field missing');
  input.value = displayName;
}

window.addEventListener('DOMContentLoaded', () => {
  void loadProfileFromServer();
});
