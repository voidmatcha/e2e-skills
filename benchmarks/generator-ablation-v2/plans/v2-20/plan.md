# v2-20 Test Plan

## Application Overview

Cover the reading list (`/`): 25 articles, `Article 1` to `Article 25`, loaded ten at a time with Load more, and `Showing N of 25` under the list. Load more never repeats an article and is disabled once all 25 are shown. Mark as read toggles an article's read state (the button then reads Mark as unread) and the state is stored on the server, so a reload shows it. Hide read removes read articles from the list and from the `Showing N of 25` count.

## Test Scenarios

### 1. v2-20 approved behaviors

**Seed:** `tests/seed.spec.ts`

#### 1.1 Behavior 1

**Steps:**
  1. Exercise this behavior in the running app: Cover the reading list (`/`): 25 articles, `Article 1` to `Article 25`, loaded ten at a time with Load more, and `Showing N of 25` under the list.

**Expected Results:**
  - Cover the reading list (`/`): 25 articles, `Article 1` to `Article 25`, loaded ten at a time with Load more, and `Showing N of 25` under the list.

#### 1.2 Behavior 2

**Steps:**
  1. Exercise this behavior in the running app: Load more never repeats an article and is disabled once all 25 are shown.

**Expected Results:**
  - Load more never repeats an article and is disabled once all 25 are shown.

#### 1.3 Behavior 3

**Steps:**
  1. Exercise this behavior in the running app: Mark as read toggles an article's read state (the button then reads Mark as unread) and the state is stored on the server, so a reload shows it.

**Expected Results:**
  - Mark as read toggles an article's read state (the button then reads Mark as unread) and the state is stored on the server, so a reload shows it.

#### 1.4 Behavior 4

**Steps:**
  1. Exercise this behavior in the running app: Hide read removes read articles from the list and from the `Showing N of 25` count.

**Expected Results:**
  - Hide read removes read articles from the list and from the `Showing N of 25` count.
