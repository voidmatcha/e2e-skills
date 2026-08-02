export function SignupForm() {
  const submit = async () => {
    await fetch('/api/signup', { method: 'POST' });
  };

  return (
    <button data-cy="signup-submit" onClick={submit} type="button">
      Sign up
    </button>
  );
}
