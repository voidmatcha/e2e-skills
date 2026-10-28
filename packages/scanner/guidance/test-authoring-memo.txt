# Test authoring notes

- Make the server reject the action (intercept the request, answer with an error). Assert the interface returns to its previous state and shows no success indicator.
- Where the code guards an action, attempt the forbidden one: submit invalid or empty input; trigger the same action twice. Assert nothing was sent, or only one request, and state did not change.
- A success indicator is not proof. Assert it appears only after the server confirmed, and read server-side state directly.
- If the interface updates before the server answers, hold the response, assert the pending state, then release it.
- If the code lacks a guard, do not assert it; a test must pass on the unchanged app.

Finally, ask of each assertion: if this behavior broke, would this line fail? Strengthen any that would still pass.
