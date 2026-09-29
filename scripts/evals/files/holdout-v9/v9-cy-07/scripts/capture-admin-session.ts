// Run by hand after signing in as the admin in a normal browser window:
//   npx ts-node scripts/capture-admin-session.ts <cookie-value>
import { writeFileSync } from 'node:fs';

const cookie = process.argv[2];
writeFileSync('cypress/fixtures/sessions/admin-session.json', JSON.stringify({ cookie }));
