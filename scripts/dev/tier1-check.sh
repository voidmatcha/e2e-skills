#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
#
# Runs the checklist for a Tier 1 change (SKILL.md instruction wording) per
# CONTRIBUTING.md's tier table. Does not write a RED test for you -- that
# part is change-specific -- but reminds you of the sequence and runs the
# two required gates in order.
set -euo pipefail
cd "$(dirname "$0")/../.."

echo "Tier 1 checklist (skill instruction wording change)"
echo "  1. RED: a contract test exists and fails against the OLD wording"
echo "  2. Smallest edit made"
echo "  3. GREEN: the same contract test now passes"
echo "  4. ci-local.sh + pre-push-security.sh both green"
echo
echo "This script only runs step 4. Steps 1-3 are change-specific --"
echo "see scripts/ci/test-routing-contract.py for a worked example."
echo

/bin/bash -p scripts/ci/ci-local.sh
/bin/bash -p scripts/ci/pre-push-security.sh

echo
echo "Tier 1 checklist: gates passed. Confirm you actually wrote a RED test"
echo "for this specific change before opening the PR -- this script cannot"
echo "verify that part for you."
