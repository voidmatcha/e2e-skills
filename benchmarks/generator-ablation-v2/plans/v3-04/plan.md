# v3-04 Test Plan

## Application Overview

Cover the playlist editor (`/`), seeded with four tracks (Blue in Green 5:37, So What 9:22, Freddie Freeloader 9:49, All Blues 11:33). Play shows the Now playing panel with that track's title and Stop hides the panel. Move up and Move down reorder the tracks and the new order survives a reload. The Total line (`Total 36:21`) sums the track lengths and follows a removal; Remove deletes a track. The Repeat toggle reports its state through aria-pressed and the setting is remembered on the server across a reload.

## Test Scenarios

### 1. v3-04 approved behaviors

**Seed:** `tests/seed.spec.ts`

#### 1.1 Behavior 1

**Steps:**
  1. Exercise this behavior in the running app: Cover the playlist editor (`/`), seeded with four tracks (Blue in Green 5:37, So What 9:22, Freddie Freeloader 9:49, All Blues 11:33).

**Expected Results:**
  - Cover the playlist editor (`/`), seeded with four tracks (Blue in Green 5:37, So What 9:22, Freddie Freeloader 9:49, All Blues 11:33).

#### 1.2 Behavior 2

**Steps:**
  1. Exercise this behavior in the running app: Play shows the Now playing panel with that track's title and Stop hides the panel.

**Expected Results:**
  - Play shows the Now playing panel with that track's title and Stop hides the panel.

#### 1.3 Behavior 3

**Steps:**
  1. Exercise this behavior in the running app: Move up and Move down reorder the tracks and the new order survives a reload.

**Expected Results:**
  - Move up and Move down reorder the tracks and the new order survives a reload.

#### 1.4 Behavior 4

**Steps:**
  1. Exercise this behavior in the running app: The Total line (`Total 36:21`) sums the track lengths and follows a removal; Remove deletes a track.

**Expected Results:**
  - The Total line (`Total 36:21`) sums the track lengths and follows a removal; Remove deletes a track.

#### 1.5 Behavior 5

**Steps:**
  1. Exercise this behavior in the running app: The Repeat toggle reports its state through aria-pressed and the setting is remembered on the server across a reload.

**Expected Results:**
  - The Repeat toggle reports its state through aria-pressed and the setting is remembered on the server across a reload.
