export const seenPlanets = new Set<string>();
export function mark(name: string) { seenPlanets.add(name); }
