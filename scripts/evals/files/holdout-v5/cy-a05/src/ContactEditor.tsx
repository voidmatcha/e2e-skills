import { useState } from 'react';
import { createContact } from './contact-service';

export function ContactEditor() {
  const [name, setName] = useState('');

  return (
    <form>
      <input data-cy="name" value={name} onChange={(event) => setName(event.target.value)} />
      <button data-cy="save" type="button" onClick={() => void createContact(name)}>
        Save
      </button>
    </form>
  );
}
