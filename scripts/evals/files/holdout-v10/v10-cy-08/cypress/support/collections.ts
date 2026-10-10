export function only<T>(items: T[], keep: (item: T) => boolean): T[] {
  return items.filter(keep);
}
