import { execFileSync } from 'node:child_process';

// Recreates the local project's database only; the staging host is never reset.
export default async function globalSetup() {
  execFileSync('docker', ['compose', '-f', 'e2e/db.compose.yml', 'up', '-d', '--force-recreate']);
  execFileSync('npm', ['run', 'db:migrate:e2e']);
}
