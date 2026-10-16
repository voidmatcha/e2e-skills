# v2-22 Test Plan

## Application Overview

Cover the orders page (`/`): eight orders with numbers like `1001`, `1010`, `2010` and a status of paid, shipped or refunded. The Status filter and the Search box (matches order numbers containing the typed digits) narrow the list together, so both conditions must hold; the `N orders` line follows the list. The filters are mirrored in the URL (`?status=shipped&q=101`), so a reload, or opening such a URL directly, shows the same filtered list with the controls set accordingly. Clear filters empties both controls and shows every order again.

## Test Scenarios

### 1. v2-22 approved behaviors

**Seed:** `tests/seed.spec.ts`

#### 1.1 Behavior 1

**Steps:**
  1. Exercise this behavior in the running app: Cover the orders page (`/`): eight orders with numbers like `1001`, `1010`, `2010` and a status of paid, shipped or refunded.

**Expected Results:**
  - Cover the orders page (`/`): eight orders with numbers like `1001`, `1010`, `2010` and a status of paid, shipped or refunded.

#### 1.2 Behavior 2

**Steps:**
  1. Exercise this behavior in the running app: The Status filter and the Search box (matches order numbers containing the typed digits) narrow the list together, so both conditions must hold; the `N orders` line follows the list.

**Expected Results:**
  - The Status filter and the Search box (matches order numbers containing the typed digits) narrow the list together, so both conditions must hold; the `N orders` line follows the list.

#### 1.3 Behavior 3

**Steps:**
  1. Exercise this behavior in the running app: The filters are mirrored in the URL (`?status=shipped&q=101`), so a reload, or opening such a URL directly, shows the same filtered list with the controls set accordingly.

**Expected Results:**
  - The filters are mirrored in the URL (`?status=shipped&q=101`), so a reload, or opening such a URL directly, shows the same filtered list with the controls set accordingly.

#### 1.4 Behavior 4

**Steps:**
  1. Exercise this behavior in the running app: Clear filters empties both controls and shows every order again.

**Expected Results:**
  - Clear filters empties both controls and shows every order again.
