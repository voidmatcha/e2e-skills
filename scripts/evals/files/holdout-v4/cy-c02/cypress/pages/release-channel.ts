export class ReleaseChannel {
  open() {
    cy.visit('/release');
  }

  choose(name: string) {
    cy.get(`[data-cy=channel-${name}]`).click();
  }
}
