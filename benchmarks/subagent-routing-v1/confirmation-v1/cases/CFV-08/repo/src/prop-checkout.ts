// confirmation-case: CFV-08/src/prop-checkout.ts
export async function checkOutProp(propId: string) {
  return fetch(`/api/props/${propId}/checkout`, { method: 'POST' });
}
