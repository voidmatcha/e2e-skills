# v2-23 Test Plan

## Application Overview

Cover account deletion on the account page (`/`). Delete account opens a confirmation dialog whose Delete my account button stays disabled until the box contains exactly `DELETE` (lower-case or partial text does not count). Escape, like Cancel, closes the dialog without deleting and moves focus back to the Delete account button. Confirming deletes the account on the server and shows `Your account has been deleted` in place of the profile; after a reload the page still shows the account as deleted.

## Test Scenarios

### 1. v2-23 approved behaviors

**Seed:** `tests/seed.spec.ts`

#### 1.1 Behavior 1

**Steps:**
  1. Exercise this behavior in the running app: Delete account opens a confirmation dialog whose Delete my account button stays disabled until the box contains exactly `DELETE` (lower-case or partial text does not count).

**Expected Results:**
  - Delete account opens a confirmation dialog whose Delete my account button stays disabled until the box contains exactly `DELETE` (lower-case or partial text does not count).

#### 1.2 Behavior 2

**Steps:**
  1. Exercise this behavior in the running app: Escape, like Cancel, closes the dialog without deleting and moves focus back to the Delete account button.

**Expected Results:**
  - Escape, like Cancel, closes the dialog without deleting and moves focus back to the Delete account button.

#### 1.3 Behavior 3

**Steps:**
  1. Exercise this behavior in the running app: Confirming deletes the account on the server and shows `Your account has been deleted` in place of the profile; after a reload the page still shows the account as deleted.

**Expected Results:**
  - Confirming deletes the account on the server and shows `Your account has been deleted` in place of the profile; after a reload the page still shows the account as deleted.
