let currentPage: unknown;

export function setCurrentPage(value: unknown) {
  currentPage = value;
}

export function getCurrentPage() {
  return currentPage;
}
