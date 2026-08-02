const release = {
  only(channels: string[], selected: string) {
    return channels.filter((channel) => channel === selected);
  },
};

describe("counter", () => {
  it.only("renders the counter", () => {
    cy.visit("/counter");
    cy.get('[role="status"]').should("have.text", "Count: 0");
  });

  it("selects the stable release", () => {
    expect(release.only(["stable", "beta"], "stable")).to.deep.equal(["stable"]);
  });
});
