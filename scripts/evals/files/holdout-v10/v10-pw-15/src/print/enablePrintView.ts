export function enablePrintView(): void {
  const link = document.createElement('link');
  link.rel = 'preload';
  link.as = 'style';
  link.href = '/assets/rubric-print.css';
  document.head.append(link);
}
