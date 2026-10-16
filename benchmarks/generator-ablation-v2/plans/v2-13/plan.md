# v2-13 Test Plan

## Application Overview

Cover the sprint board (`/`): three columns, seven seeded cards (four in Todo, two in In progress, one in Done). A card can be moved to another column by dragging it onto that column or with its Move menu, and it then appears in the new column only; each column heading shows its card count in parentheses. In progress holds at most three cards: moving a fourth there is refused with `In progress is full (limit 3)` and the card stays in its column. Moves are stored on the server, so a reload shows the same board.

## Test Scenarios

### 1. v2-13 approved behaviors

**Seed:** `tests/seed.spec.ts`

#### 1.1 Behavior 1

**Steps:**
  1. Exercise this behavior in the running app: Cover the sprint board (`/`): three columns, seven seeded cards (four in Todo, two in In progress, one in Done).

**Expected Results:**
  - Cover the sprint board (`/`): three columns, seven seeded cards (four in Todo, two in In progress, one in Done).

#### 1.2 Behavior 2

**Steps:**
  1. Exercise this behavior in the running app: A card can be moved to another column by dragging it onto that column or with its Move menu, and it then appears in the new column only; each column heading shows its card count in parentheses.

**Expected Results:**
  - A card can be moved to another column by dragging it onto that column or with its Move menu, and it then appears in the new column only; each column heading shows its card count in parentheses.

#### 1.3 Behavior 3

**Steps:**
  1. Exercise this behavior in the running app: In progress holds at most three cards: moving a fourth there is refused with `In progress is full (limit 3)` and the card stays in its column.

**Expected Results:**
  - In progress holds at most three cards: moving a fourth there is refused with `In progress is full (limit 3)` and the card stays in its column.

#### 1.4 Behavior 4

**Steps:**
  1. Exercise this behavior in the running app: Moves are stored on the server, so a reload shows the same board.

**Expected Results:**
  - Moves are stored on the server, so a reload shows the same board.
