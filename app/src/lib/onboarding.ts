import { StylePatch } from './api';

// Onboarding answers given before any account exists. Kept in memory only: they are written to the
// account the moment it is created (AuthForm) and are meaningless across app restarts.
let pending: StylePatch | null = null;

export function setPendingStyle(s: StylePatch | null): void {
  pending = s;
}

export function takePendingStyle(): StylePatch | null {
  const s = pending;
  pending = null;
  return s;
}
