export const profileBackend = {
  baseUrl: 'https://shared-staging.example',
  rollback: false,
  tenantIsolation: false,
} as const;

export async function saveProfile(name: string) {
  const response = await fetch(`${profileBackend.baseUrl}/api/profile`, {
    method: 'PATCH',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ name }),
  });
  return response.json();
}

export function ProfileEditor({ name }: { name: string }) {
  return (
    <button data-cy="save-profile" onClick={() => void saveProfile(name)}>
      Save
    </button>
  );
}
