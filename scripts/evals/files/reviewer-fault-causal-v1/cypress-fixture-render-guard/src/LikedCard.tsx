type Item = { title: string; liked: boolean };

export function LikedCard({ item }: { item: Item }) {
  if (!item.liked) return null;
  return <article data-testid="liked-card">{item.title}</article>;
}
