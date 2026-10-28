type SentenceItem = {
  id: number;
  text: string;
  liked: boolean;
};

// Render guard: on the Liked tab, unliked items self-hide — the API type allows
// liked: false, but this component never renders such an item in that view.
export function LikedListItem({ item, tabIsLiked }: { item: SentenceItem; tabIsLiked: boolean }) {
  if (tabIsLiked && !item.liked) return null;
  return <li data-testid="sentence-item">{item.text}</li>;
}
