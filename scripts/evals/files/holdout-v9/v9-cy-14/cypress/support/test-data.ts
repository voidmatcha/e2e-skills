let orderSequence = 100;

export function nextOrderNumber(): string {
  orderSequence += 1;
  return `ORD-${orderSequence}`;
}
