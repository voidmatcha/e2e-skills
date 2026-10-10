export function RsvpForm({ slug }: { slug: string }) {
  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const email = new FormData(event.currentTarget).get('email');
    await fetch(`/api/events/${slug}/rsvps`, { method: 'POST', body: JSON.stringify({ email }) });
  }
  return (
    <form onSubmit={onSubmit}>
      <input name="email" data-cy="guest-email" />
      <button data-cy="rsvp-submit">RSVP</button>
    </form>
  );
}
