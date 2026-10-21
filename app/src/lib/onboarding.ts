import { StylePatch } from './api';

// Onboarding state before any account exists. Kept in memory only: the answers are written to the
// account the moment it is created (AuthForm), the first-pieces flag is consumed by index.tsx right
// after sign-in. Meaningless across app restarts, cleared when the user takes another path.
let pending: StylePatch | null = null;
let firstPieces = false;

export function setPendingOnboarding(s: StylePatch | null, first: boolean): void {
  pending = s;
  firstPieces = first;
}

export function clearPendingOnboarding(): void {
  pending = null;
  firstPieces = false;
}

export function takePendingStyle(): StylePatch | null {
  const s = pending;
  pending = null;
  return s;
}

/** True once: whether the account that just signed in should go straight to its first pieces. */
export function takeFirstPieces(): boolean {
  const f = firstPieces;
  firstPieces = false;
  return f;
}
