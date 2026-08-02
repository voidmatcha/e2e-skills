export function pageTheme() {
  return getComputedStyle(document.body).getPropertyValue('--theme-name');
}
