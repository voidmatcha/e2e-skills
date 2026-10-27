# Roster import change

Scope: the test changed in `changes.patch`; `roster-import.cy.ts` is the current proposed source.

## Accepted requirements

Roster Import RI-4, approved on 2026-08-19, limited the client to CSV files.
Its example for a `.tsv` file required "Choose a CSV file" and no submission.
RI-9, approved by the roster product owner on 2026-10-23 and effective for this
patch, supersedes that extension rule: the client must submit CSV or TSV files.
For a TSV file containing the header `name` and one data row, a successful
`POST /api/roster-imports` response with `imported: 1` must display
"1 member imported". The TSV media type is `text/tab-separated-values`.
The approval explicitly removes the old TSV rejection example.

## Scenario inputs and scope

`/roster/import` has a file input labelled "Roster file", an Import button,
and a status region. The selected bytes are a valid single-column TSV file.
The replacement test supplies a 201 response from the import service to exercise
the client selection, submission, and success rendering. That service stub does
not establish production parser behavior; server parsing is outside this test's
client acceptance scope.

## Evidence boundary

The requirements and UI contract above are authored scenario documents. Neither
the before nor the after test was executed for this fixture; the stub is a test
input, not a recording of an actual service response.
