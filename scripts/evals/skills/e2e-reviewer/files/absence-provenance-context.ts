// SPDX-License-Identifier: Apache-2.0
// Supplied UI contract: after GET /api/entries finishes, show "Catalog loaded"
// and display only enabled entries. Disabled entries must remain absent;
// this is an initial filtered state, not a removal transition.
// A dismissible hint is present on /catalog; its button removes that hint.
export function entryView(entry: { code: string; label: string; enabled: boolean }) {
  return { testId: `entry-${entry.code}`, text: entry.label };
}
export function catalogView(entries: Parameters<typeof entryView>[0][]) {
  return {
    status: 'Catalog loaded',
    rows: entries.filter(entry => entry.enabled).map(entryView),
    hint: { testId: 'catalog-hint', text: 'Browse the available guides' },
    dismissButton: { role: 'button', name: 'Dismiss hint', removes: 'catalog-hint' },
  };
}
// The DOM adapter renders each row/hint's testId as data-testid, and row.text
// as its text content; status is rendered with role="status" after loading.
// It renders no element with class "retired-hint"; that selector is obsolete.
