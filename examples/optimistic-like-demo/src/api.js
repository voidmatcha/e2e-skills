export async function postLike() {
  const response = await fetch("/api/like", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ liked: true }),
  });
  if (!response.ok) throw new Error(`POST /api/like returned ${response.status}`);
}

export async function getLike() {
  const response = await fetch("/api/like");
  return (await response.json()).liked;
}
