type LikedItem = {
  id: string;
  liked: boolean;
  title: string;
};

export function LikedCard({ item }: { item: LikedItem }) {
  if (!item.liked) {
    return null;
  }

  return <article data-cy="liked-card">{item.title}</article>;
}
