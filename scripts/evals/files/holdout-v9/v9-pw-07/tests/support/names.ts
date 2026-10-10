var runPrefix = `run-${Date.now()}`;
const issuedNames = new Set<string>();

export function uniqueProjectName(base: string): string {
  let candidate = `${runPrefix}-${base}`;
  while (issuedNames.has(candidate)) {
    candidate = `${candidate}-x`;
  }
  issuedNames.add(candidate);
  return candidate;
}
