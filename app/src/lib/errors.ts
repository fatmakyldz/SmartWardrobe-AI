import { ApiError } from './api';
import { useI18n } from './i18n';

export function useErrorText() {
  const { t } = useI18n();
  return (err: unknown): string => {
    const code = err instanceof ApiError ? err.code : 'unknown';
    return (t.errors as Record<string, string>)[code] ?? t.errors.unknown;
  };
}
