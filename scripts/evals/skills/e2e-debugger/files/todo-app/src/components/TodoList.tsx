import { useState } from 'react';
import { addTodo, type Todo } from '../api/todos';

export function TodoList() {
  const [todos, setTodos] = useState<Todo[]>([]);
  const [title, setTitle] = useState('');
  const [error, setError] = useState('');

  async function submit() {
    try {
      const saved = await addTodo(title);
      setTodos([...todos, saved]);
      setTitle('');
    } catch {
      setError('Could not save');
    }
  }

  return (
    <main>
      <label htmlFor="new-todo">New todo</label>
      <input id="new-todo" value={title} onChange={(e) => setTitle(e.target.value)} />
      <button onClick={submit}>Add todo</button>
      {error && <p role="alert">{error}</p>}
      <ul aria-label="Todos">
        {todos.map((todo) => (
          <li key={todo.id}>{todo.title}</li>
        ))}
      </ul>
    </main>
  );
}
