import { useState } from 'react';

export function FavouriteInstructor({ instructorId }: { instructorId: string }) {
  const [saved, setSaved] = useState(false);
  function toggle() {
    setSaved(!saved);
    void fetch(`/api/me/favourite-instructors/${instructorId}`, { method: saved ? 'DELETE' : 'PUT' });
  }
  return (
    <button aria-pressed={saved} onClick={toggle}>
      Favourite instructor
    </button>
  );
}
