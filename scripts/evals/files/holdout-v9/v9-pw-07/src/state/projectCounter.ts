let openProjectCount = 0;

export function trackProjectOpened(): number {
  openProjectCount += 1;
  return openProjectCount;
}
