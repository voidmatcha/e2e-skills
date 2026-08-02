export const teamRoutes = new Set(['/team/invoices', '/team/members']);

export function destinationFor(pathname: string, signedIn: boolean) {
  if (teamRoutes.has(pathname) && !signedIn) return '/sign-in';
  return pathname;
}
