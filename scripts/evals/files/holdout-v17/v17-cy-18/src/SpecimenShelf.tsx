export function SpecimenShelf({ specimens }: { specimens: { id: string; catalogued: boolean }[] }) {
  return <section>{specimens.filter(item => item.catalogued).map(item => <article data-cy='specimen' key={item.id}>{item.id}</article>)}</section>;
}
