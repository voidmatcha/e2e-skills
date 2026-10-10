let nextChart = 1000;

export function newChartNumber(): string {
  nextChart += 1;
  return `CH-${nextChart}`;
}
