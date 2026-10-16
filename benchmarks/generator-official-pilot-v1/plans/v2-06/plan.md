# v2-06 Test Plan

## Application Overview

Cover the article tag editor (`/`). Typing a tag and pressing Enter adds it as a chip and clears the box; a tag that is already there, compared without regard to letter case, is rejected with `Already added`; pressing Backspace in the empty box removes the last chip; each chip's remove button removes that chip. At most five tags can be added: once there are five, `Tag limit reached` is shown and the box is disabled until a chip is removed. Save stores the tags, shows `Tags saved`, and a reload shows the saved tags.

## Test Scenarios

### 1. v2-06 approved behaviors

**Seed:** `tests/seed.spec.ts`

#### 1.1 Behavior 1

**Steps:**
  1. Exercise this behavior in the running app: Typing a tag and pressing Enter adds it as a chip and clears the box; a tag that is already there, compared without regard to letter case, is rejected with `Already added`; pressing Backspace in the empty box removes the last chip; each chip's remove button removes that chip.

**Expected Results:**
  - Typing a tag and pressing Enter adds it as a chip and clears the box; a tag that is already there, compared without regard to letter case, is rejected with `Already added`; pressing Backspace in the empty box removes the last chip; each chip's remove button removes that chip.

#### 1.2 Behavior 2

**Steps:**
  1. Exercise this behavior in the running app: At most five tags can be added: once there are five, `Tag limit reached` is shown and the box is disabled until a chip is removed.

**Expected Results:**
  - At most five tags can be added: once there are five, `Tag limit reached` is shown and the box is disabled until a chip is removed.

#### 1.3 Behavior 3

**Steps:**
  1. Exercise this behavior in the running app: Save stores the tags, shows `Tags saved`, and a reload shows the saved tags.

**Expected Results:**
  - Save stores the tags, shows `Tags saved`, and a reload shows the saved tags.
