import React from 'react';
export function BloomTray({ bulbs }: { bulbs: { id: string; sprouted: boolean }[] }) {
  const [items, setItems] = React.useState(bulbs);
  return <><button onClick={() => setItems([])}>Remove bulbs</button><ul>
    {items.filter(b => b.sprouted).map(b => <li data-testid='sprout' key={b.id}>{b.id}</li>)}
  </ul></>;
}
