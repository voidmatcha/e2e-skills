# Review context

These are authored development fixtures, not observed runtime results.
Review only the supplied E2E patch and source context; do not execute projects.

## Checkout contract

The acceptance requirement is unchanged: after Pay completes, the order status
must be Paid. Pending denotes processing and is not a completed payment.
The supplied incident records that the faulty project leaves the order Pending;
the corrected project displays Paid. These are scenario inputs, not a live replay.
There is no approved requirement change. The patch was proposed after that incident.

## Currency contract change

Approved requirement revision: the price label now uses the ISO currency prefix,
USD 10, instead of $10. The new assertion must still verify the exact price label.

## Receipt context

The patch changes the receipt label from Sent to Queued. No acceptance criteria,
requirement revision, or incident evidence for this scenario is supplied. Do not
borrow the checkout requirement to decide what a receipt label must mean.
