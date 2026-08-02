export function accountMarkup(authenticated: boolean): string {
  if (!authenticated) {
    return "<main><h1>Account</h1><a href='/login'>Sign in</a></main>";
  }
  return "<main><h1>Account</h1><p data-testid='account-name'>Ada Lovelace</p></main>";
}
