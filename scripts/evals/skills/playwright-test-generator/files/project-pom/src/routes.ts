// Application route table consumed by the router.
// Each entry maps a URL path to its handler/component.

export interface AppRoute {
  path: string;
  // Logical handler name (component or controller); fake values for fixtures.
  handler: string;
  // Whether the route requires an authenticated session.
  protected: boolean;
}

export const routes: AppRoute[] = [
  { path: "/login", handler: "LoginPage", protected: false },
  { path: "/dashboard", handler: "DashboardPage", protected: true },
  { path: "/dashboard/analytics", handler: "AnalyticsPage", protected: true },
  { path: "/settings", handler: "SettingsPage", protected: true },
  { path: "/settings/notifications", handler: "NotificationSettingsPage", protected: true },
  { path: "/settings/security", handler: "SecuritySettingsPage", protected: true },
  { path: "/profile", handler: "ProfilePage", protected: true },
  // Checkout: show renders the form, process handles the POST submission.
  { path: "/checkout", handler: "CheckoutPage.show", protected: true },
  { path: "/checkout", handler: "CheckoutPage.process", protected: true },
  { path: "/checkout/confirmation", handler: "CheckoutConfirmationPage", protected: true },
];

export default routes;
