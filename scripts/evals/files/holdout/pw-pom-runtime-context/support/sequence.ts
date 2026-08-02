let sequence = 0;

export function nextSequence(): number {
  sequence += 1;
  return sequence;
}
