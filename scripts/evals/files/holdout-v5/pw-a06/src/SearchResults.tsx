type SearchResult = {
  title: string;
};

export function SearchResults({ results }: { results: SearchResult[] }) {
  return (
    <ul>
      {results.map((result) => (
        <li data-testid="result-row" key={result.title}>
          {result.title}
        </li>
      ))}
    </ul>
  );
}
