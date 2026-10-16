# v3-03 Test Plan

## Application Overview

Cover the team roster (`/`), a table of five members (one, Linus Torvalds, starts on leave). Toggle leave switches that member's status badge between Active and On leave, and the headcount line (`5 members · 1 on leave`) follows. Remove opens an inline confirmation row under that member (`Remove Ada?` with Confirm and Cancel): Cancel keeps the member and closes the row; Confirm removes exactly that member and updates the headcount. Leave status and removals are stored on the server and survive a reload.

## Test Scenarios

### 1. v3-03 approved behaviors

**Seed:** `tests/seed.spec.ts`

#### 1.1 Behavior 1

**Steps:**
  1. Exercise this behavior in the running app: Toggle leave switches that member's status badge between Active and On leave, and the headcount line (`5 members · 1 on leave`) follows.

**Expected Results:**
  - Toggle leave switches that member's status badge between Active and On leave, and the headcount line (`5 members · 1 on leave`) follows.

#### 1.2 Behavior 2

**Steps:**
  1. Exercise this behavior in the running app: Remove opens an inline confirmation row under that member (`Remove Ada?` with Confirm and Cancel): Cancel keeps the member and closes the row; Confirm removes exactly that member and updates the headcount.

**Expected Results:**
  - Remove opens an inline confirmation row under that member (`Remove Ada?` with Confirm and Cancel): Cancel keeps the member and closes the row; Confirm removes exactly that member and updates the headcount.

#### 1.3 Behavior 3

**Steps:**
  1. Exercise this behavior in the running app: Leave status and removals are stored on the server and survive a reload.

**Expected Results:**
  - Leave status and removals are stored on the server and survive a reload.
