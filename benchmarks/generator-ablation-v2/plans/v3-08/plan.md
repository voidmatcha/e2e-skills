# v3-08 Test Plan

## Application Overview

Cover the issue list (`/`) for the signed-in user Ada: five seeded issues (#101 to #105; #105 is already Ada's, #102 is Grace's). Assign to me sets that issue's assignee line to `Assigned to Ada` and its button becomes Unassign; Unassign reverts it to `Unassigned`. The filter chips carry live counts (`All (5)`, `Mine (2)`, `Unassigned (2)`) and the Mine chip shows only Ada's issues. Changing an issue's priority with its Priority select updates its `Priority: <level>` badge and the list is ordered high, then medium, then low. Assignments and priorities are stored on the server and survive a reload.

## Test Scenarios

### 1. v3-08 approved behaviors

**Seed:** `tests/seed.spec.ts`

#### 1.1 Behavior 1

**Steps:**
  1. Exercise this behavior in the running app: Cover the issue list (`/`) for the signed-in user Ada: five seeded issues (#101 to #105; #105 is already Ada's, #102 is Grace's).

**Expected Results:**
  - Cover the issue list (`/`) for the signed-in user Ada: five seeded issues (#101 to #105; #105 is already Ada's, #102 is Grace's).

#### 1.2 Behavior 2

**Steps:**
  1. Exercise this behavior in the running app: Assign to me sets that issue's assignee line to `Assigned to Ada` and its button becomes Unassign; Unassign reverts it to `Unassigned`.

**Expected Results:**
  - Assign to me sets that issue's assignee line to `Assigned to Ada` and its button becomes Unassign; Unassign reverts it to `Unassigned`.

#### 1.3 Behavior 3

**Steps:**
  1. Exercise this behavior in the running app: The filter chips carry live counts (`All (5)`, `Mine (2)`, `Unassigned (2)`) and the Mine chip shows only Ada's issues.

**Expected Results:**
  - The filter chips carry live counts (`All (5)`, `Mine (2)`, `Unassigned (2)`) and the Mine chip shows only Ada's issues.

#### 1.4 Behavior 4

**Steps:**
  1. Exercise this behavior in the running app: Changing an issue's priority with its Priority select updates its `Priority: <level>` badge and the list is ordered high, then medium, then low.

**Expected Results:**
  - Changing an issue's priority with its Priority select updates its `Priority: <level>` badge and the list is ordered high, then medium, then low.

#### 1.5 Behavior 5

**Steps:**
  1. Exercise this behavior in the running app: Assignments and priorities are stored on the server and survive a reload.

**Expected Results:**
  - Assignments and priorities are stored on the server and survive a reload.
