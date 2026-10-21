import { useQueryClient } from '@tanstack/react-query';
import { useCallback } from 'react';

import { ApiError, Entitlements } from './api';
import { keys } from './queries';
import { useI18n } from './i18n';

/** Error code → text. Stable per language, so it is safe in effect dependency lists. */
export function useErrorText() {
  const { t } = useI18n();
  const qc = useQueryClient();
  return useCallback(
    (err: unknown): string => {
      const code = err instanceof ApiError ? err.code : 'unknown';
      // Limit messages carry the plan's own numbers when the entitlements are known (AI-08).
      const ent = qc.getQueryData<Entitlements>(keys.entitlements);
      if (code === 'wardrobe_full' && ent) return t.errors.wardrobe_full_n(ent.max_items);
      // The token budget can run out with requests left; only name the request count when that is what ran out.
      if (code === 'budget_exceeded' && ent?.usage.requests_left === 0) return t.errors.budget_exceeded_n(ent.daily_ai_requests);
      const text = (t.errors as unknown as Record<string, string | ((n: number) => string)>)[code];
      return typeof text === 'string' ? text : t.errors.unknown;
    },
    [t, qc],
  );
}
