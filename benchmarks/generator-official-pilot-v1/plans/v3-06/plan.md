# v3-06 Test Plan

## Application Overview

Cover the budget envelopes page (`/`): three cards (Groceries $120 of $300, Transport $150 of $150, Fun $0 of $100). Adding spending to an envelope raises its `$spent of $limit` line and its progress bar's aria-valuenow (the percentage of the limit, capped at 100), and the Total line (`Total $270 of $550`) sums every envelope. An envelope whose spending exceeds its limit shows the Over budget badge; spending exactly the limit does not. Reset envelope sets its spending back to $0 and removes the badge. Spending is stored on the server and survives a reload.

## Test Scenarios

### 1. v3-06 approved behaviors

**Seed:** `tests/seed.spec.ts`

#### 1.1 Behavior 1

**Steps:**
  1. Exercise this behavior in the running app: Cover the budget envelopes page (`/`): three cards (Groceries $120 of $300, Transport $150 of $150, Fun $0 of $100).

**Expected Results:**
  - Cover the budget envelopes page (`/`): three cards (Groceries $120 of $300, Transport $150 of $150, Fun $0 of $100).

#### 1.2 Behavior 2

**Steps:**
  1. Exercise this behavior in the running app: Adding spending to an envelope raises its `$spent of $limit` line and its progress bar's aria-valuenow (the percentage of the limit, capped at 100), and the Total line (`Total $270 of $550`) sums every envelope.

**Expected Results:**
  - Adding spending to an envelope raises its `$spent of $limit` line and its progress bar's aria-valuenow (the percentage of the limit, capped at 100), and the Total line (`Total $270 of $550`) sums every envelope.

#### 1.3 Behavior 3

**Steps:**
  1. Exercise this behavior in the running app: An envelope whose spending exceeds its limit shows the Over budget badge; spending exactly the limit does not.

**Expected Results:**
  - An envelope whose spending exceeds its limit shows the Over budget badge; spending exactly the limit does not.

#### 1.4 Behavior 4

**Steps:**
  1. Exercise this behavior in the running app: Reset envelope sets its spending back to $0 and removes the badge.

**Expected Results:**
  - Reset envelope sets its spending back to $0 and removes the badge.

#### 1.5 Behavior 5

**Steps:**
  1. Exercise this behavior in the running app: Spending is stored on the server and survives a reload.

**Expected Results:**
  - Spending is stored on the server and survives a reload.
