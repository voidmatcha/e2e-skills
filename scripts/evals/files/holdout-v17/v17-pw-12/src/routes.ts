export function render(path: string, signedIn: boolean) {
  if (path === '/private/atlas' && !signedIn) return '<h1>Welcome</h1><form>Sign in</form>';
  return '<h1>Welcome</h1><section>Private atlas</section>';
}
