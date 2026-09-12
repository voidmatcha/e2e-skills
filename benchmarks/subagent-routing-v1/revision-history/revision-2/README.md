# Protocol revision 2 archive

Revision 2 fixed Claude delegation attestation by counting only invocation events and ignoring progress heartbeats. Its fresh Claude smoke passed and the protocol was refrozen, but the first measured cell, `FC-03-claude.named-r2`, stopped `INCOMPLETE` because evidence item 4 did not satisfy the report-citation schema.

The failure exposed a prompt-quality gap: the response schema showed only a file-and-line citation even though every failure-classification case requires at least one `report_field` citation whose source must be the literal string `report_excerpt`. Scoring and the case oracle were internally consistent, so revision 3 adds the missing prompt example and instruction without changing scoring logic or case content.

Preserved digests:

- `protocol.json`: `afd35e126c34ac7782bcc02650854dba2eb0ee17c35ec4168ba826d711b3ec9a`
- `run_routing.py`: `7ff49c83b4b60860659e84da5d654ef678e579fe675fb379fa6956bb4778bd0b`
- `freeze-record.json`: `d9574f3a4607b7841efc5d32cbf824f69c5f55f017ed5bbf29f0a590f1ab45a3`
- `execution-authorization-claude.json`: `fc9d65910b5c34b5248334958c05d2678d0baff0b3a18cc1a0302aa195bfb1b4`
- `smoke-results-claude.json`: `b2724f7d375ebca86c8753fa2ec39d1fc9918007da2157c7a8ceebe125a69dd5`
- `routing-results-claude.json`: `eb96a6e678848f2b7630e5919a1b0b290dfe745c5762e66dd5f994f733648333`
- measured stdout: `2471ec124d2c0bf0e4b2e84b4cbc9c60a97ac7017c811560db10c0565057f3f6`

Revision 2 is preserved, superseded, unscored, and excluded from revision 3.
