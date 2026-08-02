const PROBE_CASE = Cypress.env("probeCase");
let assertionStartedAt = 0;

function selectedCase(id, title, callback) {
  const declaration = PROBE_CASE === id ? it : it.skip;
  declaration(title, callback);
}

function startProbe(marker) {
  cy.task("probeLog", marker).then(() => {
    assertionStartedAt = Date.now();
  });
}

afterEach(function recordZeroTimeoutObservation() {
  if (!this.currentTest.title.includes("timeout zero")) {
    return;
  }
  cy.document().then((document) => {
    const status = document.querySelector("#status")?.textContent ?? "missing";
    const elapsedMs = Date.now() - assertionStartedAt;
    cy.task(
      "probeLog",
      `PROBE_ZERO_OBSERVED elapsed_ms=${elapsedMs} status=${status}`,
    );
  });
});

selectedCase(
  "default-retries",
  "#4g Cypress default command timeout retries until delayed DOM change",
  () => {
    cy.visit("/");
    startProbe("PROBE_DEFAULT_RETRY_STARTED");
    cy.get("#status")
      .should("have.text", "ready")
      .then(() => {
        const elapsedMs = Date.now() - assertionStartedAt;
        cy.task(
          "probeLog",
          `PROBE_DEFAULT_RETRY_PASSED elapsed_ms=${elapsedMs} status=ready`,
        );
      });
  },
);

selectedCase(
  "timeout-zero-delayed",
  "#4g Cypress timeout zero checks delayed state immediately",
  () => {
    cy.visit("/");
    startProbe("PROBE_TIMEOUT_ZERO_DELAYED_STARTED");
    cy.get("#status", { timeout: 0 }).should("have.text", "ready");
  },
);

selectedCase(
  "timeout-zero-missing",
  "#4g Cypress timeout zero checks a missing selector immediately",
  () => {
    cy.visit("/");
    startProbe("PROBE_TIMEOUT_ZERO_MISSING_STARTED");
    cy.get("#missing-status", { timeout: 0 }).should("exist");
  },
);
