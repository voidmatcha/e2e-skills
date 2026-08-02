import { ReleaseChannel } from '../pages/release-channel';
import { releasePolicy } from '../../src/release-policy';

describe('release channel', () => {
  const channel = new ReleaseChannel();

  it('selects the stable channel', () => {
    channel.open();
    channel.choose('stable');
    cy.get('[data-cy=current-channel]').should('have.text', 'stable');
  });

  it('waits for the channel request', () => {
    cy.intercept('GET', '/api/channel').as('channel');
    channel.open();
    cy.wait('@channel');
    cy.get('[data-cy=current-channel]').should('be.visible');
  });

  it('filters the channel list', () => {
    expect(releasePolicy.only(['stable', 'beta'], 'stable')).to.deep.equal(['stable']);
  });
});
