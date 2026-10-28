import Link from "next/link";

// Next.js App Router home page (route: "/").
// The links below define the navigable surface used for coverage-gap analysis.

const features = [
  "View your dashboard at a glance",
  "Manage your profile and account details",
  "Configure notifications and alerts",
];

export default function HomePage() {
  return (
    <main>
      <h1>Acme App</h1>
      <p>Welcome to the Acme demo application.</p>

      <ul>
        {features.map((feature) => (
          <li key={feature}>{feature}</li>
        ))}
      </ul>

      <nav>
        <Link href="/login">Log in</Link>
        <Link href="/signup">Sign up</Link>
        <Link href="/dashboard">Dashboard</Link>
        <Link href="/profile">Profile</Link>
        <Link href="/notifications">Notifications</Link>
      </nav>
    </main>
  );
}
