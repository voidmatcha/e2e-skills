export function PalettePicker() {
  return <button data-cy='palette' onClick={() => document.querySelector('[data-cy=palette]')?.replaceWith(document.createElement('div'))}>Change palette</button>;
}
