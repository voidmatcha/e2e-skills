type Field = { name: string; type: string };

export function FieldList({ fields, sortBy = 'type' }: { fields: Field[]; sortBy?: 'type' | 'name' }) {
  const ordered = [...fields].sort((a, b) => a[sortBy].localeCompare(b[sortBy]));
  return (
    <ul>
      {ordered.map((field) => (
        <li key={field.name} data-testid="field-row">{field.name}: {field.type}</li>
      ))}
    </ul>
  );
}
