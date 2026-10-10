# Contributing

## End-to-end tests

Flaky Cypress specs are quarantined with a bare `it.skip` and listed in
`cypress/QUARANTINE.md` with the owner, the tracking ticket, and a revisit date.
The weekly triage job reads that file; a skip that is not listed there is a bug.
