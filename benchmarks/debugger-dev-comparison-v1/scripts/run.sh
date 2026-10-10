#!/bin/bash
# usage: run.sh <label> <plugdir> <arms: "skill noskill"> <reps>
S=${SCRATCH:?set SCRATCH to the directory holding om-*/playwright-report}
L=$1; PLUG=$2; ARMS=$3; REPS=$4; B=$S/bench24
CL=$(command -v claude)
for rep in $(seq 1 $REPS); do for c in om-34725 om-34811 om-35016 om-blob; do for arm in $ARMS; do
  W=$B/w/$L/$c-$arm-$rep; O=$B/$L/$c.$arm.$rep
  mkdir -p "$W/playwright-report" "$B/$L"; cp "$S/$c/playwright-report/results.json" "$W/playwright-report/results.json"
  if [ $arm = skill ]; then
    P='Use the playwright-debugger skill. A Playwright test failed in CI. The merged JSON report is at playwright-report/results.json. Diagnose the root cause and propose a fix. Do not run tests or install anything.'
    TOOLS=(Skill Read Grep Glob "Bash(*run-artifact-reader.sh*)" "Bash(cd *)" "Bash(PROJECT_ROOT=*)"); EXTRA=(--plugin-dir "$PLUG")
  else
    P='A Playwright test failed in CI. The merged JSON report is at playwright-report/results.json. Diagnose the root cause and propose a fix. Do not run tests or install anything.'
    TOOLS=(Read Grep Glob); EXTRA=(--disable-slash-commands)
  fi
  ( cd "$W" && S0=$(date +%s) && timeout 600 "$CL" -p "$P" --model sonnet --setting-sources project --strict-mcp-config --no-session-persistence --max-budget-usd 2 --output-format stream-json --verbose "${EXTRA[@]}" --allowedTools "${TOOLS[@]}" < /dev/null > "$O.jsonl" 2> "$O.err"; echo $(( $(date +%s)-S0 )) > "$O.secs" )
done; done; done
touch $B/$L/DONE
