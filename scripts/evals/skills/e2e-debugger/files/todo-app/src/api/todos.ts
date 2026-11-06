export type Todo = { id: number; title: string; done: boolean };

export async function addTodo(title: string): Promise<Todo> {
  const response = await fetch('/api/todos', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ title }),
  });
  if (!response.ok) throw new Error('save failed');
  return response.json();
}
