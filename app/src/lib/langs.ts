// The languages the app speaks. Adding one: a label here, a dictionary in i18n.tsx (typed against
// the English one, so a missing key fails typecheck), plus the backend side (vocab.LANGS and the
// templates it lists). English is the fallback for any device language not in this list.
export const SUPPORTED_LANGS = ['en', 'tr'] as const;
export type Lang = (typeof SUPPORTED_LANGS)[number];
export const LANG_LABELS: Record<Lang, string> = { en: 'English', tr: 'Türkçe' };
export const DEFAULT_LANG: Lang = 'en';

export function isLang(x: unknown): x is Lang {
  return typeof x === 'string' && (SUPPORTED_LANGS as readonly string[]).includes(x);
}

/** A supported language from any code the device or server hands us ("tr-TR" → "tr"), else English. */
export function toLang(code: string | null | undefined): Lang {
  const base = (code ?? '').toLowerCase().split('-')[0];
  return isLang(base) ? base : DEFAULT_LANG;
}
