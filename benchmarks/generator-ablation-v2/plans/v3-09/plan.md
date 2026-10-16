# v3-09 Test Plan

## Application Overview

Cover the flashcards app (`/`): two decks, Spanish basics (hola, gracias, adiós; gracias already learned) and Capitals (Norway, Peru). Study on a deck opens the Study panel titled `Studying <deck>` with the first card's front and `Card 1 of N`. Flip reveals the back. Got it marks the card learned and Again leaves it unlearned; both advance to the next card and the `Card N of M` line follows. After the last card the panel shows `Session done` and `All N cards reviewed`, and the deck's `N cards · M learned` line reflects the learned count. Learned state is stored on the server and survives a reload. Back to decks closes the panel.

## Test Scenarios

### 1. v3-09 approved behaviors

**Seed:** `tests/seed.spec.ts`

#### 1.1 Behavior 1

**Steps:**
  1. Exercise this behavior in the running app: Cover the flashcards app (`/`): two decks, Spanish basics (hola, gracias, adiós; gracias already learned) and Capitals (Norway, Peru).

**Expected Results:**
  - Cover the flashcards app (`/`): two decks, Spanish basics (hola, gracias, adiós; gracias already learned) and Capitals (Norway, Peru).

#### 1.2 Behavior 2

**Steps:**
  1. Exercise this behavior in the running app: Study on a deck opens the Study panel titled `Studying <deck>` with the first card's front and `Card 1 of N`.

**Expected Results:**
  - Study on a deck opens the Study panel titled `Studying <deck>` with the first card's front and `Card 1 of N`.

#### 1.3 Behavior 3

**Steps:**
  1. Exercise this behavior in the running app: Flip reveals the back.

**Expected Results:**
  - Flip reveals the back.

#### 1.4 Behavior 4

**Steps:**
  1. Exercise this behavior in the running app: Got it marks the card learned and Again leaves it unlearned; both advance to the next card and the `Card N of M` line follows.

**Expected Results:**
  - Got it marks the card learned and Again leaves it unlearned; both advance to the next card and the `Card N of M` line follows.

#### 1.5 Behavior 5

**Steps:**
  1. Exercise this behavior in the running app: After the last card the panel shows `Session done` and `All N cards reviewed`, and the deck's `N cards · M learned` line reflects the learned count.

**Expected Results:**
  - After the last card the panel shows `Session done` and `All N cards reviewed`, and the deck's `N cards · M learned` line reflects the learned count.

#### 1.6 Behavior 6

**Steps:**
  1. Exercise this behavior in the running app: Learned state is stored on the server and survives a reload.

**Expected Results:**
  - Learned state is stored on the server and survives a reload.

#### 1.7 Behavior 7

**Steps:**
  1. Exercise this behavior in the running app: Back to decks closes the panel.

**Expected Results:**
  - Back to decks closes the panel.
