export async function seedSamplePatron(request: { post(path: string): Promise<{ ok(): boolean }> }) {
  const response = await request.post("/api/test-data/patrons/SAMPLE-PATRON-404");
  if (!response.ok()) {
    throw new Error("Sample patron fixture SAMPLE-PATRON-404 is unavailable");
  }
}
