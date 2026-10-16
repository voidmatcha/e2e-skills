# v3-10 Test Plan

## Application Overview

Cover the order tracking page (`/`). The timeline lists five steps (Ordered, Packed, Shipped, Out for delivery, Delivered); exactly one step is marked Current, the earlier ones Done and the later ones Upcoming, and the header line reads `Step N of 5: <step name>`. The Advance (test seam) button moves the order to the next step. Cancel order is offered only while the order has not reached Shipped; cancelling shows `Order cancelled` in the header and the `Cancelled` notice, hides the estimated delivery, and leaves no step marked Current. Progress and cancellation are stored on the server and survive a reload.

## Test Scenarios

### 1. v3-10 approved behaviors

**Seed:** `tests/seed.spec.ts`

#### 1.1 Behavior 1

**Steps:**
  1. Exercise this behavior in the running app: The timeline lists five steps (Ordered, Packed, Shipped, Out for delivery, Delivered); exactly one step is marked Current, the earlier ones Done and the later ones Upcoming, and the header line reads `Step N of 5: <step name>`.

**Expected Results:**
  - The timeline lists five steps (Ordered, Packed, Shipped, Out for delivery, Delivered); exactly one step is marked Current, the earlier ones Done and the later ones Upcoming, and the header line reads `Step N of 5: <step name>`.

#### 1.2 Behavior 2

**Steps:**
  1. Exercise this behavior in the running app: The Advance (test seam) button moves the order to the next step.

**Expected Results:**
  - The Advance (test seam) button moves the order to the next step.

#### 1.3 Behavior 3

**Steps:**
  1. Exercise this behavior in the running app: Cancel order is offered only while the order has not reached Shipped; cancelling shows `Order cancelled` in the header and the `Cancelled` notice, hides the estimated delivery, and leaves no step marked Current.

**Expected Results:**
  - Cancel order is offered only while the order has not reached Shipped; cancelling shows `Order cancelled` in the header and the `Cancelled` notice, hides the estimated delivery, and leaves no step marked Current.

#### 1.4 Behavior 4

**Steps:**
  1. Exercise this behavior in the running app: Progress and cancellation are stored on the server and survive a reload.

**Expected Results:**
  - Progress and cancellation are stored on the server and survive a reload.
