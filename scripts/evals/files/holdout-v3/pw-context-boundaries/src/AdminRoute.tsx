export function AdminRoute({ authenticated }: { authenticated: boolean }) {
  if (!authenticated) {
    return <nav aria-label="Sign in">Sign in</nav>;
  }

  return (
    <main>
      <nav aria-label="Admin">Admin</nav>
      <section data-billing-ready>Billing</section>
    </main>
  );
}
