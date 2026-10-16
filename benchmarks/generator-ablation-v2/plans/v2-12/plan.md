# v2-12 Test Plan

## Application Overview

Cover the expense tracker (`/`). Adding a description and an amount lists the expense, newest first, with the amount formatted like `$12.50`, and the total line updates. Leaving the Amount field with an invalid value (empty, zero, negative or not a number) shows `Amount must be a positive number` next to it as soon as the field loses focus, and Add is refused until the amount is fixed. Edit lets an expense's amount be changed in place and the total follows the change. Delete removes an expense. Expenses, edits and deletions are stored on the server and survive a reload.

## Test Scenarios

### 1. v2-12 approved behaviors

**Seed:** `tests/seed.spec.ts`

#### 1.1 Behavior 1

**Steps:**
  1. Exercise this behavior in the running app: Adding a description and an amount lists the expense, newest first, with the amount formatted like `$12.50`, and the total line updates.

**Expected Results:**
  - Adding a description and an amount lists the expense, newest first, with the amount formatted like `$12.50`, and the total line updates.

#### 1.2 Behavior 2

**Steps:**
  1. Exercise this behavior in the running app: Leaving the Amount field with an invalid value (empty, zero, negative or not a number) shows `Amount must be a positive number` next to it as soon as the field loses focus, and Add is refused until the amount is fixed.

**Expected Results:**
  - Leaving the Amount field with an invalid value (empty, zero, negative or not a number) shows `Amount must be a positive number` next to it as soon as the field loses focus, and Add is refused until the amount is fixed.

#### 1.3 Behavior 3

**Steps:**
  1. Exercise this behavior in the running app: Edit lets an expense's amount be changed in place and the total follows the change.

**Expected Results:**
  - Edit lets an expense's amount be changed in place and the total follows the change.

#### 1.4 Behavior 4

**Steps:**
  1. Exercise this behavior in the running app: Delete removes an expense.

**Expected Results:**
  - Delete removes an expense.

#### 1.5 Behavior 5

**Steps:**
  1. Exercise this behavior in the running app: Expenses, edits and deletions are stored on the server and survive a reload.

**Expected Results:**
  - Expenses, edits and deletions are stored on the server and survive a reload.
