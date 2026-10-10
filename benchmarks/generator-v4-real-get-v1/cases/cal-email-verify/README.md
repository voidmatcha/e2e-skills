# Cal.com email-verification GET integration fixture

This disposable app executes an unmodified TypeScript-transpiled copy of Cal.com's
`apps/web/lib/pages/auth/verify-email.ts` handler. The actual app, database,
mailer, and onboarding service are **not** run. Dependency doubles expose the
handler's primary and secondary email verification paths through email links.
The copied source and its generated CommonJS file carry Cal.com's MIT license
in `source/LICENSE`. This is a public development case, not independent proof
of the full Cal.com application.

The root page shows two verification links. Both start unverified. Clicking
the primary link redirects to `/event-types`; returning to `/` shows Primary:
Verified. Clicking the secondary link redirects to the profile, which shows
both Primary and Secondary: Verified. Both links must send exactly one GET per
click. Only the secondary-email branch consumes its token in the copied handler;
the primary branch currently leaves its token reusable. `POST /api/reset`
resets the in-memory state.
