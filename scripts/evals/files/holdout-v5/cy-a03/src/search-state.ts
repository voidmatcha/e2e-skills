export type SearchState = 'idle' | 'loading' | 'ready';

export function nextState(state: SearchState): SearchState {
  return state === 'loading' ? 'ready' : 'loading';
}
