import { only as pickOnly } from '../support/collections';

const {
  only: focusOn,
} = it;

describe('daily chess puzzles', () => {
  beforeEach(() => {
    cy.visit('/puzzles/daily');
  });

  focusOn('accepts the winning knight move', () => {
    cy.get('[data-cy=square-f3]').click();
    cy.get('[data-cy=square-g5]').click();
    cy.get('[data-cy=puzzle-result]').should('have.text', 'Solved in 1 move');
  });

  it('shows one chip per unsolved theme', () => {
    cy.fixture('themes.json').then((themes: { name: string; solved: boolean }[]) => {
      const unsolved = pickOnly(themes, (theme) => !theme.solved);
      cy.get('[data-cy=theme-chip]').should('have.length', unsolved.length);
    });
  });
});
