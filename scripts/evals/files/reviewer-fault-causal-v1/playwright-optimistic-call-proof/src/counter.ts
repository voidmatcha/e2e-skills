export async function increment(
  setCount: (count: number) => void,
  currentCount: number,
): Promise<void> {
  setCount(currentCount + 1);
  await fetch("/api/increment", { method: "POST" });
}
