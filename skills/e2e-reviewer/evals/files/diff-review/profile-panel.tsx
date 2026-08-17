export function ProfilePanel({ name }: { name: string }) {
  return (
    <section aria-label="Profile">
      <h2>{name}</h2>
      <button type="button">Edit profile</button>
    </section>
  );
}
