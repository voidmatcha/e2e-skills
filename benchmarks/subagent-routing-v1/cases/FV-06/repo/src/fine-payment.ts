const form = document.querySelector<HTMLFormElement>("[data-fine-payment]");

form?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const fineId = form.dataset.fineId;
  await fetch(`/api/fines/${fineId}/payments`, { method: "POST" });
  form.dataset.status = "paid";
});
