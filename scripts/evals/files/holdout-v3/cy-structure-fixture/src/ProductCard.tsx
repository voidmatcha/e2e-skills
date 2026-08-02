type Product = {
  id: string;
  kind: 'summary' | 'detail';
  name: string;
};

export function ProductCard({ product }: { product: Product }) {
  if (product.kind !== 'detail') {
    return null;
  }
  return <button data-cy="detail-toolbar">{product.name}</button>;
}
