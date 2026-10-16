# v3-07 Test Plan

## Application Overview

Cover the seat picker (`/`): twelve seats A1 to C4, with A1, B3 and C4 already taken. Clicking a free seat selects it, which its aria-pressed reports as true, and lists it in the Selected line (`Selected: A2, B1`); clicking it again deselects it. At most 4 seats can be selected: a fifth click shows `You can pick up to 4 seats` and selects nothing. The legend (`Selected 2 · Available 7 · Taken 3`) follows every change. Reserve turns the selected seats into taken seats (disabled and counted as Taken), shows `Reserved A2, B1`, and clears the selection; reservations are stored on the server and survive a reload.

## Test Scenarios

### 1. v3-07 approved behaviors

**Seed:** `tests/seed.spec.ts`

#### 1.1 Behavior 1

**Steps:**
  1. Exercise this behavior in the running app: Cover the seat picker (`/`): twelve seats A1 to C4, with A1, B3 and C4 already taken.

**Expected Results:**
  - Cover the seat picker (`/`): twelve seats A1 to C4, with A1, B3 and C4 already taken.

#### 1.2 Behavior 2

**Steps:**
  1. Exercise this behavior in the running app: Clicking a free seat selects it, which its aria-pressed reports as true, and lists it in the Selected line (`Selected: A2, B1`); clicking it again deselects it.

**Expected Results:**
  - Clicking a free seat selects it, which its aria-pressed reports as true, and lists it in the Selected line (`Selected: A2, B1`); clicking it again deselects it.

#### 1.3 Behavior 3

**Steps:**
  1. Exercise this behavior in the running app: At most 4 seats can be selected: a fifth click shows `You can pick up to 4 seats` and selects nothing.

**Expected Results:**
  - At most 4 seats can be selected: a fifth click shows `You can pick up to 4 seats` and selects nothing.

#### 1.4 Behavior 4

**Steps:**
  1. Exercise this behavior in the running app: The legend (`Selected 2 · Available 7 · Taken 3`) follows every change.

**Expected Results:**
  - The legend (`Selected 2 · Available 7 · Taken 3`) follows every change.

#### 1.5 Behavior 5

**Steps:**
  1. Exercise this behavior in the running app: Reserve turns the selected seats into taken seats (disabled and counted as Taken), shows `Reserved A2, B1`, and clears the selection; reservations are stored on the server and survive a reload.

**Expected Results:**
  - Reserve turns the selected seats into taken seats (disabled and counted as Taken), shows `Reserved A2, B1`, and clears the selection; reservations are stored on the server and survive a reload.
