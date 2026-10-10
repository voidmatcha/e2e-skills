type Props = { field: string; values: string[] };

export function TopValuesPopover({ field, values }: Props) {
  return (
    <div data-testid="top-values-popover" role="dialog">
      <h3>Top 5 values of {field}</h3>
      <ol>
        {values.slice(0, 5).map((value) => (
          <li key={value}>{value}</li>
        ))}
      </ol>
    </div>
  );
}
