// Error tracking (AI-09b). On only when EXPO_PUBLIC_SENTRY_DSN is set at build time; otherwise every
// call here is a no-op, so local runs and the tests never talk to Sentry.
// What leaves the device: the error, the stack, the route, the app version and the pseudonymous user
// id — no e-mail, no IP (sendDefaultPii off), no photos, no request bodies.
import * as Sentry from '@sentry/react-native';
import Constants from 'expo-constants';
import type { ComponentType } from 'react';

export const SENTRY_DSN = process.env.EXPO_PUBLIC_SENTRY_DSN || '';

export function initSentry() {
  if (!SENTRY_DSN) return;
  Sentry.init({
    dsn: SENTRY_DSN,
    environment: process.env.EXPO_PUBLIC_SENTRY_ENVIRONMENT || 'production',
    release: Constants.expoConfig?.version ? `smartwardrobe@${Constants.expoConfig.version}` : undefined,
    sendDefaultPii: false,
    // No tracesSampleRate at all: a number (even 0) switches the performance instrumentation on.
    enableAutoSessionTracking: true,
    integrations: [Sentry.expoRouterIntegration()], // navigation breadcrumbs
    beforeSend(event) {
      if (event.user) event.user = { id: event.user.id };
      delete event.request; // on the web this is the page URL + user agent; route context comes from breadcrumbs
      return event;
    },
    beforeBreadcrumb(crumb) {
      // fetch/xhr breadcrumbs carry the request URL; /weather?lat=…&lon=… must not travel (§11).
      if ((crumb.category === 'fetch' || crumb.category === 'xhr') && typeof crumb.data?.url === 'string') {
        crumb.data.url = crumb.data.url.split('?')[0];
      }
      return crumb;
    },
  });
}

/** The pseudonymous account id, so errors group per account; null on sign-out. */
export function setSentryUser(id: string | null) {
  if (!SENTRY_DSN) return;
  Sentry.setUser(id ? { id } : null);
}

/** Wraps the root component for native crash + touch breadcrumbs; identity when Sentry is off. */
export function wrapRoot<T extends ComponentType<Record<string, never>>>(component: T): T {
  return SENTRY_DSN ? (Sentry.wrap(component) as T) : component;
}

export const captureException = (e: unknown) => {
  if (SENTRY_DSN) Sentry.captureException(e);
};
